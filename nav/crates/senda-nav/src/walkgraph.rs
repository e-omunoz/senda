//! The travel planner's walk graph (docs/TRAVEL.md, «Andar»): a coarse graph per continent with real
//! walking yards, from Senda's own HPA* packs (nav/out/SendaNav_<map>_graph.lua + _cells.lua).
//! Copyright (C) 2026 Senda contributors. GPL-3.0-only.
//!
//! Nodes: one representative walkable cell per sector region (the abstract nodes of a sector that
//! reach each other without leaving it), plus every planner place of data/travel (flight masters,
//! boarding points, portal ends, inns, teleport landings) snapped to the coarse grid. Edges: the
//! shortest walk between two nodes whose sectors touch (3 x 3 block), over the abstract graph and
//! the sector cells, in yards; an edge a 2-hop path matches within 2 % is dropped. Regions that are
//! only water (open sea, lakes) are left out, and so is every component with no planner place
//! (islands nobody travels to). Between places the walk is also exact: a matrix of the shortest
//! walks over the whole abstract graph (without those water regions).
//!
//!   senda-nav walkgraph --packs nav/out --travel data/travel --out data/travel [--continents 0,1]

use crate::hpa::{self, Abstract, Grid, St, SEC};
use crate::pack;
use rustc_hash::{FxHashMap, FxHashSet};
use serde_json::{json, Value};
use std::cmp::Ordering;
use std::collections::BinaryHeap;
use std::path::Path;

/// Snap radius for a place, in cells (33 yd), as the evaluator.
const SNAP: i32 = 8;
/// Stretch of the greedy spanner: an edge goes when the kept ones already walk it within this.
const PRUNE: f64 = 1.1;
/// A region reaching fewer land cells than this inside its sector gets no representative (the walk
/// still passes through it: edges are measured over every abstract node).
const MIN_CELLS: usize = 100;
/// Edges join nodes whose sectors are at most this many sectors apart (Chebyshev).
const BLOCK: i32 = 2;

fn param<T: std::str::FromStr>(name: &str, def: T) -> T {
	std::env::var(name).ok().and_then(|v| v.parse().ok()).unwrap_or(def)
}

#[derive(Copy, Clone, PartialEq)]
struct Q(f64, u32);
impl Eq for Q {}
impl Ord for Q {
	fn cmp(&self, o: &Self) -> Ordering {
		o.0.partial_cmp(&self.0).unwrap_or(Ordering::Equal).then(o.1.cmp(&self.1))
	}
}
impl PartialOrd for Q {
	fn partial_cmp(&self, o: &Self) -> Option<Ordering> {
		Some(self.cmp(o))
	}
}

struct Place {
	key: String,
	wx: f64,
	wy: f64,
	z: Option<f64>,
}

/// A coarse node: a region's representative or a place, with the abstract nodes it reaches inside
/// its sector (fwd: cost from it; bwd: cost to it).
struct Coarse {
	sid: u32,
	st: St,
	wx: f64,
	wy: f64,
	fwd: Vec<(u32, f64)>,
	bwd: Vec<(u32, f64)>,
	key: Option<String>,
	/// Yards from the place's own point to the cell it snapped to (0 for a representative): added at
	/// both ends of every walk to or from it.
	off: f64,
}

