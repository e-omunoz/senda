//! The route evaluator: loads the shipped packs (nav/out/SendaNav_<map>_*.lua), runs every route
//! of nav/eval/routes.json through the HPA* query and writes nav/eval/report.md.
//! Copyright (C) 2026 Senda contributors. GPL-3.0-only.
//!
//! Per route: found or not; the smoothed line's length against the straight line; segments of
//! the line that leave the coarse grid's links (must be 0) and samples (every yard) over fine
//! columns with no reachable surface in the reference grid (nav/out/ref, never shipped); the
//! abstract search's and the whole query's time and their expansions.

use crate::coords::Frames;
use crate::hpa::{self, Abstract, QueryStats};
use crate::pack;
use rustc_hash::FxHashMap;
use serde_json::Value;
use std::fmt::Write as _;
use std::path::{Path, PathBuf};

const FINE: f64 = hpa::ADT / 256.0;

struct Ref(FxHashMap<(i32, i32), Vec<u8>>);
impl Ref {
	fn load(p: &Path) -> Option<Ref> {
		let raw = forge_navbuild::format::gunzip(&std::fs::read(p).ok()?).ok()?;
		let mut m = FxHashMap::default();
		for c in raw.chunks(4 + 8192) {
			m.insert((u16::from_le_bytes([c[0], c[1]]) as i32, u16::from_le_bytes([c[2], c[3]]) as i32), c[4..].to_vec());
		}
		Some(Ref(m))
	}
	fn walk(&self, wx: f64, wy: f64) -> bool {
		let gi = ((32.0 * hpa::ADT - wy) / FINE).floor() as i32;
		let gj = ((32.0 * hpa::ADT - wx) / FINE).floor() as i32;
		let (col, row) = (gi.div_euclid(256), gj.div_euclid(256));
		let k = (gj.rem_euclid(256) * 256 + gi.rem_euclid(256)) as usize;
		self.0.get(&(col, row)).is_some_and(|b| b[k >> 3] & (1 << (k & 7)) != 0)
	}
}

struct Row {
	id: String,
	kind: String,
	map: u32,
	found: String,
	yards: f64,
	straight: f64,
	cross: usize,
	fine_off: usize,
	samples: usize,
	stats: QueryStats,
	lifts: usize,
	cost: f64,
}

pub fn run(packs: &Path, frames_dir: &Path, routes: &Path, report: &Path, _grid: Option<PathBuf>) -> Result<(), String> {
	let frames = Frames::load(&frames_dir.join("ui_map.jsonl"))?;
	let doc: Value = serde_json::from_slice(&std::fs::read(routes).map_err(|e| e.to_string())?).map_err(|e| e.to_string())?;
	let list = doc["routes"].as_array().ok_or("routes.json: no routes")?;
	let mut grids: FxHashMap<u32, (hpa::Grid, Abstract, Option<Ref>, f64)> = FxHashMap::default();
	let mut rows = Vec::new();
	for r in list {
		let id = r["id"].as_str().unwrap_or("?").to_string();
		let end = |v: &Value| -> Option<(u32, f64, f64, Option<f64>)> {
			let (m, wx, wy) = frames.to_world(v["uiMap"].as_u64()? as u32, v["x"].as_f64()?, v["y"].as_f64()?)?;
			Some((m, wx, wy, v["z"].as_f64()))
		};
		let (Some(a), Some(b)) = (end(&r["from"]), end(&r["to"])) else {
			eprintln!("{id}: an end has no frame");
			continue;
		};
		if !grids.contains_key(&a.0) {
			let t = std::time::Instant::now();
			let g = pack::read(packs, a.0)?;
			let tl = t.elapsed().as_secs_f64();
			let t = std::time::Instant::now();
			let ab = Abstract::build(&g);
			eprintln!("eval: map {} loaded in {tl:.1} s, abstract graph {} nodes in {:.2} s", a.0, ab.nodes.len(), t.elapsed().as_secs_f64());
			let rf = Ref::load(&packs.join(format!("ref/{}.bin.gz", a.0)));
			grids.insert(a.0, (g, ab, rf, t.elapsed().as_secs_f64()));
		}
		let (g, ab, rf, _) = &grids[&a.0];
		let mut row = Row { id: id.clone(), kind: r["kind"].as_str().unwrap_or("").into(), map: a.0, found: String::new(), yards: 0.0, straight: (a.1 - b.1).hypot(a.2 - b.2), cross: 0, fine_off: 0, samples: 0, stats: QueryStats::default(), lifts: 0, cost: 0.0 };
		let s = g.snap(a.1, a.2, a.3, 8);
		let t = g.snap(b.1, b.2, b.3, 8);
		if s.is_empty() || t.is_empty() {
			row.found = if s.is_empty() { "start off mesh".into() } else { "goal off mesh".into() };
			rows.push(row);
			continue;
		}
		match hpa::query(g, ab, &s, &t, &mut row.stats) {
			None => row.found = "no".into(),
			Some(route) => {
				row.found = "yes".into();
				row.cost = route.cost;
				row.lifts = route.lifts.len();
				let line = hpa::smooth(g, &route, 400);
				if std::env::var("SENDA_DUMP").ok().as_deref() == Some(id.as_str()) {
					for st in &line {
						let (wx, wy) = hpa::cell_to_world(st.0 as f64, st.1 as f64);
						let ui = r["from"]["uiMap"].as_u64().unwrap_or(0) as u32;
						let p = frames.to_percent(ui, wx, wy).unwrap_or((0.0, 0.0));
						println!("dump {wx:.1} {wy:.1} z{:.0} L{} cls{} | {ui} {:.2},{:.2}", g.z(*st), st.2, g.class(*st), p.0, p.1);
					}
				}
				// lift hops: consecutive kept states that are a lift's two landings
				let is_lift = |p: &hpa::St, q: &hpa::St| g.lifts.iter().any(|l| (l.a == *p && l.b == *q) || (l.b == *p && l.a == *q));
				for w in line.windows(2) {
					if is_lift(&w[0], &w[1]) {
						continue;
					}
					if !hpa::sight(g, w[0], w[1]) {
						row.cross += 1;
					}
					let (x0, y0) = hpa::cell_to_world(w[0].0 as f64, w[0].1 as f64);
					let (x1, y1) = hpa::cell_to_world(w[1].0 as f64, w[1].1 as f64);
					let len = (x1 - x0).hypot(y1 - y0);
					row.yards += len;
					if let Some(rf) = rf {
						let n = len.ceil().max(1.0) as usize;
						for k in 0..=n {
							let f = k as f64 / n as f64;
							row.samples += 1;
							if !rf.walk(x0 + (x1 - x0) * f, y0 + (y1 - y0) * f) {
								row.fine_off += 1;
							}
						}
					}
				}
			}
		}
		eprintln!("{id}: {} {:.0} yd (straight {:.0}), cross {}, fine off {}/{}, {} us", row.found, row.yards, row.straight, row.cross, row.fine_off, row.samples, row.stats.micros_total);
		rows.push(row);
	}
	write_report(packs, report, &rows)
}

