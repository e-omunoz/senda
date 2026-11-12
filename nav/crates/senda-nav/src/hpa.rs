//! The coarse walk grid, its HPA* abstraction and the queries (the same algorithm the in-game Lua
//! router runs; docs/NAV.md). Copyright (C) 2026 Senda contributors. GPL-3.0-only.
//!
//! Cells: 128 per ADT tile (4.17 yd), global (gx east, gy south):
//!   gx = floor((32 * ADT - wy) / CELL), gy = floor((32 * ADT - wx) / CELL)
//! Sectors: 64 x 64 cells (a quarter of a tile), id sy * 128 + sx.
//! Each cell holds 0-7 layers (separate floors); a layer links in each of 8 directions to one
//! layer of the neighbouring cell (or none).

use rustc_hash::FxHashMap;
use std::cmp::Ordering;
use std::collections::BinaryHeap;

pub const ADT: f64 = 1600.0 / 3.0;
pub const CELL: f64 = ADT / 128.0;
pub const SEC: i32 = 64;
pub const SCELLS: usize = (SEC * SEC) as usize;
pub const SECTORS_X: i32 = 128;
/// "No group" in the bake's per-entry arrays.
pub const NONE: u8 = 255;
pub const MAX_LAYERS: usize = 7;
/// E, SE, S, SW, W, NW, N, NE (x east, y south): forge-navbuild's DIRS.
pub const DIRS: [(i32, i32); 8] = [(1, 0), (1, 1), (0, 1), (-1, 1), (-1, 0), (-1, -1), (0, -1), (1, -1)];
/// Classes: 0 walk, 1 swim, 2 indoor.
pub const CLS_WALK: u8 = 0;
pub const CLS_SWIM: u8 = 1;
pub const CLS_INDOOR: u8 = 2;
pub const SWIM_MULT: f64 = 3.0;
/// A lift ride's cost in yards (25 s at run speed 7 yd/s, Polestar's figure).
pub const LIFT_COST: f64 = 175.0;
/// Intra-sector costs are stored in whole yards.
pub const COST_UNIT: f64 = 1.0;
pub const NO_COST: u16 = 0xffff;

pub fn dir_len(d: usize) -> f64 {
	if d & 1 == 1 {
		CELL * std::f64::consts::SQRT_2
	} else {
		CELL
	}
}

pub fn mult(class: u8) -> f64 {
	if class == CLS_SWIM {
		SWIM_MULT
	} else {
		1.0
	}
}

pub fn world_to_cell(wx: f64, wy: f64) -> (i32, i32) {
	(((32.0 * ADT - wy) / CELL).floor() as i32, ((32.0 * ADT - wx) / CELL).floor() as i32)
}

pub fn cell_to_world(gx: f64, gy: f64) -> (f64, f64) {
	(32.0 * ADT - (gy + 0.5) * CELL, 32.0 * ADT - (gx + 0.5) * CELL)
}

pub fn sid_of(gx: i32, gy: i32) -> u32 {
	((gy >> 6) * SECTORS_X + (gx >> 6)) as u32
}

pub fn local_of(gx: i32, gy: i32) -> usize {
	((gy & 63) * SEC + (gx & 63)) as usize
}

pub fn sector_origin(sid: u32) -> (i32, i32) {
	((sid as i32 % SECTORS_X) * SEC, (sid as i32 / SECTORS_X) * SEC)
}

/// One sector's cells.
#[derive(Clone, Debug, Default)]
pub struct Sector {
	pub count: Vec<u8>,
	/// First layer ordinal of each cell (SCELLS + 1).
	pub first: Vec<u16>,
	/// Per layer ordinal and direction: the bitmask of the neighbouring cell's layers it links to
	/// (bit li; 0: no link).
	pub links: Vec<[u8; 8]>,
	pub class: Vec<u8>,
	/// Per layer ordinal its height (yards; the pack keeps it only where a cell has 2+ layers).
	pub z: Vec<f32>,
}

impl Sector {
	pub fn from_counts(count: Vec<u8>) -> Sector {
		let mut first = vec![0u16; SCELLS + 1];
		for k in 0..SCELLS {
			first[k + 1] = first[k] + count[k] as u16;
		}
		let n = first[SCELLS] as usize;
		Sector { count, first, links: vec![[0u8; 8]; n], class: vec![0; n], z: vec![0.0; n] }
	}
	pub fn layers(&self) -> usize {
		self.first[SCELLS] as usize
	}
}