fn places(travel: &Path, map: u32) -> Result<Vec<Place>, String> {
	let rows = |name: &str| -> Result<Vec<Value>, String> {
		let v: Value = serde_json::from_slice(&std::fs::read(travel.join(format!("{name}.json"))).map_err(|e| format!("{name}.json: {e}"))?).map_err(|e| e.to_string())?;
		Ok(v["rows"].as_array().cloned().unwrap_or_default())
	};
	let mut out = Vec::new();
	let on = |p: &Value| p["c"].as_u64() == Some(map as u64);
	let f = |p: &Value, k: &str| p[k].as_f64().unwrap_or(0.0);
	for t in rows("taxi_nodes")? {
		if on(&t) {
			out.push(Place { key: format!("fp:{}", t["id"]), wx: f(&t, "wx"), wy: f(&t, "wy"), z: None });
		}
	}
	for t in rows("transports")? {
		for side in ["a", "b"] {
			let e = &t[side];
			if !on(e) {
				continue;
			}
			// the boarding point when there is one: where the planner and the arrow send you
			let (wx, wy, z) = if e["board"].is_object() {
				(f(&e["board"], "wx"), f(&e["board"], "wy"), e["board"]["z"].as_f64())
			} else {
				(f(e, "wx"), f(e, "wy"), e["z"].as_f64())
			};
			out.push(Place { key: format!("ride:{}:{side}", t["id"].as_str().unwrap_or("?")), wx, wy, z });
		}
	}
	for p in rows("portals")? {
		for side in ["a", "b"] {
			let e = &p[side];
			if on(e) {
				out.push(Place { key: format!("portal:{}:{side}", p["id"].as_str().unwrap_or("?")), wx: f(e, "wx"), wy: f(e, "wy"), z: e["z"].as_f64() });
			}
		}
	}
	for i in rows("inns")? {
		if on(&i) {
			out.push(Place { key: format!("inn:{}", i["npc"]), wx: f(&i, "wx"), wy: f(&i, "wy"), z: None });
		}
	}
	for t in rows("teleports")? {
		let to = &t["to"];
		if to.is_object() && on(to) {
			out.push(Place { key: format!("tele:{}", t["spell"]), wx: f(to, "wx"), wy: f(to, "wy"), z: to["z"].as_f64() });
		}
	}
	Ok(out)
}

fn chebyshev(a: u32, b: u32) -> i32 {
	let (ax, ay) = ((a % hpa::SECTORS_X as u32) as i32, (a / hpa::SECTORS_X as u32) as i32);
	let (bx, by) = ((b % hpa::SECTORS_X as u32) as i32, (b / hpa::SECTORS_X as u32) as i32);
	(ax - bx).abs().max((ay - by).abs())
}

struct Walk<'a> {
	g: &'a Grid,
	ab: &'a Abstract,
	banned: Vec<bool>,
	dist: Vec<f64>,
	touched: Vec<u32>,
}

impl Walk<'_> {
	fn state_of(&self, sid: u32, cell: u16, li: u8) -> St {
		let (ox, oy) = hpa::sector_origin(sid);
		(ox + cell as i32 % SEC, oy + cell as i32 / SEC, li)
	}
	/// Costs from st to its sector's abstract nodes (fwd) and from them to st (bwd), and the two
	/// sector searches (for direct in-sector costs).
	fn seeds(&self, st: St) -> (Vec<(u32, f64)>, Vec<(u32, f64)>, hpa::SectorResult, hpa::SectorResult) {
		let sid = hpa::sid_of(st.0, st.1);
		let f = self.g.sector_search(sid, &[(st, 0.0)], None, false);
		let b = self.g.sector_search(sid, &[(st, 0.0)], None, true);
		let mut fwd = Vec::new();
		let mut bwd = Vec::new();
		if let Some(sg) = self.g.graphs.get(&sid) {
			for &(cell, li, _) in &sg.nodes {
				let s = self.state_of(sid, cell, li);
				let Some(&i) = self.ab.at.get(&s) else { continue };
				if self.banned[i as usize] {
					continue;
				}
				let (cf, cb) = (f.cost(s), b.cost(s));
				if cf.is_finite() {
					fwd.push((i, cf));
				}
				if cb.is_finite() {
					bwd.push((i, cb));
				}
			}
		}
		(fwd, bwd, f, b)
	}
	/// Dijkstra over the abstract graph from seeds, within the sectors `keep` accepts.
	fn run(&mut self, seeds: &[(u32, f64)], keep: impl Fn(u32) -> bool) {
		for &i in &self.touched {
			self.dist[i as usize] = f64::INFINITY;
		}
		self.touched.clear();
		let mut heap = BinaryHeap::new();
		for &(i, c) in seeds {
			if c < self.dist[i as usize] {
				if self.dist[i as usize].is_infinite() {
					self.touched.push(i);
				}
				self.dist[i as usize] = c;
				heap.push(Q(c, i));
			}
		}
		while let Some(Q(d, i)) = heap.pop() {
			if d > self.dist[i as usize] {
				continue;
			}
			for &(j, c, _) in &self.ab.adj[i as usize] {
				if self.banned[j as usize] || !keep(self.ab.nodes[j as usize].0) {
					continue;
				}
				let nd = d + c;
				if nd < self.dist[j as usize] {
					if self.dist[j as usize].is_infinite() {
						self.touched.push(j);
					}
					self.dist[j as usize] = nd;
					heap.push(Q(nd, j));
				}
			}
		}
	}
	fn to(&self, bwd: &[(u32, f64)]) -> f64 {
		bwd.iter().map(|&(i, c)| self.dist[i as usize] + c).fold(f64::INFINITY, f64::min)
	}
}