fn write_report(packs: &Path, report: &Path, rows: &[Row]) -> Result<(), String> {
	let mut s = String::new();
	let found = rows.iter().filter(|r| r.found == "yes").count();
	let cross: usize = rows.iter().map(|r| r.cross).sum();
	let mut ta: Vec<u128> = rows.iter().filter(|r| r.found == "yes").map(|r| r.stats.micros_abstract).collect();
	let mut tt: Vec<u128> = rows.iter().filter(|r| r.found == "yes").map(|r| r.stats.micros_total).collect();
	ta.sort_unstable();
	tt.sort_unstable();
	let med = |v: &[u128]| v.get(v.len() / 2).copied().unwrap_or(0);
	let max = |v: &[u128]| v.last().copied().unwrap_or(0);
	let mut ea: Vec<usize> = rows.iter().map(|r| r.stats.exp_abstract).collect();
	let mut ec: Vec<usize> = rows.iter().map(|r| r.stats.exp_cells).collect();
	ea.sort_unstable();
	ec.sort_unstable();
	let _ = writeln!(s, "# Senda navigation: route evaluation\n");
	let _ = writeln!(s, "Generated by `senda-nav eval` (nav/, docs/NAV.md) over `nav/eval/routes.json` against the packs in `nav/out`.\n");
	let _ = writeln!(s, "## Summary\n");
	let _ = writeln!(s, "- Routes: {}; found: {found}; not found or off the mesh: {}.", rows.len(), rows.len() - found);
	let _ = writeln!(s, "- Line segments leaving the coarse grid's links: **{cross}** (must be 0).");
	let fo: usize = rows.iter().map(|r| r.fine_off).sum();
	let fs: usize = rows.iter().map(|r| r.samples).sum();
	let _ = writeln!(s, "- One-yard samples of the drawn lines over fine columns with no reachable surface (reference grid, not shipped): {fo} of {fs} ({:.2} %).", 100.0 * fo as f64 / fs.max(1) as f64);
	let _ = writeln!(s, "- Abstract search (Rust, release, one thread): median {} us, max {} us. Whole query with full refinement: median {} us, max {} us.", med(&ta), max(&ta), med(&tt), max(&tt));
	let _ = writeln!(s, "- Expansions, abstract graph: median {}, max {}; cells (end connections + refinement of every hop): median {}, max {}.", ea.get(ea.len() / 2).unwrap_or(&0), ea.last().unwrap_or(&0), ec.get(ec.len() / 2).unwrap_or(&0), ec.last().unwrap_or(&0));
	let mut ratios: Vec<f64> = rows.iter().filter(|r| r.found == "yes" && r.straight > 1.0).map(|r| r.yards / r.straight).collect();
	ratios.sort_by(|a, b| a.partial_cmp(b).unwrap());
	if !ratios.is_empty() {
		let _ = writeln!(s, "- Line length / straight line: median {:.2}, max {:.2}.", ratios[ratios.len() / 2], ratios[ratios.len() - 1]);
	}
	let _ = writeln!(s, "\n## Pack sizes\n");
	let _ = writeln!(s, "| map | sectors | layers | graph nodes | graph file | cells file | total files |\n|---|---|---|---|---|---|---|");
	let mut tot = 0usize;
	for m in [0u32, 1] {
		if let Ok(t) = std::fs::read_to_string(packs.join(format!("SendaNav_{m}_sizes.json"))) {
			let v: Value = serde_json::from_str(&t).unwrap_or_default();
			let g = v["graph_file"].as_u64().unwrap_or(0) as usize;
			let c = v["cells_file"].as_u64().unwrap_or(0) as usize;
			tot += g + c;
			let _ = writeln!(s, "| {m} | {} | {} | {} | {:.2} MB | {:.2} MB | {:.2} MB |", v["sectors"], v["layers"], v["nodes"], g as f64 / 1e6, c as f64 / 1e6, (g + c) as f64 / 1e6);
		}
	}
	let _ = writeln!(s, "\nBoth continents: {:.2} MB of Lua files (the strings a loaded continent holds; see docs/NAV.md for the memory budget).\n", tot as f64 / 1e6);
	let _ = writeln!(s, "## Routes\n");
	let _ = writeln!(s, "| route | kind | map | found | line yd | straight yd | ratio | lifts | off links | fine off | abstract us | total us | exp. abstract | exp. cells | sectors |\n|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|");
	for r in rows {
		let ratio = if r.found == "yes" && r.straight > 1.0 { format!("{:.2}", r.yards / r.straight) } else { "-".into() };
		let _ = writeln!(
			s,
			"| {} | {} | {} | {} | {:.0} | {:.0} | {} | {} | {} | {} | {} | {} | {} | {} | {} |",
			r.id, r.kind, r.map, r.found, r.yards, r.straight, ratio, r.lifts, r.cross, r.fine_off, r.stats.micros_abstract, r.stats.micros_total, r.stats.exp_abstract, r.stats.exp_cells, r.stats.sectors_touched
		);
	}
	let _ = r#"unused"#;
	std::fs::write(report, s).map_err(|e| e.to_string())
}