/// A sector's abstract graph: its nodes (cell, layer, crossing mask) and the costs between them.
#[derive(Clone, Debug, Default)]
pub struct SectorGraph {
	pub nodes: Vec<(u16, u8, u8)>,
	/// n * n, row = from, yards, NO_COST when unreachable inside the sector.
	pub cost: Vec<u16>,
	/// Per node: its component in the continent's abstract graph (undirected): two ends whose
	/// sectors share no component are unreachable without a search.
	pub comp: Vec<u16>,
	/// Crossings out of the sector: (from node, direction, node index in the neighbouring
	/// sector that way, cost in tenths of a yard).
	pub cross: Vec<(u8, u8, u8, u8)>,
}

#[derive(Clone, Debug)]
pub struct Lift {
	pub a: (i32, i32, u8),
	pub b: (i32, i32, u8),
	pub cost: f64,
	pub name: String,
	/// A teleporter: a -> b only.
	pub oneway: bool,
}

#[derive(Default)]
pub struct Grid {
	pub map: u32,
	pub sectors: FxHashMap<u32, Sector>,
	pub graphs: FxHashMap<u32, SectorGraph>,
	pub lifts: Vec<Lift>,
}

/// A state: global cell and layer index in that cell.
pub type St = (i32, i32, u8);

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

pub fn octile(ax: i32, ay: i32, bx: i32, by: i32) -> f64 {
	let dx = (ax - bx).abs() as f64;
	let dy = (ay - by).abs() as f64;
	(dx.max(dy) - dx.min(dy) + dx.min(dy) * std::f64::consts::SQRT_2) * CELL
}

impl Grid {
	pub fn sector(&self, gx: i32, gy: i32) -> Option<&Sector> {
		if gx < 0 || gy < 0 || gx >= SEC * SECTORS_X || gy >= SEC * SECTORS_X {
			return None;
		}
		self.sectors.get(&sid_of(gx, gy))
	}
	pub fn count(&self, gx: i32, gy: i32) -> u8 {
		self.sector(gx, gy).map_or(0, |s| s.count[local_of(gx, gy)])
	}
	fn ord(&self, s: &Sector, gx: i32, gy: i32, li: u8) -> usize {
		s.first[local_of(gx, gy)] as usize + li as usize
	}
	/// The layers of the neighbouring cell in direction d that st links to (bitmask).
	pub fn mask(&self, st: St, d: usize) -> u8 {
		let Some(s) = self.sector(st.0, st.1) else { return 0 };
		let m = s.links[self.ord(s, st.0, st.1, st.2)][d];
		if m == 0 {
			return 0;
		}
		let n = self.count(st.0 + DIRS[d].0, st.1 + DIRS[d].1);
		m & ((1u16 << n) - 1) as u8
	}
	/// The states a move from st in direction d lands on.
	pub fn steps(&self, st: St, d: usize) -> impl Iterator<Item = St> {
		let m = self.mask(st, d);
		let (nx, ny) = (st.0 + DIRS[d].0, st.1 + DIRS[d].1);
		(0..7u8).filter(move |li| m & (1 << li) != 0).map(move |li| (nx, ny, li))
	}
	pub fn has_step(&self, a: St, d: usize, b: St) -> bool {
		(a.0 + DIRS[d].0, a.1 + DIRS[d].1) == (b.0, b.1) && self.mask(a, d) & (1 << b.2) != 0
	}
	pub fn class(&self, st: St) -> u8 {
		self.sector(st.0, st.1).map_or(0, |s| s.class[self.ord(s, st.0, st.1, st.2)])
	}
	pub fn z(&self, st: St) -> f32 {
		self.sector(st.0, st.1).map_or(0.0, |s| s.z[self.ord(s, st.0, st.1, st.2)])
	}
	pub fn move_cost(&self, to: St, d: usize) -> f64 {
		dir_len(d) * mult(self.class(to))
	}
	/// Predecessors of st: states with a link into it.
	pub fn preds(&self, st: St, out: &mut Vec<(St, usize)>) {
		out.clear();
		for d in 0..8 {
			let (px, py) = (st.0 - DIRS[d].0, st.1 - DIRS[d].1);
			for li in 0..self.count(px, py) {
				if self.has_step((px, py, li), d, st) {
					out.push(((px, py, li), d));
				}
			}
		}
	}