struct UF(Vec<u32>);
impl UF {
	fn find(&mut self, a: u32) -> u32 {
		let mut a = a;
		while self.0[a as usize] != a {
			self.0[a as usize] = self.0[self.0[a as usize] as usize];
			a = self.0[a as usize];
		}
		a
	}
	fn union(&mut self, a: u32, b: u32) {
		let (a, b) = (self.find(a), self.find(b));
		if a != b {
			self.0[a as usize] = b;
		}
	}
}

/// Greedy spanner over the candidate edges: from the shortest up, an edge (u, v, c) is kept only
/// when the edges kept so far do not already walk from u to v within `t` x c. Keeps every
/// candidate path within `t` and the graph sparse (a few edges per node).
fn spanner(cand: &[FxHashMap<u32, f64>], t: f64) -> Vec<(u32, u32, f64)> {
	let n = cand.len();
	let mut all: Vec<(f64, u32, u32)> = Vec::new();
	for (u, m) in cand.iter().enumerate() {
		for (&v, &c) in m {
			all.push((c, u as u32, v));
		}
	}
	all.sort_by(|a, b| a.0.partial_cmp(&b.0).unwrap().then(a.1.cmp(&b.1)).then(a.2.cmp(&b.2)));
	let mut adj: Vec<Vec<(u32, f64)>> = vec![Vec::new(); n];
	let mut dist = vec![f64::INFINITY; n];
	let mut touched: Vec<u32> = Vec::new();
	let mut out = Vec::new();
	for (c, u, v) in all {
		let limit = c * t;
		for &i in &touched {
			dist[i as usize] = f64::INFINITY;
		}
		touched.clear();
		dist[u as usize] = 0.0;
		touched.push(u);
		let mut heap = BinaryHeap::new();
		heap.push(Q(0.0, u));
		let mut found = false;
		while let Some(Q(d, i)) = heap.pop() {
			if d > dist[i as usize] {
				continue;
			}
			if i == v {
				found = true;
				break;
			}
			for &(j, cj) in &adj[i as usize] {
				let nd = d + cj;
				if nd <= limit && nd < dist[j as usize] {
					if dist[j as usize].is_infinite() {
						touched.push(j);
					}
					dist[j as usize] = nd;
					heap.push(Q(nd, j));
				}
			}
		}
		if !found {
			adj[u as usize].push((v, c));
			out.push((u, v, c));
		}
	}
	out
}

