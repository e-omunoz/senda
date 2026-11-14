//! Fine grid (forge-navbuild tiles: 256 columns a tile, many surfaces a column) -> Senda's coarse
//! layered grid (128 cells a tile) -> HPA* sector graphs -> Lua packs.
//! Copyright (C) 2026 Senda contributors. GPL-3.0-only.
//!
//! 1. Reachable surfaces: union-find over every walkable entry (not BLOCKED, with links, not
//!    terrain buried under an indoor WMO floor) joined by
//!    its neighbour links and the lifts; components smaller than KEEP entries (rooftops, ledges,
//!    pockets inside rocks and walls) are dropped, unless a lift lands on them.
//! 2. Coarse layers: in each 2 x 2 block of fine columns the kept entries joined by links inside
//!    the block form one layer; at most 7 layers (the largest) a cell.
//! 3. Coarse links: a fine link leaving the block in some direction links its layer to the
//!    target's layer in that neighbouring cell (every layer met: a bitmask per direction).
//! 4. Class: swim when every entry is SWIM, indoor when any is INDOOR, else walk; z: mean height.

use crate::hpa::{self, Grid, Lift, Sector, CELL, DIRS, MAX_LAYERS, NONE, SCELLS, SEC};
use crate::pack;
use forge_navbuild::format::{self, flag, Tile, NO_LINK, TILE_CELLS};
use rayon::prelude::*;
use rustc_hash::FxHashMap;
use serde_json::Value;
use std::path::Path;

/// Fine link classes (forge_navbuild::format::cls) the bake ignores, as a bitmask: 0 for the
/// shipped packs (every link); the travel planner's walk graph bakes with `--skip climb` (no
/// climbing up rock faces over STEEP_MAX: a runner cannot walk the Dun Morogh - Wetlands ridge).
static SKIP: std::sync::atomic::AtomicU8 = std::sync::atomic::AtomicU8::new(0);

/// Sets the skipped link classes from names (`climb`, `steep`, `jump`, ...).
pub fn set_skip(names: &str) -> Result<(), String> {
	let mut m = 0u8;
	for n in names.split(',').map(str::trim).filter(|n| !n.is_empty()) {
		let i = format::CLS_NAMES.iter().position(|&x| x == n).ok_or(format!("bake: unknown link class {n}"))?;
		m |= 1 << i;
	}
	SKIP.store(m, std::sync::atomic::Ordering::Relaxed);
	Ok(())
}

/// A stored link byte the bake follows: a link whose class is not skipped. LINK_SLOPE (7, a
/// walkable slope) is never skipped.
fn usable(b: u8) -> bool {
	b != NO_LINK && (b >> 5 == format::LINK_SLOPE || SKIP.load(std::sync::atomic::Ordering::Relaxed) & (1 << (b >> 5)) == 0)
}

/// Ground the bake leaves out (`--block FILE`, only for the travel planner's walk graph): per
/// continent, polygons in world yards (wx, wy) and the height above which a surface inside them
/// is dropped (with `outdoor`, never an indoor WMO floor: a city's halls under the mountain). Reviewed by hand (docs/TRAVEL.md, «Andar»).
pub struct Block {
	pub poly: Vec<(f64, f64)>,
	pub zmin: f32,
	pub outdoor: bool,
}

static BLOCKS: std::sync::OnceLock<FxHashMap<u32, Vec<Block>>> = std::sync::OnceLock::new();

/// Reads the blocked ground (nav/data/walk_blocks.json).
pub fn set_blocks(p: Option<&Path>) -> Result<(), String> {
	let mut m: FxHashMap<u32, Vec<Block>> = FxHashMap::default();
	if let Some(p) = p {
		let v: Value = serde_json::from_slice(&std::fs::read(p).map_err(|e| format!("{}: {e}", p.display()))?).map_err(|e| e.to_string())?;
		for b in v["blocks"].as_array().into_iter().flatten() {
			let poly: Vec<(f64, f64)> = b["poly"].as_array().into_iter().flatten().filter_map(|q| Some((q[0].as_f64()?, q[1].as_f64()?))).collect();
			if poly.len() < 3 {
				return Err(format!("bake: block {} needs a polygon", b["id"]));
			}
			let map = b["map"].as_u64().ok_or("bake: block without map")? as u32;
			eprintln!("bake: block {} on map {map} above z {}", b["id"].as_str().unwrap_or("?"), b["zmin"]);
			m.entry(map).or_default().push(Block { poly, zmin: b["zmin"].as_f64().unwrap_or(-1e9) as f32, outdoor: b["outdoor"].as_bool().unwrap_or(false) });
		}
	}
	let _ = BLOCKS.set(m);
	Ok(())
}