	/// The nearest walkable cell to a world point (within `r` cells), its layer chosen by z when
	/// given, else the lowest-cost choice is left to the caller: returns every layer.
	pub fn snap(&self, wx: f64, wy: f64, z: Option<f64>, r: i32) -> Vec<St> {
		let (gx, gy) = world_to_cell(wx, wy);
		for ring in 0..=r {
			let mut best: Vec<(f64, i32, i32)> = Vec::new();
			for dy in -ring..=ring {
				for dx in -ring..=ring {
					if dx.abs().max(dy.abs()) != ring {
						continue;
					}
					if self.count(gx + dx, gy + dy) > 0 {
						best.push(((dx * dx + dy * dy) as f64, gx + dx, gy + dy));
					}
				}
			}
			if let Some(&(_, x, y)) = best.iter().min_by(|a, b| a.0.partial_cmp(&b.0).unwrap()) {
				let n = self.count(x, y);
				if let (Some(z), true) = (z, n > 1) {
					let li = (0..n).min_by(|&a, &b| (self.z((x, y, a)) as f64 - z).abs().partial_cmp(&(self.z((x, y, b)) as f64 - z).abs()).unwrap()).unwrap();
					return vec![(x, y, li)];
				}
				return (0..n).map(|li| (x, y, li)).collect();
			}
		}
		Vec::new()
	}

	/// Dijkstra / A* restricted to one sector (`sid`), from sources (with initial costs), forward
	/// or backward. Stops when `goal` is settled (A* with octile heuristic) or the sector is
	/// exhausted. Returns the settled costs and parents, and the expansions.
	pub fn sector_search(&self, sid: u32, sources: &[(St, f64)], goal: Option<St>, reverse: bool) -> SectorResult {
		let s = &self.sectors[&sid];
		let (ox, oy) = sector_origin(sid);
		let n = s.layers();
		let mut dist = vec![f64::INFINITY; n];
		let mut parent = vec![u32::MAX; n];
		let mut heap = BinaryHeap::new();
		let idx = |st: St| -> usize { s.first[local_of(st.0, st.1)] as usize + st.2 as usize };
		let h = |st: St| -> f64 { goal.map_or(0.0, |g| octile(st.0, st.1, g.0, g.1)) };
		for &(st, c) in sources {
			if sid_of(st.0, st.1) != sid {
				continue;
			}
			let i = idx(st);
			if c < dist[i] {
				dist[i] = c;
				heap.push(Q(c + h(st), i as u32));
			}
		}
		// ordinal -> state
		let state = |i: usize| -> St {
			let k = match s.first.binary_search(&(i as u16)) {
				Ok(mut k) => {
					while s.first[k + 1] as usize == i {
						k += 1;
					}
					k
				}
				Err(k) => k - 1,
			};
			(ox + (k as i32 % SEC), oy + (k as i32 / SEC), (i - s.first[k] as usize) as u8)
		};
		let mut done = vec![false; n];
		let mut exp = 0usize;
		let mut preds = Vec::new();
		let goal_i = goal.filter(|g| sid_of(g.0, g.1) == sid).map(idx);
		while let Some(Q(_, i)) = heap.pop() {
			let i = i as usize;
			if done[i] {
				continue;
			}
			done[i] = true;
			exp += 1;
			if Some(i) == goal_i {
				break;
			}
			let st = state(i);
			if !reverse {
				for d in 0..8 {
					for t in self.steps(st, d) {
						if sid_of(t.0, t.1) != sid {
							continue;
						}
						let j = idx(t);
						let c = dist[i] + self.move_cost(t, d);
						if c < dist[j] {
							dist[j] = c;
							parent[j] = i as u32;
							heap.push(Q(c + h(t), j as u32));
						}
					}
				}
			} else {
				self.preds(st, &mut preds);
				for &(p, d) in &preds {
					if sid_of(p.0, p.1) != sid {
						continue;
					}
					let j = idx(p);
					let c = dist[i] + self.move_cost(st, d);
					if c < dist[j] {
						dist[j] = c;
						parent[j] = i as u32;
						heap.push(Q(c + h(p), j as u32));
					}
				}
			}
		}
		SectorResult { sid, dist, parent, exp, first: s.first.clone(), origin: (ox, oy) }
	}
}

pub struct SectorResult {
	pub sid: u32,
	pub dist: Vec<f64>,
	pub parent: Vec<u32>,
	pub exp: usize,
	first: Vec<u16>,
	origin: (i32, i32),
}