/// Debug: the cells around a world point (layers, class, z, links) and whether a walk from it
/// reaches a second point.
pub fn probe(packs: &Path, map: u32, wx: f64, wy: f64, to: Option<(f64, f64)>, sz: Option<f64>, tz: Option<f64>) -> Result<(), String> {
	let g = pack::read(packs, map)?;
	let (gx, gy) = hpa::world_to_cell(wx, wy);
	for dy in -3..=3 {
		let mut line = String::new();
		for dx in -3..=3 {
			let n = g.count(gx + dx, gy + dy);
			let _ = write!(line, "{n}");
			for li in 0..n {
				let st = (gx + dx, gy + dy, li);
				let links: String = (0..8).map(|d| if g.mask(st, d) != 0 { '1' } else { '0' }).collect();
				let _ = write!(line, "[{} z{:.0} {}]", g.class(st), g.z(st), links);
			}
			line.push_str("  ");
		}
		println!("{line}");
	}
	if let Some((tx, ty)) = to {
		let ab = Abstract::build(&g);
		let s = g.snap(wx, wy, sz, 8);
		let t = g.snap(tx, ty, tz, 8);
		let mut st = QueryStats::default();
		let r = hpa::query(&g, &ab, &s, &t, &mut st);
		println!("snap {:?} -> {:?}: {}", s, t, r.map_or("no route".into(), |r| format!("{:.0} yd", r.cost)));
		// single-sector flood from the start: how far does it reach?
		let f = g.sector_search(hpa::sid_of(s[0].0, s[0].1), &s.iter().map(|&x| (x, 0.0)).collect::<Vec<_>>(), None, false);
		println!("start sector reach: {} of {} layers", f.dist.iter().filter(|d| d.is_finite()).count(), f.dist.len());
		for (lab, e, rev) in [("start", &s, false), ("goal", &t, true)] {
			let sid = hpa::sid_of(e[0].0, e[0].1);
			let r = g.sector_search(sid, &e.iter().map(|&x| (x, 0.0)).collect::<Vec<_>>(), None, rev);
			let (ox, oy) = hpa::sector_origin(sid);
			let comps: Vec<(hpa::St, u16)> = g.graphs.get(&sid).map(|sg| sg.nodes.iter().zip(&sg.comp).filter_map(|(&(c, li, _), &k)| {
				let st = (ox + c as i32 % hpa::SEC, oy + c as i32 / hpa::SEC, li);
				r.cost(st).is_finite().then_some((st, k))
			}).collect()).unwrap_or_default();
			println!("{lab}: sector {sid}, reached nodes {:?}", comps);
		}
	}
	Ok(())
}