fn inside(poly: &[(f64, f64)], x: f64, y: f64) -> bool {
	let mut c = false;
	let mut j = poly.len() - 1;
	for i in 0..poly.len() {
		let (xi, yi) = poly[i];
		let (xj, yj) = poly[j];
		if (yi > y) != (yj > y) && x < (xj - xi) * (y - yi) / (yj - yi) + xi {
			c = !c;
		}
		j = i;
	}
	c
}

/// Whether the entry at height z of fine column (i, j) of tile (col, row) lies on blocked ground.
fn blocked(c: u32, col: i32, row: i32, i: i32, j: i32, z: f32, flags: u8) -> bool {
	let Some(list) = BLOCKS.get().and_then(|m| m.get(&c)) else { return false };
	let (wx, wy) = format::cell_centre(col, row, i, j);
	list.iter().any(|b| z > b.zmin && !(b.outdoor && flags & flag::INDOOR != 0) && inside(&b.poly, wx, wy))
}

/// Components under this many fine entries (2.08 x 2.08 yd each: ~17,000 yd², a 130-yd square)
/// are not reachable ground.
pub const KEEP: u32 = 4000;

thread_local! {
	static REF: std::cell::RefCell<Option<Vec<u8>>> = const { std::cell::RefCell::new(None) };
}

struct UF(Vec<u32>);
impl UF {
	fn find(&mut self, mut x: u32) -> u32 {
		while self.0[x as usize] != x {
			let p = self.0[x as usize];
			self.0[x as usize] = self.0[p as usize];
			x = p;
		}
		x
	}
	fn union(&mut self, a: u32, b: u32) {
		let (ra, rb) = (self.find(a), self.find(b));
		if ra != rb {
			if ra < rb {
				self.0[rb as usize] = ra;
			} else {
				self.0[ra as usize] = rb;
			}
		}
	}
}

fn load(grid: &Path, c: u32, key: &str) -> Result<Tile, String> {
	let p = grid.join(format!("tiles/{c}/{key}.nav.gz"));
	let b = std::fs::read(&p).map_err(|e| format!("{}: {e}", p.display()))?;
	format::decode_tile(&b)
}

pub struct Fine {
	pub tiles: Vec<(i32, i32)>,
	pub index: FxHashMap<(i32, i32), usize>,
	pub base: Vec<u32>,
	pub first: Vec<Vec<u32>>,
}

impl Fine {
	/// Global entry of (tile col, row, column k, layer).
	fn entry(&self, col: i32, row: i32, k: usize, layer: u32) -> Option<u32> {
		let t = *self.index.get(&(col, row))?;
		let f = &self.first[t];
		if layer >= f[k + 1] - f[k] {
			return None;
		}
		Some(self.base[t] + f[k] + layer)
	}
	/// The target of a link from column (i, j) of tile t in direction d with stored byte b.
	fn target(&self, t: usize, i: i32, j: i32, d: usize, b: u8) -> Option<(usize, i32, i32, u32)> {
		let tc = TILE_CELLS as i32;
		let (col, row) = self.tiles[t];
		let (mut ni, mut nj, mut c2, mut r2) = (i + DIRS[d].0, j + DIRS[d].1, col, row);
		if ni < 0 {
			ni += tc;
			c2 -= 1;
		} else if ni >= tc {
			ni -= tc;
			c2 += 1;
		}
		if nj < 0 {
			nj += tc;
			r2 -= 1;
		} else if nj >= tc {
			nj -= tc;
			r2 += 1;
		}
		let k2 = (nj * tc + ni) as usize;
		let e = self.entry(c2, r2, k2, u32::from(b & 31))?;
		Some((self.index[&(c2, r2)], c2 * tc + ni, r2 * tc + nj, e))
	}
}

fn walkable(t: &Tile, e: usize) -> bool {
	t.flags[e] & flag::BLOCKED == 0 && t.links.as_ref().is_some_and(|l| l[e * 8..e * 8 + 8].iter().any(|&b| usable(b)))
}