impl SectorResult {
	pub fn idx(&self, st: St) -> usize {
		self.first[local_of(st.0, st.1)] as usize + st.2 as usize
	}
	pub fn cost(&self, st: St) -> f64 {
		if sid_of(st.0, st.1) != self.sid {
			return f64::INFINITY;
		}
		self.dist[self.idx(st)]
	}
	fn state(&self, i: usize) -> St {
		let k = match self.first.binary_search(&(i as u16)) {
			Ok(mut k) => {
				while self.first[k + 1] as usize == i {
					k += 1;
				}
				k
			}
			Err(k) => k - 1,
		};
		(self.origin.0 + (k as i32 % SEC), self.origin.1 + (k as i32 / SEC), (i - self.first[k] as usize) as u8)
	}
	/// The parent chain from st back to a source (forward search: goal -> source order).
	pub fn chain(&self, st: St) -> Vec<St> {
		let mut out = vec![st];
		let mut i = self.idx(st);
		while self.parent[i] != u32::MAX {
			i = self.parent[i] as usize;
			out.push(self.state(i));
		}
		out
	}
}

/// The abstract graph of a whole continent (built from the per-sector graphs, as the Lua does at
/// load).
pub struct Abstract {
	pub nodes: Vec<(u32, St)>,
	pub at: FxHashMap<St, u32>,
	/// Adjacency: (to, cost yards, kind 0 intra, 1 cross, 2 lift).
	pub adj: Vec<Vec<(u32, f64, u8)>>,
	pub comp: Vec<u16>,
}

impl Abstract {
	pub fn build(g: &Grid) -> Abstract {
		let mut nodes = Vec::new();
		let mut comp = Vec::new();
		let mut at = FxHashMap::default();
		let mut base: FxHashMap<u32, u32> = FxHashMap::default();
		let mut sids: Vec<u32> = g.graphs.keys().copied().collect();
		sids.sort_unstable();
		for &sid in &sids {
			let sg = &g.graphs[&sid];
			let (ox, oy) = sector_origin(sid);
			base.insert(sid, nodes.len() as u32);
			for (k, &(cell, li, _)) in sg.nodes.iter().enumerate() {
				let st = (ox + cell as i32 % SEC, oy + cell as i32 / SEC, li);
				at.insert(st, nodes.len() as u32);
				nodes.push((sid, st));
				comp.push(sg.comp.get(k).copied().unwrap_or(0));
			}
		}
		let mut adj = vec![Vec::new(); nodes.len()];
		for &sid in &sids {
			let sg = &g.graphs[&sid];
			let b = base[&sid] as usize;
			let n = sg.nodes.len();
			for i in 0..n {
				for j in 0..n {
					let c = sg.cost[i * n + j];
					if i != j && c != NO_COST {
						adj[b + i].push(((b + j) as u32, c as f64 * COST_UNIT, 0));
					}
				}
			}
			for &(i, d, j, c) in &sg.cross {
				let st = nodes[b + i as usize].1;
				let (nx, ny) = (st.0 + DIRS[d as usize].0, st.1 + DIRS[d as usize].1);
				let sid2 = sid_of(nx, ny);
				if let Some(&b2) = base.get(&sid2) {
					adj[b + i as usize].push((b2 + j as u32, c as f64 * 0.1, 1));
				}
			}
		}
		for l in &g.lifts {
			if let (Some(&a), Some(&b)) = (at.get(&l.a), at.get(&l.b)) {
				adj[a as usize].push((b, l.cost, 2));
				if !l.oneway {
					adj[b as usize].push((a, l.cost, 2));
				}
			}
		}
		Abstract { nodes, at, adj, comp }
	}
}

#[derive(Default, Debug, Clone)]
pub struct QueryStats {
	pub exp_cells: usize,
	pub exp_abstract: usize,
	pub sectors_touched: usize,
	pub micros_abstract: u128,
	pub micros_total: u128,
}

pub struct Route {
	pub states: Vec<St>,
	/// Indices in `states` after which a lift ride follows.
	pub lifts: Vec<usize>,
	pub cost: f64,
}