pub fn run(packs: &Path, travel: &Path, out: &Path, grid: Option<&Path>, maps: &[u32]) -> Result<(), String> {
	let build = std::fs::read_to_string(grid.map_or_else(|| packs.join("grid/index.json"), |g| g.join("index.json")))
		.ok()
		.and_then(|s| serde_json::from_str::<Value>(&s).ok())
		.and_then(|v| v["build"].as_str().map(String::from))
		.unwrap_or_else(|| "?".into());
	let tol: f64 = param("WALK_PRUNE", PRUNE);
	let min_cells: usize = param("WALK_MIN_CELLS", MIN_CELLS);
	let reach: i32 = param("WALK_BLOCK", BLOCK);
	for &map in maps {
		let t0 = std::time::Instant::now();
		let mut g = pack::read(packs, map)?;
		// One-way teleporters (Darnassus - Rut'theran) are the planner's portals, not walking.
		g.lifts.retain(|l| !l.oneway);
		let ab = Abstract::build(&g);
		let n = ab.nodes.len();
		let mut w = Walk { g: &g, ab: &ab, banned: vec![false; n], dist: vec![f64::INFINITY; n], touched: Vec::new() };
		eprintln!("walkgraph {map}: {} sectors, {n} abstract nodes ({:.1} s)", g.graphs.len(), t0.elapsed().as_secs_f64());

		// 1. Regions: abstract nodes of a sector joined by an in-sector cost either way.
		let mut uf = UF((0..n as u32).collect());
		let mut base: FxHashMap<u32, u32> = FxHashMap::default();
		for (i, &(sid, _)) in ab.nodes.iter().enumerate() {
			base.entry(sid).or_insert(i as u32);
		}
		for (&sid, sg) in &g.graphs {
			let b = base[&sid];
			let k = sg.nodes.len();
			for i in 0..k {
				for j in 0..k {
					if i != j && sg.cost[i * k + j] != hpa::NO_COST {
						uf.union(b + i as u32, b + j as u32);
					}
				}
			}
		}
		let mut regions: FxHashMap<u32, Vec<u32>> = FxHashMap::default();
		for i in 0..n as u32 {
			let r = uf.find(i);
			regions.entry(r).or_default().push(i);
		}
		let mut rlist: Vec<Vec<u32>> = regions.into_values().collect();
		rlist.sort_by_key(|v| (ab.nodes[v[0] as usize].0, v[0]));

		// 2. A representative per region: the reachable cell nearest the middle of what the region
		//    reaches inside its sector, on land when it has any. Water-only regions are banned.
		let mut coarse: Vec<Coarse> = Vec::new();
		let mut swim_regions = 0usize;
		let mut small = 0usize;
		let mut reps: Vec<(u32, St)> = Vec::new();
				for nodes in &rlist {
			let sid = ab.nodes[nodes[0] as usize].0;
			let src: Vec<(St, f64)> = nodes.iter().map(|&i| (ab.nodes[i as usize].1, 0.0)).collect();
			let r = g.sector_search(sid, &src, None, false);
			let s = &g.sectors[&sid];
			let (ox, oy) = hpa::sector_origin(sid);
			let mut cells: Vec<St> = Vec::new();
			for k in 0..hpa::SCELLS {
				for li in 0..s.count[k] {
					let st = (ox + k as i32 % SEC, oy + k as i32 / SEC, li);
					if r.cost(st).is_finite() && g.class(st) != hpa::CLS_SWIM {
						cells.push(st);
					}
				}
			}
			if cells.len() < min_cells.max(1) {
				if !cells.is_empty() {
					small += 1;
					continue;
				}
				swim_regions += 1;
				for &i in nodes {
					w.banned[i as usize] = true;
				}
				continue;
			}
			let (mx, my) = cells.iter().fold((0.0, 0.0), |a, c| (a.0 + c.0 as f64, a.1 + c.1 as f64));
			let (mx, my) = (mx / cells.len() as f64, my / cells.len() as f64);
			let rep = *cells.iter().min_by(|a, b| {
				let da = (a.0 as f64 - mx).powi(2) + (a.1 as f64 - my).powi(2);
				let db = (b.0 as f64 - mx).powi(2) + (b.1 as f64 - my).powi(2);
				da.partial_cmp(&db).unwrap().then(a.2.cmp(&b.2))
			}).unwrap();
			reps.push((sid, rep));
		}
		for &(sid, st) in &reps {
			let (fwd, bwd, _, _) = w.seeds(st);
			let (wx, wy) = hpa::cell_to_world(st.0 as f64, st.1 as f64);
			coarse.push(Coarse { sid, st, wx, wy, fwd, bwd, key: None, off: 0.0 });
		}
		let nrep = coarse.len();

		// 3. Candidate edges between representatives in touching sectors.
		let mut by_sid: FxHashMap<u32, Vec<u32>> = FxHashMap::default();
		for (i, c) in coarse.iter().enumerate() {
			by_sid.entry(c.sid).or_default().push(i as u32);
		}
		let block = |sid: u32, by_sid: &FxHashMap<u32, Vec<u32>>| -> Vec<u32> {
			let (sx, sy) = ((sid % hpa::SECTORS_X as u32) as i32, (sid / hpa::SECTORS_X as u32) as i32);
			let mut v = Vec::new();
			for dy in -reach..=reach {
				for dx in -reach..=reach {
					let (x, y) = (sx + dx, sy + dy);
					if x < 0 || y < 0 {
						continue;
					}
					if let Some(l) = by_sid.get(&((y * hpa::SECTORS_X + x) as u32)) {
						v.extend_from_slice(l);
					}
				}
			}
			v
		};
		let mut cand: Vec<FxHashMap<u32, f64>> = vec![FxHashMap::default(); nrep];
		for u in 0..nrep {
			let sid = coarse[u].sid;
			let seeds = coarse[u].fwd.clone();
			w.run(&seeds, |s| chebyshev(s, sid) <= reach);
			for v in block(sid, &by_sid) {
				if v as usize == u {
					continue;
				}
				let c = w.to(&coarse[v as usize].bwd);
				if c.is_finite() {
					cand[u].insert(v, c);
				}
			}
		}

		// 4. Components of the abstract graph (undirected, without the water-only regions): a place
		//    without z takes the layer whose walk reaches the biggest one.
		let mut auf = UF((0..n as u32).collect());
		for i in 0..n {
			if w.banned[i] {
				continue;
			}
			for &(j, _, _) in &ab.adj[i] {
				if !w.banned[j as usize] {
					auf.union(i as u32, j);
				}
			}
		}
		let mut acsize: FxHashMap<u32, usize> = FxHashMap::default();
		for i in 0..n as u32 {
			if !w.banned[i as usize] {
				*acsize.entry(auf.find(i)).or_default() += 1;
			}
		}

		// 5. Places, snapped to the grid. Candidates: the nearest cell's layers and, every 3 cells, the
		//    cells around within SNAP (by z when known). Kept: on land, in the biggest component (inside
		//    Ironforge, not on the mountain above), then the one closest to the point plus the cheapest
		//    way out of its sector and back (the street at the inn's door, not a pocket of its floor
		//    the grid closed off, nor an upper floor).
		let plist = places(travel, map)?;
		let mut missing: Vec<String> = Vec::new();
		let mut place_rows: Vec<(String, u32)> = Vec::new();
		for p in &plist {
			let mut cands = g.snap(p.wx, p.wy, p.z, SNAP);
			let (gx, gy) = hpa::world_to_cell(p.wx, p.wy);
			for dy in (-SNAP..=SNAP).step_by(3) {
				for dx in (-SNAP..=SNAP).step_by(3) {
					if dx * dx + dy * dy > SNAP * SNAP {
						continue;
					}
					for li in 0..g.count(gx + dx, gy + dy) {
						let st = (gx + dx, gy + dy, li);
						let z = g.z(st) as f64;
						if let Some(pz) = p.z {
							if z != 0.0 && (z - pz).abs() > 6.0 {
								continue;
							}
						}
						if !cands.contains(&st) {
							cands.push(st);
						}
					}
				}
			}
			let land: Vec<St> = cands.iter().copied().filter(|&s| g.class(s) != hpa::CLS_SWIM).collect();
			if !land.is_empty() {
				cands = land;
			}
			let mut best: Option<(usize, f64, St)> = None;
			for &st in &cands {
				let (fwd, bwd, _, _) = w.seeds(st);
				let size = fwd.iter().chain(bwd.iter()).map(|&(i, _)| acsize[&auf.find(i)]).max().unwrap_or(0);
				if size == 0 {
					continue;
				}
				let out = fwd.iter().map(|x| x.1).fold(f64::INFINITY, f64::min);
				let back = bwd.iter().map(|x| x.1).fold(f64::INFINITY, f64::min);
				let (cx, cy) = hpa::cell_to_world(st.0 as f64, st.1 as f64);
				let score = ((cx - p.wx).powi(2) + (cy - p.wy).powi(2)).sqrt() + out + back;
				if best.is_none_or(|b| size > b.0 || (size == b.0 && score < b.1)) {
					best = Some((size, score, st));
				}
			}
			let Some((_, _, st)) = best else {
				missing.push(p.key.clone());
				continue;
			};
			let (fwd, bwd, _, _) = w.seeds(st);
			let sid = hpa::sid_of(st.0, st.1);
			place_rows.push((p.key.clone(), coarse.len() as u32));
			let (cx, cy) = hpa::cell_to_world(st.0 as f64, st.1 as f64);
			let off = ((cx - p.wx).powi(2) + (cy - p.wy).powi(2)).sqrt();
			coarse.push(Coarse { sid, st, wx: p.wx, wy: p.wy, fwd, bwd, key: Some(p.key.clone()), off });
		}
		cand.resize(coarse.len(), FxHashMap::default());
		// edges place -> representatives (and places) of its block, representatives -> place
		for u in nrep..coarse.len() {
			let sid = coarse[u].sid;
			let st = coarse[u].st;
			let (_, _, fr, br) = w.seeds(st);
			let seeds = coarse[u].fwd.clone();
			w.run(&seeds, |s| chebyshev(s, sid) <= reach);
			let near = block(sid, &by_sid);
			for &v in &near {
				let mut c = w.to(&coarse[v as usize].bwd);
				if coarse[v as usize].sid == sid {
					c = c.min(fr.cost(coarse[v as usize].st));
				}
				if c.is_finite() {
					cand[u].insert(v, c + coarse[u].off);
				}
			}
			for &v in &near {
				let mut back = f64::INFINITY;
				if coarse[v as usize].sid == sid {
					back = br.cost(coarse[v as usize].st);
				}
				// v -> place: v's block walk reaching the place's backward seeds
				let vseeds = coarse[v as usize].fwd.clone();
				let vsid = coarse[v as usize].sid;
				w.run(&vseeds, |s| chebyshev(s, vsid) <= reach);
				back = back.min(w.to(&coarse[u].bwd));
				if back.is_finite() {
					cand[v as usize].insert(u as u32, back + coarse[u].off);
				}
			}
		}

		// 6. Place-to-place matrix over the whole abstract graph (no water-only regions). A place
		//    that walks to no other place and none to it (a landing the grid leaves in a pocket) is
		//    dropped: the planner walks there in a straight line with its penalty.
		let nc = coarse.len();
		let mut raw: Vec<Vec<f64>> = Vec::new();
		for a in nrep..nc {
			let st = coarse[a].st;
			let (_, _, fr, _) = w.seeds(st);
			let seeds = coarse[a].fwd.clone();
			w.run(&seeds, |_| true);
			raw.push((nrep..nc).map(|b| {
				if a == b {
					return 0.0;
				}
				let mut c = w.to(&coarse[b].bwd);
				if coarse[b].sid == coarse[a].sid {
					c = c.min(fr.cost(coarse[b].st));
				}
				c
			}).collect());
		}
		let np = nc - nrep;
		let alive: Vec<bool> = (0..np).map(|i| (0..np).any(|j| j != i && (raw[i][j].is_finite() || raw[j][i].is_finite()))).collect();
		for (i, &ok) in alive.iter().enumerate() {
			if !ok {
				missing.push(format!("{} (isolated)", coarse[nrep + i].key.clone().unwrap()));
			}
		}

		// 7. Keep the components (undirected) that hold a place; prune; renumber by sector.
		let mut kuf = UF((0..nc as u32).collect());
		for (u, m) in cand.iter().enumerate() {
			for &v in m.keys() {
				kuf.union(u as u32, v);
			}
		}
		let placed: FxHashSet<u32> = (nrep..nc).filter(|&u| alive[u - nrep]).map(|u| kuf.find(u as u32)).collect();
		let keep: Vec<bool> = (0..nc).map(|u| placed.contains(&kuf.find(u as u32)) && (u < nrep || alive[u - nrep])).collect();
		for (u, m) in cand.iter_mut().enumerate() {
			if !keep[u] {
				m.clear();
			}
		}
		let edges = spanner(&cand, tol);
		let mut order: Vec<u32> = (0..nc as u32).filter(|&u| keep[u as usize]).collect();
		order.sort_by_key(|&u| (coarse[u as usize].sid, u));
		let mut newid = vec![u32::MAX; nc];
		for (k, &u) in order.iter().enumerate() {
			newid[u as usize] = k as u32;
		}
		let nodes_json: Vec<Value> = order.iter().map(|&u| json!([coarse[u as usize].wx.round() as i64, coarse[u as usize].wy.round() as i64])).collect();
		let mut edges_json: Vec<(u32, u32, i64)> = edges
			.iter()
			.filter(|e| keep[e.0 as usize] && keep[e.1 as usize])
			.map(|&(u, v, c)| (newid[u as usize], newid[v as usize], c.round().max(1.0) as i64))
			.collect();
		edges_json.sort_unstable();
		let mut places_json = serde_json::Map::new();
		let pk: Vec<usize> = (0..np).filter(|&i| alive[i]).collect();
		for &i in &pk {
			places_json.insert(coarse[nrep + i].key.clone().unwrap(), json!(newid[nrep + i]));
		}
		let matrix: Vec<Vec<Value>> = pk.iter().map(|&i| pk.iter().map(|&j| if raw[i][j].is_finite() { json!((raw[i][j] + if i == j { 0.0 } else { coarse[nrep + i].off + coarse[nrep + j].off }).round() as i64) } else { Value::Null }).collect()).collect();
		let keys: Vec<Value> = pk.iter().map(|&i| json!(coarse[nrep + i].key.clone().unwrap())).collect();
		let dropped = nrep - order.iter().filter(|&&u| (u as usize) < nrep).count();
		let doc = json!({
			"meta": {
				"name": "senda-walk",
				"schema": 1,
				"map": map,
				"source": "Senda's navigation packs (nav/, senda-nav bake: the World of Warcraft: Forever client's terrain, WMO and M2 collision through forge-navbuild, GPL-3.0) -> senda-nav walkgraph",
				"client_build": build,
				"units": "nodes [wx, wy] world yards (wx north, wy west), edges [from, to, yards] directed, matrix yards (null: no walk)",
				"counts": {
					"sectors": g.graphs.len(),
					"abstract_nodes": n,
					"regions": rlist.len(),
					"water_regions": swim_regions,
					"small_regions": small,
					"representatives": nrep - dropped,
					"dropped_islands": dropped,
					"places": pk.len(),
					"places_missing": missing,
					"nodes": order.len(),
					"edges": edges_json.len(),
				},
				"prune": tol,
				"min_cells": min_cells,
				"block": reach,
				"snap_cells": SNAP,
			},
			"nodes": nodes_json,
			"edges": edges_json.iter().map(|e| json!([e.0, e.1, e.2])).collect::<Vec<_>>(),
			"places": places_json,
			"matrix": { "keys": keys, "yards": matrix },
		});
		// one row per line: readable diffs, small file
		let mut s = String::from("{\n");
		s.push_str(&format!(" \"meta\": {},\n", serde_json::to_string(&doc["meta"]).unwrap()));
		let arr = |name: &str, v: &Value, last: bool| -> String {
			let items: Vec<String> = v.as_array().unwrap().iter().map(|x| serde_json::to_string(x).unwrap()).collect();
			format!(" \"{name}\": [\n  {}\n ]{}\n", items.join(",\n  "), if last { "" } else { "," })
		};
		s.push_str(&arr("nodes", &doc["nodes"], false));
		s.push_str(&arr("edges", &doc["edges"], false));
		s.push_str(&format!(" \"places\": {},\n", serde_json::to_string(&doc["places"]).unwrap()));
		s.push_str(&format!(" \"matrix\": {{\n  \"keys\": {},\n  \"yards\": [\n   {}\n  ]\n }}\n}}\n",
			serde_json::to_string(&doc["matrix"]["keys"]).unwrap(),
			doc["matrix"]["yards"].as_array().unwrap().iter().map(|r| serde_json::to_string(r).unwrap()).collect::<Vec<_>>().join(",\n   ")));
		std::fs::write(out.join(format!("walk_{map}.json")), s).map_err(|e| e.to_string())?;
		eprintln!(
			"walkgraph {map}: {} regions ({swim_regions} water), {} nodes, {} edges, {} places ({} missing: {:?}), {dropped} island representatives dropped, {:.1} s",
			rlist.len(), order.len(), edges_json.len(), pk.len(), missing.len(), missing, t0.elapsed().as_secs_f64()
		);
	}
	Ok(())
}