/// The highest walkable indoor WMO surface of column k (an indoor floor, a city's streets).
fn indoor_top(t: &Tile, k: usize) -> f32 {
	let both = flag::WMO | flag::INDOOR;
	(t.first[k] as usize..t.first[k + 1] as usize).filter(|&e| t.flags[e] & both == both && walkable(t, e)).map(|e| t.z[e]).fold(f32::NEG_INFINITY, f32::max)
}

/// Terrain under an indoor WMO floor (the ground buried under Stormwind's streets, under a
/// house's floor): never walked, though the grid can reach it from the open ground around.
fn buried(t: &Tile, e: usize, indoor_top: f32) -> bool {
	t.flags[e] & flag::TERRAIN != 0 && t.flags[e] & flag::WMO == 0 && t.z[e] < indoor_top - 2.0
}

/// Per coarse block of a tile: layers (class, z, count).
struct TileCoarse {
	/// 128 x 128 counts.
	count: Vec<u8>,
	first: Vec<u32>,
	class: Vec<u8>,
	z: Vec<f32>,
	links: Vec<[u8; 8]>,
}

pub fn run(grid: &Path, out: &Path, continents: &[u32], teleports: Option<&Path>) -> Result<(), String> {
	let tele: Value = match teleports {
		Some(p) => serde_json::from_slice(&std::fs::read(p).map_err(|e| format!("{}: {e}", p.display()))?).map_err(|e| e.to_string())?,
		None => Value::Null,
	};
	let index: Value = serde_json::from_slice(&std::fs::read(grid.join("index.json")).map_err(|e| e.to_string())?).map_err(|e| e.to_string())?;
	let lifts_json: Value = serde_json::from_slice(&std::fs::read(grid.join("lifts.json")).map_err(|e| e.to_string())?).map_err(|e| e.to_string())?;
	std::fs::create_dir_all(out).map_err(|e| e.to_string())?;
	for &c in continents {
		let t0 = std::time::Instant::now();
		let keys: Vec<String> = index["continents"][c.to_string()]["tiles"].as_array().ok_or(format!("continent {c} not in grid"))?.iter().filter_map(|v| v.as_str().map(String::from)).collect();
		let g = bake_continent(grid, c, &keys, &lifts_json[c.to_string()])?;
		eprintln!("bake {c}: coarse grid {} sectors in {:.1} s", g.sectors.len(), t0.elapsed().as_secs_f64());
		let mut g = g;
		for t in tele["teleports"].as_array().into_iter().flatten().filter(|t| t["map"].as_u64() == Some(c as u64)) {
			let p = |k: &str| -> Option<hpa::St> {
				let v = t[k].as_array()?;
				let (x, y, z) = (v[0].as_f64()?, v[1].as_f64()?, v[2].as_f64());
				g.snap(x, y, z, 4).first().copied()
			};
			match (p("a"), p("b")) {
				(Some(a), Some(b)) => g.lifts.push(Lift { a, b, cost: t["seconds"].as_f64().unwrap_or(5.0) * 7.0, name: t["name"].as_str().unwrap_or("").into(), oneway: true }),
				_ => eprintln!("bake {c}: teleport {} has an end off the grid", t["id"]),
			}
		}
		build_graphs(&mut g);
		components(&mut g);
		eprintln!("bake {c}: graphs in {:.1} s", t0.elapsed().as_secs_f64());
		pack::write(&g, out)?;
		if let Some(raw) = REF.with(|r| r.borrow_mut().take()) {
			let dir = out.join("ref");
			std::fs::create_dir_all(&dir).map_err(|e| e.to_string())?;
			std::fs::write(dir.join(format!("{c}.bin.gz")), format::gzip(&raw)).map_err(|e| e.to_string())?;
		}
		eprintln!("bake {c}: packed in {:.1} s", t0.elapsed().as_secs_f64());
	}
	Ok(())
}