/// A full query: connect the ends inside their sectors, A* on the abstract graph, refine every
/// abstract hop with a sector A*. (The Lua router refines lazily near the player.)
pub fn query(g: &Grid, ab: &Abstract, starts: &[St], goals: &[St], stats: &mut QueryStats) -> Option<Route> {
	let t0 = std::time::Instant::now();
	let ssid = sid_of(starts[0].0, starts[0].1);
	let gsid = sid_of(goals[0].0, goals[0].1);
	let src: Vec<(St, f64)> = starts.iter().map(|&s| (s, 0.0)).collect();
	let fwd = g.sector_search(ssid, &src, None, false);
	let gsrc: Vec<(St, f64)> = goals.iter().map(|&s| (s, 0.0)).collect();
	let bwd = g.sector_search(gsid, &gsrc, None, true);
	stats.exp_cells += fwd.exp + bwd.exp;
	// Direct inside one sector.
	let mut direct: Option<(f64, St)> = None;
	if ssid == gsid {
		for &gl in goals {
			let c = fwd.cost(gl);
			if c.is_finite() && direct.is_none_or(|d| c < d.0) {
				direct = Some((c, gl));
			}
		}
	}
	// Abstract A*: virtual start S (index n) and goal T (n + 1).
	let n = ab.nodes.len();
	let (gx, gy) = (goals[0].0, goals[0].1);
	let h = |i: usize| -> f64 { if i >= n { 0.0 } else { let st = ab.nodes[i].1; octile(st.0, st.1, gx, gy) } };
	let mut dist: FxHashMap<usize, f64> = FxHashMap::default();
	let mut par: FxHashMap<usize, usize> = FxHashMap::default();
	let mut heap = BinaryHeap::new();
	let ta = std::time::Instant::now();
	let sg_start = &g.graphs.get(&ssid);
	let goal_cost: FxHashMap<usize, f64> = match g.graphs.get(&gsid) {
		Some(sg) => {
			let (ox, oy) = sector_origin(gsid);
			sg.nodes.iter().filter_map(|&(cell, li, _)| {
				let st = (ox + cell as i32 % SEC, oy + cell as i32 / SEC, li);
				let c = bwd.cost(st);
				if c.is_finite() { ab.at.get(&st).map(|&i| (i as usize, c)) } else { None }
			}).collect()
		}
		None => FxHashMap::default(),
	};
	if let Some(sg) = sg_start {
		let (ox, oy) = sector_origin(ssid);
		for &(cell, li, _) in &sg.nodes {
			let st = (ox + cell as i32 % SEC, oy + cell as i32 / SEC, li);
			let c = fwd.cost(st);
			if c.is_finite() {
				if let Some(&i) = ab.at.get(&st) {
					let i = i as usize;
					if c < *dist.get(&i).unwrap_or(&f64::INFINITY) {
						dist.insert(i, c);
						par.insert(i, n);
						heap.push(Q(c + h(i), i as u32));
					}
				}
			}
		}
	}
	// No shared component: unreachable without searching.
	let goal_comps: rustc_hash::FxHashSet<u16> = goal_cost.keys().map(|&i| ab.comp[i]).collect();
	if direct.is_none() && !dist.keys().any(|&i| goal_comps.contains(&ab.comp[i])) {
		stats.micros_total += t0.elapsed().as_micros();
		return None;
	}
	let mut best_t = direct.map_or(f64::INFINITY, |d| d.0);
	let mut t_par: Option<usize> = None;
	let mut closed = rustc_hash::FxHashSet::default();
	while let Some(Q(f, i)) = heap.pop() {
		let i = i as usize;
		if f >= best_t {
			break;
		}
		if !closed.insert(i) {
			continue;
		}
		stats.exp_abstract += 1;
		let di = dist[&i];
		if let Some(&gc) = goal_cost.get(&i) {
			if di + gc < best_t {
				best_t = di + gc;
				t_par = Some(i);
			}
		}
		for &(j, c, _) in &ab.adj[i] {
			let j = j as usize;
			let nd = di + c;
			if nd < *dist.get(&j).unwrap_or(&f64::INFINITY) {
				dist.insert(j, nd);
				par.insert(j, i);
				heap.push(Q(nd + h(j), j as u32));
			}
		}
	}
	stats.micros_abstract += ta.elapsed().as_micros();
	if !best_t.is_finite() {
		stats.micros_total += t0.elapsed().as_micros();
		return None;
	}
	// Refine.
	let mut states: Vec<St> = Vec::new();
	let mut lifts = Vec::new();
	let mut touched = rustc_hash::FxHashSet::default();
	touched.insert(ssid);
	touched.insert(gsid);
	match t_par {
		None => {
			let (_, gl) = direct.unwrap();
			let mut c = fwd.chain(gl);
			c.reverse();
			states = c;
		}
		Some(last) => {
			let mut hops = vec![last];
			let mut k = last;
			while let Some(&p) = par.get(&k) {
				if p == n {
					break;
				}
				hops.push(p);
				k = p;
			}
			hops.reverse();
			let mut c = fwd.chain(ab.nodes[hops[0]].1);
			c.reverse();
			states.extend(c);
			for w in hops.windows(2) {
				let (a, b) = (ab.nodes[w[0]], ab.nodes[w[1]]);
				let kind = ab.adj[w[0]].iter().filter(|e| e.0 as usize == w[1]).map(|e| e.2).min().unwrap_or(0);
				if kind == 2 {
					lifts.push(states.len() - 1);
					states.push(b.1);
				} else if kind == 1 && a.0 != b.0 {
					states.push(b.1);
				} else {
					touched.insert(a.0);
					let r = g.sector_search(a.0, &[(a.1, 0.0)], Some(b.1), false);
					stats.exp_cells += r.exp;
					let mut c = r.chain(b.1);
					c.reverse();
					states.extend(c.into_iter().skip(1));
				}
			}
			// last node -> goal: the backward tree's chain
			let mut i = bwd.chain(ab.nodes[last].1);
			i.remove(0);
			states.extend(i);
		}
	}
	stats.sectors_touched = touched.len();
	stats.micros_total += t0.elapsed().as_micros();
	Some(Route { states, lifts, cost: best_t })
}