/// Debug: per world point of a dump file (lines "<tag> wx wy ..."), the terrain chunk's area and
/// the fine surfaces (z/flags/slope) of its column.  senda-nav zprof --grid DIR --map 0 --file F
pub fn zprof(grid: &Path, map: u32, file: &Path) -> Result<(), String> {
	use forge_navbuild::format;
	let names: Value = serde_json::from_slice(&std::fs::read(grid.join("areas.json")).map_err(|e| e.to_string())?).map_err(|e| e.to_string())?;
	let text = std::fs::read_to_string(file).map_err(|e| e.to_string())?;
	let mut cache: FxHashMap<(i32, i32), format::Tile> = FxHashMap::default();
	for line in text.lines() {
		let p: Vec<&str> = line.split_whitespace().collect();
		if p.len() < 3 {
			continue;
		}
		let (Ok(wx), Ok(wy)) = (p[1].parse::<f64>(), p[2].parse::<f64>()) else { continue };
		let (col, row, i, j) = format::cell_of(wx, wy);
		if let std::collections::hash_map::Entry::Vacant(e) = cache.entry((col, row)) {
			let b = std::fs::read(grid.join(format!("tiles/{map}/{col}_{row}.nav.gz"))).map_err(|e| e.to_string())?;
			e.insert(format::decode_tile(&b)?);
		}
		let t = &cache[&(col, row)];
		let k = (j * 256 + i) as usize;
		let area = t.areas[((j / 16) * 16 + i / 16) as usize];
		let zs: Vec<String> = (t.first[k]..t.first[k + 1]).map(|e| format!("{:.0}/{:x}/{}", t.z[e as usize], t.flags[e as usize], t.slope[e as usize])).collect();
		println!("{wx:.0} {wy:.0} area {area} {} | {}", names[area.to_string()][0].as_str().unwrap_or("?"), zs.join(" "));
	}
	Ok(())
}