fn bake_continent(grid: &Path, c: u32, keys: &[String], lifts: &Value) -> Result<Grid, String> {
	let tiles: Vec<(i32, i32)> = keys.iter().map(|k| {
		let mut p = k.split('_').map(|x| x.parse::<i32>().unwrap());
		(p.next().unwrap(), p.next().unwrap())
	}).collect();
	let index: FxHashMap<(i32, i32), usize> = tiles.iter().enumerate().map(|(i, &t)| (t, i)).collect();
	// Pass 1: firsts.
	let firsts: Vec<Result<Vec<u32>, String>> = keys.par_iter().map(|k| load(grid, c, k).map(|t| t.first)).collect();
	let mut first = Vec::new();
	let mut base = Vec::new();
	let mut total = 0u32;
	for f in firsts {
		let f = f?;
		base.push(total);
		total += f[f.len() - 1];
		first.push(f);
	}
	let fine = Fine { tiles: tiles.clone(), index, base, first };
	eprintln!("bake {c}: {} tiles, {total} entries", tiles.len());
	// Pass 2: union-find on links (in chunks: decode in parallel, union in order).
	let mut uf = UF((0..total).collect());
	let mut walk = vec![false; total as usize];
	for chunk in (0..tiles.len()).collect::<Vec<_>>().chunks(64) {
		let pairs: Vec<Result<(usize, Vec<u32>, Vec<(u32, u32)>), String>> = chunk.par_iter().map(|&t| {
			let tile = load(grid, c, &keys[t])?;
			let links = tile.links.as_ref().ok_or("unlinked tile")?;
			let mut ws = Vec::new();
			let mut ps = Vec::new();
			for k in 0..format::COLUMNS {
				let (i, j) = ((k % TILE_CELLS) as i32, (k / TILE_CELLS) as i32);
				let top = indoor_top(&tile, k);
				let (col, row) = fine.tiles[t];
				for e in tile.first[k] as usize..tile.first[k + 1] as usize {
					if !walkable(&tile, e) || buried(&tile, e, top) || blocked(c, col, row, i, j, tile.z[e], tile.flags[e]) {
						continue;
					}
					let ge = fine.base[t] + e as u32;
					ws.push(ge);
					for d in 0..8 {
						let b = links[e * 8 + d];
						if !usable(b) {
							continue;
						}
						if let Some((_, _, _, te)) = fine.target(t, i, j, d, b) {
							ps.push((ge, te));
						}
					}
				}
			}
			Ok((t, ws, ps))
		}).collect();
		for r in pairs {
			let (_, ws, ps) = r?;
			for w in ws {
				walk[w as usize] = true;
			}
			for (a, b) in ps {
				uf.union(a, b);
			}
		}
	}
	// Lifts join their landings.
	let mut lift_list = Vec::new();
	for l in lifts.as_array().into_iter().flatten() {
		let end = |v: &Value| -> Option<u32> {
			let (col, row) = (v["col"].as_i64()? as i32, v["row"].as_i64()? as i32);
			let t = *fine.index.get(&(col, row))?;
			Some(fine.base[t] + v["entry"].as_u64()? as u32)
		};
		if let (Some(a), Some(b)) = (end(&l["a"]), end(&l["b"])) {
			uf.union(a, b);
			lift_list.push((a, b, l["name"].as_str().unwrap_or("").to_string()));
		}
	}
	let mut size: FxHashMap<u32, u32> = FxHashMap::default();
	for e in 0..total {
		if walk[e as usize] {
			*size.entry(uf.find(e)).or_default() += 1;
		}
	}
	let mut lift_roots = rustc_hash::FxHashSet::default();
	for (a, _, _) in &lift_list {
		lift_roots.insert(uf.find(*a));
	}
	let kept_roots: rustc_hash::FxHashSet<u32> = size.iter().filter(|(r, &n)| n >= KEEP || lift_roots.contains(r)).map(|(&r, _)| r).collect();
	let mut keep = vec![false; total as usize];
	let mut kept = 0usize;
	for e in 0..total {
		if walk[e as usize] && kept_roots.contains(&uf.find(e)) {
			keep[e as usize] = true;
			kept += 1;
		}
	}
	// Reference walkability (any kept surface in a fine column), for the evaluator only: never shipped.
	{
		let mut raw: Vec<u8> = Vec::with_capacity(tiles.len() * (4 + 8192));
		for (t, &(col, row)) in tiles.iter().enumerate() {
			raw.extend_from_slice(&(col as u16).to_le_bytes());
			raw.extend_from_slice(&(row as u16).to_le_bytes());
			let mut bits = vec![0u8; 8192];
			for k in 0..format::COLUMNS {
				let f = &fine.first[t];
				if (f[k]..f[k + 1]).any(|e| keep[(fine.base[t] + e) as usize]) {
					bits[k >> 3] |= 1 << (k & 7);
				}
			}
			raw.extend_from_slice(&bits);
		}
		REF.with(|r| *r.borrow_mut() = Some(raw));
	}
	let mut big: Vec<u32> = size.values().copied().collect();
	big.sort_unstable_by(|a, b| b.cmp(a));
	eprintln!("bake {c}: {} walkable components, {} kept ({kept} entries); largest {:?}", size.len(), kept_roots.len(), &big[..big.len().min(6)]);
	drop(uf);
	drop(walk);
	// Pass 3: coarse layers per tile (group of every kept entry).
	let mut group = vec![NONE; total as usize];
	let coarse: Vec<Result<(TileCoarse, Vec<u8>), String>> = (0..tiles.len()).into_par_iter().map(|t| {
		let tile = load(grid, c, &keys[t])?;
		let links = tile.links.as_ref().unwrap();
		let b0 = fine.base[t] as usize;
		let mut grp = vec![NONE; tile.n];
		let mut count = vec![0u8; 128 * 128];
		let mut class = Vec::new();
		let mut zs = Vec::new();
		for bj in 0..128usize {
			for bi in 0..128usize {
				// entries of the block
				let mut es: Vec<(usize, usize)> = Vec::new(); // (entry, column)
				for (di, dj) in [(0, 0), (1, 0), (0, 1), (1, 1)] {
					let k = (2 * bj + dj) * TILE_CELLS + 2 * bi + di;
					for e in tile.first[k] as usize..tile.first[k + 1] as usize {
						if keep[b0 + e] {
							es.push((e, k));
						}
					}
				}
				if es.is_empty() {
					continue;
				}
				// local union over links staying in the block
				let mut p: Vec<usize> = (0..es.len()).collect();
				fn f(p: &mut [usize], mut x: usize) -> usize {
					while p[x] != x {
						p[x] = p[p[x]];
						x = p[x];
					}
					x
				}
				let pos: FxHashMap<usize, usize> = es.iter().enumerate().map(|(n, &(e, _))| (e, n)).collect();
				for (n, &(e, k)) in es.iter().enumerate() {
					let (i, j) = ((k % TILE_CELLS) as i32, (k / TILE_CELLS) as i32);
					for d in 0..8 {
						let b = links[e * 8 + d];
						if !usable(b) {
							continue;
						}
						let (ni, nj) = (i + DIRS[d].0, j + DIRS[d].1);
						if ni < 0 || nj < 0 || ni >= TILE_CELLS as i32 || nj >= TILE_CELLS as i32 || (ni as usize) / 2 != bi || (nj as usize) / 2 != bj {
							continue;
						}
						let k2 = nj as usize * TILE_CELLS + ni as usize;
						let e2 = tile.first[k2] as usize + (b & 31) as usize;
						if let Some(&m) = pos.get(&e2) {
							let (ra, rb) = (f(&mut p, n), f(&mut p, m));
							if ra != rb {
								p[ra.max(rb)] = ra.min(rb);
							}
						}
					}
				}
				let mut groups: Vec<(usize, Vec<usize>)> = Vec::new();
				for n in 0..es.len() {
					let r = f(&mut p, n);
					match groups.iter_mut().find(|g| g.0 == r) {
						Some(g) => g.1.push(n),
						None => groups.push((r, vec![n])),
					}
				}
				groups.sort_by(|a, b| b.1.len().cmp(&a.1.len()));
				groups.truncate(MAX_LAYERS);
				// order layers by height (lowest first) so layer 0 is the ground floor
				let mut lz: Vec<(f32, Vec<usize>)> = groups.into_iter().map(|(_, m)| (m.iter().map(|&n| tile.z[es[n].0]).sum::<f32>() / m.len() as f32, m)).collect();
				lz.sort_by(|a, b| a.0.partial_cmp(&b.0).unwrap());
				count[bj * 128 + bi] = lz.len() as u8;
				for (li, (z, m)) in lz.iter().enumerate() {
					let mut all_swim = true;
					let mut indoor = false;
					for &n in m {
						let fl = tile.flags[es[n].0];
						all_swim &= fl & flag::SWIM != 0;
						indoor |= fl & flag::INDOOR != 0;
						grp[es[n].0] = li as u8;
					}
					class.push(if all_swim { hpa::CLS_SWIM } else if indoor { hpa::CLS_INDOOR } else { hpa::CLS_WALK });
					zs.push(*z);
				}
			}
		}
		let mut firstc = vec![0u32; 128 * 128 + 1];
		for k in 0..128 * 128 {
			firstc[k + 1] = firstc[k] + count[k] as u32;
		}
		let n = firstc[128 * 128] as usize;
		Ok((TileCoarse { count, first: firstc, class, z: zs, links: vec![[0u8; 8]; n] }, grp))
	}).collect();
	let mut tc_list = Vec::new();
	for (t, r) in coarse.into_iter().enumerate() {
		let (tcz, grp) = r?;
		let b0 = fine.base[t] as usize;
		group[b0..b0 + grp.len()].copy_from_slice(&grp);
		tc_list.push(tcz);
	}
	// Pass 4: coarse links.
	let linked: Vec<Result<Vec<[u8; 8]>, String>> = (0..tiles.len()).into_par_iter().map(|t| {
		let tile = load(grid, c, &keys[t])?;
		let links = tile.links.as_ref().unwrap();
		let b0 = fine.base[t] as usize;
		let tcz = &tc_list[t];
		let mut out = tcz.links.clone();
		let (col, row) = tiles[t];
		for k in 0..format::COLUMNS {
			let (i, j) = ((k % TILE_CELLS) as i32, (k / TILE_CELLS) as i32);
			let (gi, gj) = (col * 256 + i, row * 256 + j);
			let blk = ((j / 2) * 128 + i / 2) as usize;
			for e in tile.first[k] as usize..tile.first[k + 1] as usize {
				let a = group[b0 + e];
				if a == NONE {
					continue;
				}
				let ord = tcz.first[blk] as usize + a as usize;
				for d in 0..8 {
					let b = links[e * 8 + d];
					if !usable(b) {
						continue;
					}
					let Some((_, ti, tj, te)) = fine.target(t, i, j, d, b) else { continue };
					let g2 = group[te as usize];
					if g2 == NONE {
						continue;
					}
					let (cdx, cdy) = ((ti >> 1) - (gi >> 1), (tj >> 1) - (gj >> 1));
					if cdx == 0 && cdy == 0 {
						continue;
					}
					let cd = DIRS.iter().position(|&v| v == (cdx, cdy)).unwrap();
					out[ord][cd] |= 1 << g2;
				}
			}
		}
		Ok(out)
	}).collect();
	for (t, r) in linked.into_iter().enumerate() {
		tc_list[t].links = r?;
	}
	// Sectors: each tile is 2 x 2 sectors.
	let mut g = Grid { map: c, ..Default::default() };
	for (t, &(col, row)) in tiles.iter().enumerate() {
		let tcz = &tc_list[t];
		for qy in 0..2 {
			for qx in 0..2 {
				let (sx, sy) = (col * 2 + qx, row * 2 + qy);
				let mut count = vec![0u8; SCELLS];
				for ly in 0..SEC as usize {
					for lx in 0..SEC as usize {
						count[ly * SEC as usize + lx] = tcz.count[(qy as usize * 64 + ly) * 128 + qx as usize * 64 + lx];
					}
				}
				if count.iter().all(|&n| n == 0) {
					continue;
				}
				let mut s = Sector::from_counts(count);
				for ly in 0..SEC as usize {
					for lx in 0..SEC as usize {
						let blk = (qy as usize * 64 + ly) * 128 + qx as usize * 64 + lx;
						let k = ly * SEC as usize + lx;
						for li in 0..s.count[k] as usize {
							let o = s.first[k] as usize + li;
							let src = tcz.first[blk] as usize + li;
							s.links[o] = tcz.links[src];
							s.class[o] = tcz.class[src];
							s.z[o] = tcz.z[src];
						}
					}
				}
				g.sectors.insert((sy * hpa::SECTORS_X + sx) as u32, s);
			}
		}
	}
	// Lifts on the coarse grid.
	for (a, b, name) in lift_list {
		let end = |e: u32| -> Option<hpa::St> {
			let t = fine.base.partition_point(|&x| x <= e) - 1;
			let (col, row) = tiles[t];
			let le = e - fine.base[t];
			let f = &fine.first[t];
			let k = f.partition_point(|&x| x <= le) - 1;
			let (i, j) = ((k % TILE_CELLS) as i32, (k / TILE_CELLS) as i32);
			let li = group[e as usize];
			if li == NONE {
				return None;
			}
			Some(((col * 256 + i) >> 1, (row * 256 + j) >> 1, li))
		};
		if let (Some(sa), Some(sb)) = (end(a), end(b)) {
			g.lifts.push(Lift { a: sa, b: sb, cost: hpa::LIFT_COST, name, oneway: false });
		}
	}
	let _ = CELL;
	Ok(g)
}