/// Whether a straight walk from a to b (cell centres) follows links all the way, landing on b's
/// layer; the DDA visits every cell the segment crosses (a corner crossing is a diagonal step).
pub fn sight(g: &Grid, a: St, b: St) -> bool {
	trace(g, a, (b.0, b.1)) & (1 << b.2) != 0
}

/// Walk the DDA from state a towards cell (bx, by), carrying the set of layers the walk can be
/// on: the set reached there (bitmask; 0 when some step has no link).
pub fn trace(g: &Grid, a: St, b: (i32, i32)) -> u8 {
	let (mut x, mut y) = (a.0, a.1);
	let mut cur: u8 = 1 << a.2;
	let dx = b.0 - a.0;
	let dy = b.1 - a.1;
	let (sx, sy) = (dx.signum(), dy.signum());
	let (ax, ay) = (dx.abs() as i64, dy.abs() as i64);
	// Crossings of x lines at t = (2i+1)/(2ax), of y lines at (2j+1)/(2ay): compare (2i+1)ay, (2j+1)ax.
	let (mut i, mut j) = (0i64, 0i64);
	while i < ax || j < ay {
		let tx = (2 * i + 1) * ay;
		let ty = (2 * j + 1) * ax;
		let (mx, my) = if i >= ax {
			(0, sy)
		} else if j >= ay {
			(sx, 0)
		} else if tx < ty {
			(sx, 0)
		} else if ty < tx {
			(0, sy)
		} else {
			(sx, sy)
		};
		if mx != 0 {
			i += 1;
		}
		if my != 0 {
			j += 1;
		}
		let d = DIRS.iter().position(|&v| v == (mx, my)).unwrap();
		let mut next = 0u8;
		for li in 0..7u8 {
			if cur & (1 << li) != 0 {
				next |= g.mask((x, y, li), d);
			}
		}
		if next == 0 {
			return 0;
		}
		cur = next;
		x += mx;
		y += my;
	}
	cur
}
/// String pulling: from each anchor, the farthest state in sight (checked up to `look` states
/// ahead), never across a lift. Returns the kept states.
pub fn smooth(g: &Grid, r: &Route, look: usize) -> Vec<St> {
	let s = &r.states;
	if s.len() < 3 {
		return s.clone();
	}
	let mut out = vec![s[0]];
	let mut i = 0;
	while i < s.len() - 1 {
		let lift_after = r.lifts.iter().copied().filter(|&l| l >= i).min();
		let stop = lift_after.map_or(s.len() - 1, |l| l);
		if stop == i {
			// ride: jump to the other landing
			out.push(s[i + 1]);
			i += 1;
			continue;
		}
		let mut best = i + 1;
		let hi = stop.min(i + look);
		// farthest visible, scanning back from hi
		let mut j = hi;
		while j > i + 1 {
			if sight(g, s[i], s[j]) {
				best = j;
				break;
			}
			j -= 1;
		}
		out.push(s[best]);
		i = best;
	}
	out
}