/// HPA* entrances per sector side, nodes, and the intra-sector cost matrices.
pub fn build_graphs(g: &mut Grid) {
	// crossings: (from state, dir, to state) whose ends lie in different sectors
	let mut nodes: FxHashMap<u32, FxHashMap<(u16, u8), u8>> = FxHashMap::default();
	let sids: Vec<u32> = g.sectors.keys().copied().collect();
	let add = |nodes: &mut FxHashMap<u32, FxHashMap<(u16, u8), u8>>, st: hpa::St, mask: u8| {
		let sid = hpa::sid_of(st.0, st.1);
		*nodes.entry(sid).or_default().entry((hpa::local_of(st.0, st.1) as u16, st.2)).or_default() |= mask;
	};
	for &sid in &sids {
		let (ox, oy) = hpa::sector_origin(sid);
		// Per side (E, S, W, N: dirs 0, 2, 4, 6), runs along the border of crossing positions.
		for side in [0usize, 2, 4, 6] {
			let (sx, sy) = (ox / SEC + DIRS[side].0, oy / SEC + DIRS[side].1);
			if sx < 0 || sy < 0 {
				continue;
			}
			let across = (sy * hpa::SECTORS_X + sx) as u32;
			let mut runs: Vec<Vec<(hpa::St, usize, hpa::St)>> = Vec::new();
			let mut cur: Vec<Vec<(hpa::St, usize, hpa::St)>> = vec![Vec::new(); MAX_LAYERS];
			for p in 0..=SEC {
				let (x, y) = match side {
					0 => (ox + SEC - 1, oy + p),
					2 => (ox + p, oy + SEC - 1),
					4 => (ox, oy + p),
					_ => (ox + p, oy),
				};
				for li in 0..MAX_LAYERS as u8 {
					let mut found = None;
					if p < SEC && li < g.count(x, y) {
						// the orthogonal crossing first, then the diagonals through this side
						for d in [side, (side + 1) % 8, (side + 7) % 8] {
							for t in g.steps((x, y, li), d) {
								if found.is_none() && hpa::sid_of(t.0, t.1) == across {
									found = Some(((x, y, li), d, t));
								}
							}
						}
					}
					// a run goes on only along one floor: the previous crossing's cell links to this one
					if let (Some(f), Some(prev)) = (found, cur[li as usize].last()) {
						let along = if side == 0 || side == 4 { 2 } else { 0 };
						let (a, b) = (prev.0, f.0);
						if !g.has_step(a, along, b) && !g.has_step(b, (along + 4) % 8, a) {
							runs.push(std::mem::take(&mut cur[li as usize]));
						}
					}
					match found {
						Some(f) => cur[li as usize].push(f),
						None => {
							if !cur[li as usize].is_empty() {
								runs.push(std::mem::take(&mut cur[li as usize]));
							}
						}
					}
				}
			}
			for r in runs {
				// one entrance a short run, two (at a quarter from each end) up to 48 cells, else three
				let n = r.len();
				let picks: Vec<usize> = if n <= 16 {
					vec![n / 2]
				} else if n <= 48 {
					vec![n / 4, n - 1 - n / 4]
				} else {
					vec![n / 6, n / 2, n - 1 - n / 6]
				};
				for p in picks {
					let (a, d, b) = r[p];
					add(&mut nodes, a, 1 << d);
					add(&mut nodes, b, 0);
					// and the way back when it exists
					let back = (d + 4) % 8;
					if g.has_step(b, back, a) {
						add(&mut nodes, b, 1 << back);
					}
				}
			}
		}
	}
	for l in g.lifts.clone() {
		add(&mut nodes, l.a, 0);
		add(&mut nodes, l.b, 0);
	}
	// Intra-sector costs.
	let list: Vec<(u32, Vec<((u16, u8), u8)>)> = nodes.into_iter().map(|(sid, m)| {
		let mut v: Vec<((u16, u8), u8)> = m.into_iter().collect();
		v.sort_unstable();
		v.truncate(255);
		(sid, v)
	}).collect();
	let gr = &*g;
	let graphs: Vec<(u32, hpa::SectorGraph)> = list.par_iter().map(|(sid, v)| {
		let (ox, oy) = hpa::sector_origin(*sid);
		let st = |&((cell, li), _): &((u16, u8), u8)| (ox + cell as i32 % SEC, oy + cell as i32 / SEC, li);
		let n = v.len();
		let mut cost = vec![hpa::NO_COST; n * n];
		for i in 0..n {
			let r = gr.sector_search(*sid, &[(st(&v[i]), 0.0)], None, false);
			for j in 0..n {
				let c = r.cost(st(&v[j]));
				if c.is_finite() {
					cost[i * n + j] = ((c / hpa::COST_UNIT).round() as u64).min(hpa::NO_COST as u64 - 1) as u16;
				}
			}
		}
		(*sid, hpa::SectorGraph { nodes: v.iter().map(|&((c, l), m)| (c, l, m)).collect(), cost, comp: vec![0; n], cross: Vec::new() })
	}).collect();
	g.graphs = graphs.into_iter().collect();
	// crossings, by node index in the neighbouring sector
	let mut idx: FxHashMap<hpa::St, u8> = FxHashMap::default();
	for (&sid, sg) in &g.graphs {
		let (ox, oy) = hpa::sector_origin(sid);
		for (k, &(c, li, _)) in sg.nodes.iter().enumerate() {
			idx.insert((ox + c as i32 % SEC, oy + c as i32 / SEC, li), k as u8);
		}
	}
	let sids: Vec<u32> = g.graphs.keys().copied().collect();
	for sid in sids {
		let (ox, oy) = hpa::sector_origin(sid);
		let mut cross = Vec::new();
		for (k, &(c, li, mask)) in g.graphs[&sid].nodes.iter().enumerate() {
			let st = (ox + c as i32 % SEC, oy + c as i32 / SEC, li);
			for d in 0..8 {
				if mask & (1 << d) == 0 {
					continue;
				}
				for t in g.steps(st, d) {
					if hpa::sid_of(t.0, t.1) != sid {
						if let Some(&j) = idx.get(&t) {
							let cost = (g.move_cost(t, d) * 10.0).round().min(255.0) as u8;
							cross.push((k as u8, d as u8, j, cost));
						}
					}
				}
			}
		}
		g.graphs.get_mut(&sid).unwrap().cross = cross;
	}
	let nn: usize = g.graphs.values().map(|s| s.nodes.len()).sum();
	eprintln!("bake {}: {} sector graphs, {nn} nodes, {} lifts", g.map, g.graphs.len(), g.lifts.len());
}

/// Undirected components of the abstract graph, stored per node.
pub fn components(g: &mut Grid) {
	let ab = hpa::Abstract::build(g);
	let n = ab.nodes.len();
	let mut uf = UF((0..n as u32).collect());
	for (i, adj) in ab.adj.iter().enumerate() {
		for &(j, _, _) in adj {
			uf.union(i as u32, j);
		}
	}
	let mut ids: FxHashMap<u32, u16> = FxHashMap::default();
	let mut comp = vec![0u16; n];
	for i in 0..n {
		let r = uf.find(i as u32);
		let k = ids.len();
		comp[i] = *ids.entry(r).or_insert(k.min(65535) as u16);
	}
	for (i, &(sid, st)) in ab.nodes.iter().enumerate() {
		let sg = g.graphs.get_mut(&sid).unwrap();
		let k = sg.nodes.iter().position(|&(c, li, _)| c as usize == hpa::local_of(st.0, st.1) && li == st.2).unwrap();
		sg.comp[k] = comp[i];
	}
	eprintln!("bake {}: {} abstract components", g.map, ids.len());
}
