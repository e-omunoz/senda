//! navsim: headless test of the in-game navigation runtime (addon/Senda_Nav) in the official Lua 5.1
//! (mlua, vendored: the C interpreter the WoW client's Lua derives from), against Senda's Rust
//! evaluator (nav/crates/senda-nav, its `hpa` and `pack` modules compiled in as they are).
//! Copyright (C) 2026 Senda contributors. GPL-3.0-only.
//!
//! The addons are loaded the way the client does it: C_AddOns.LoadAddOn reads each .toc and runs
//! its files (tests/navsim/wow.lua mocks that and the few client calls Senda_Nav uses). Every
//! route of nav/eval/routes.json goes through SendaNav.Route from cold, one rendered frame at a
//! time (the addon's own OnUpdate driver), and is compared with the Rust query on the same packs:
//! cost, length, distance between the lines, segments off the coarse links (hpa::sight), samples
//! over fine columns with no ground (nav/out/ref, never shipped). Then SendaNav.Next follows each
//! path (walk.lua). Writes tests/navsim/report.md.
//!
//!   cargo run --release -- [--root ../..] [--budgets 1.2,1.5] [--report report.md]

#![allow(dead_code)]

#[path = "../../../nav/crates/senda-nav/src/hpa.rs"]
mod hpa;
#[path = "../../../nav/crates/senda-nav/src/pack.rs"]
mod pack;

use mlua::{Function, Lua, Table, Value};
use rustc_hash::FxHashMap;
use std::collections::HashMap;
use std::fmt::Write as _;
use std::io::Read;
use std::path::{Path, PathBuf};
use std::time::Instant;

fn b64(s: &[u8]) -> Vec<u8> {
	let mut v = [255u8; 256];
	for (i, &c) in b"ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/".iter().enumerate() {
		v[c as usize] = i as u8;
	}
	let mut out = Vec::with_capacity(s.len() / 4 * 3);
	for c in s.chunks(4) {
		if c.len() < 4 {
			break;
		}
		let q: Vec<u32> = c.iter().map(|&x| if x == b'=' { 0 } else { v[x as usize] as u32 }).collect();
		let n = q[0] << 18 | q[1] << 12 | q[2] << 6 | q[3];
		out.push((n >> 16) as u8);
		if c[2] != b'=' {
			out.push((n >> 8) as u8);
		}
		if c[3] != b'=' {
			out.push(n as u8);
		}
	}
	out
}

const FINE: f64 = hpa::ADT / 256.0;

struct Ref(FxHashMap<(i32, i32), Vec<u8>>);
impl Ref {
	fn load(p: &Path) -> Option<Ref> {
		let gz = std::fs::read(p).ok()?;
		let mut raw = Vec::new();
		flate2::read::GzDecoder::new(&gz[..]).read_to_end(&mut raw).ok()?;
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

#[derive(Clone, Debug)]
struct Wp {
	wx: f64,
	wy: f64,
	st: hpa::St,
	lift: bool,
}

/// Polyline legs to walk (rides left out).
fn legs(p: &[Wp]) -> Vec<((f64, f64), (f64, f64))> {
	p.windows(2).filter(|w| !w[0].lift).map(|w| ((w[0].wx, w[0].wy), (w[1].wx, w[1].wy))).collect()
}
fn length(p: &[Wp]) -> f64 {
	legs(p).iter().map(|(a, b)| (b.0 - a.0).hypot(b.1 - a.1)).sum()
}
fn seg_dist(p: (f64, f64), a: (f64, f64), b: (f64, f64)) -> f64 {
	let (dx, dy) = (b.0 - a.0, b.1 - a.1);
	let l2 = dx * dx + dy * dy;
	let t = if l2 > 0.0 { (((p.0 - a.0) * dx + (p.1 - a.1) * dy) / l2).clamp(0.0, 1.0) } else { 0.0 };
	(a.0 + dx * t - p.0).hypot(a.1 + dy * t - p.1)
}
/// Largest distance from a point of `a` (every 2 yd) to the line `b`.
fn directed(a: &[Wp], b: &[Wp]) -> (f64, f64) {
	let lb = legs(b);
	let (mut worst, mut sum, mut n) = (0f64, 0f64, 0usize);
	if lb.is_empty() {
		return (0.0, 0.0);
	}
	for (p, q) in legs(a) {
		let len = (q.0 - p.0).hypot(q.1 - p.1);
		let k = (len / 2.0).ceil().max(1.0) as usize;
		for i in 0..=k {
			let f = i as f64 / k as f64;
			let s = (p.0 + (q.0 - p.0) * f, p.1 + (q.1 - p.1) * f);
			let d = lb.iter().map(|(u, v)| seg_dist(s, *u, *v)).fold(f64::INFINITY, f64::min);
			worst = worst.max(d);
			sum += d;
			n += 1;
		}
	}
	(worst, if n > 0 { sum / n as f64 } else { 0.0 })
}

struct Frame {
	map: u32,
	left: f64,
	right: f64,
	top: f64,
	bottom: f64,
}

#[derive(Default)]
struct Run {
	found: String,
	pts: Vec<Wp>,
	cost: f64,
	frames: Vec<f64>,
	cpu: f64,
	wall: f64,
	decodes: u64,
	decode_ms: f64,
	exp: u64,
	aexp: u64,
	path: Option<Table>,
}

fn pct(v: &mut [f64], p: f64) -> f64 {
	if v.is_empty() {
		return 0.0;
	}
	v.sort_by(|a, b| a.partial_cmp(b).unwrap());
	v[((v.len() as f64 - 1.0) * p).round() as usize]
}

fn mb(kb: f64) -> String {
	format!("{:.1} MB", kb / 1024.0)
}

fn main() -> Result<(), Box<dyn std::error::Error>> {
	let a: Vec<String> = std::env::args().skip(1).collect();
	let mut kv: HashMap<String, String> = HashMap::new();
	for p in a.chunks(2) {
		kv.insert(p[0].trim_start_matches("--").into(), p.get(1).cloned().unwrap_or_default());
	}
	let here = PathBuf::from(env!("CARGO_MANIFEST_DIR"));
	let root = kv.get("root").map(PathBuf::from).unwrap_or_else(|| here.join("../.."));
	let root = root.canonicalize()?;
	let budgets: Vec<f64> = kv.get("budgets").map(|s| s.split(',').filter_map(|x| x.parse().ok()).collect()).unwrap_or_default();
	let report = kv.get("report").map(PathBuf::from).unwrap_or_else(|| here.join("report.md"));
	let only = kv.get("only").cloned();

	// ---------------------------------------------------------------- frames (forever-db)
	let mut frames: HashMap<u64, Frame> = HashMap::new();
	for line in std::fs::read_to_string(root.join("nav/out/data/ui_map.jsonl"))?.lines() {
		if line.trim().is_empty() {
			continue;
		}
		let r: serde_json::Value = serde_json::from_str(line)?;
		let f = |k: &str| r[k].as_f64().unwrap_or(0.0);
		frames.insert(r["ui_map"].as_u64().unwrap_or(0), Frame { map: r["map"].as_u64().unwrap_or(0) as u32, left: f("left"), right: f("right"), top: f("top"), bottom: f("bottom") });
	}

	// ---------------------------------------------------------------- Lua 5.1 + client mock
	let lua = Lua::new();
	let g = lua.globals();
	let t0 = Instant::now();
	let enc = lua.create_table()?;
	enc.set("DecodeBase64", lua.create_function(|l, s: mlua::String| l.create_string(b64(&s.as_bytes())))?)?;
	enc.set(
		"DecompressString",
		lua.create_function(|l, (s, _m): (mlua::String, Value)| {
			let mut out = Vec::new();
			flate2::read::ZlibDecoder::new(&s.as_bytes()[..]).read_to_end(&mut out).map_err(mlua::Error::external)?;
			l.create_string(out)
		})?,
	)?;
	g.set("C_EncodingUtil", enc)?;
	let en = lua.create_table()?;
	let cm = lua.create_table()?;
	cm.set("Zlib", 0)?;
	en.set("CompressionMethod", cm)?;
	g.set("Enum", en)?;
	g.set("debugprofilestop", lua.create_function(move |_, ()| Ok(t0.elapsed().as_secs_f64() * 1000.0))?)?;
	let ns = lua.create_table()?;
	ns.set("root", root.to_string_lossy().replace('\\', "/"))?;
	ns.set("readfile", lua.create_function(|l, p: String| match std::fs::read(&p) {
		Ok(b) => Ok(Value::String(l.create_string(b)?)),
		Err(_) => Ok(Value::Nil),
	})?)?;
	let ft = lua.create_table()?;
	for (ui, f) in &frames {
		let t = lua.create_table()?;
		t.set("map", f.map)?;
		t.set("left", f.left)?;
		t.set("right", f.right)?;
		t.set("top", f.top)?;
		t.set("bottom", f.bottom)?;
		ft.set(*ui, t)?;
	}
	ns.set("frames", ft)?;
	g.set("navsim", ns)?;
	for f in ["wow.lua", "walk.lua"] {
		lua.load(&std::fs::read(here.join(f))?[..]).set_name(f).exec()?;
	}
	let count = || -> f64 { lua.load("collectgarbage('collect'); collectgarbage('collect'); return collectgarbage('count')").eval::<f64>().unwrap() };
	let mut checks: Vec<(String, bool, String)> = Vec::new();
	let mut check = |name: &str, ok: bool, detail: String| {
		eprintln!("check {name}: {} {detail}", if ok { "ok" } else { "FAIL" });
		checks.push((name.to_string(), ok, detail));
	};

	// ---------------------------------------------------------------- loading
	let kb0 = count();
	let t = Instant::now();
	let ok: bool = lua.load("return C_AddOns.LoadAddOn('Senda_Nav')").eval()?;
	let runtime_ms = t.elapsed().as_secs_f64() * 1000.0;
	let kb_runtime = count() - kb0;
	check("Senda_Nav loads (LoadOnDemand, no dependencies)", ok && lua.load("return type(SendaNav) == 'table' and navsim.toc.Senda_Nav['LoadOnDemand'] == '1' and navsim.toc.Senda_Nav['Interface'] == '16001' and navsim.toc.Senda_Nav['Dependencies'] == nil").eval::<bool>()?, format!("{runtime_ms:.1} ms, {:.0} KB", kb_runtime));

	// before any pack, in combat: no data, no load, deferred
	let (r1, r2): (String, String) = lua
		.load(
			r#"
		navsim.combat = true
		local why
		SendaNav.Route(1436, 56.33, 47.53, 1436, 42.6, 71.7, function(p, r) why = r end)
		local ok, r = SendaNav.Load(0)
		return tostring(why), tostring(ok) .. " " .. tostring(r)
	"#,
		)
		.eval()?;
	check("Route in combat without the pack -> nodata", r1 == "nodata", r1.clone());
	check("Load(0) in combat -> false, combat", r2 == "false combat", r2.clone());
	let loaded_in_combat: bool = lua.load("return SendaNav.IsLoaded(0)").eval()?;
	check("nothing loaded during combat", !loaded_in_combat, String::new());

	// combat ends: the deferred load runs (Eastern Kingdoms)
	let kb1 = count();
	let t = Instant::now();
	lua.load("navsim.combat = false; navsim.event('PLAYER_REGEN_ENABLED')").exec()?;
	let ek_ms = t.elapsed().as_secs_f64() * 1000.0;
	let kb_ek = count() - kb1;
	let ek_loaded: bool = lua.load("return SendaNav.IsLoaded('EK')").eval()?;
	check("deferred load after combat (PLAYER_REGEN_ENABLED)", ek_loaded, format!("Eastern Kingdoms {ek_ms:.0} ms"));
	// Kalimdor, directly
	let kb2 = count();
	let t = Instant::now();
	let (kok, _): (bool, Value) = lua.load("return SendaNav.Load('Kalimdor')").eval()?;
	let kal_ms = t.elapsed().as_secs_f64() * 1000.0;
	let kb_kal = count() - kb2;
	check("Load('Kalimdor') out of combat", kok, format!("{kal_ms:.0} ms"));
	let again: bool = lua.load("return (SendaNav.Load(1))").eval()?;
	check("Load of a loaded continent is a no-op", again, String::new());
	let (e1, e2): (String, String) = lua
		.load(
			r#"
		local a, b
		SendaNav.Route(1436, 56.33, 47.53, 1438, 50, 50, function(p, r) a = r end)
		SendaNav.Route(999999, 10, 10, 1436, 42.6, 71.7, function(p, r) b = r end)
		return tostring(a), tostring(b)
	"#,
		)
		.eval()?;
	check("ends on two continents -> continent", e1 == "continent", e1.clone());
	check("unknown uiMap -> map", e2 == "map", e2.clone());
	// cancel: no callback, the queue empties
	let cancelled: String = lua
		.load(
			r#"
		local called = false
		local job = SendaNav.Route(1436, 56.33, 47.53, 1436, 42.6, 71.7, function() called = true end)
		navsim.frame(1 / 60)
		SendaNav.Cancel(job)
		for _ = 1, 10 do navsim.frame(1 / 60) end
		return tostring(called) .. " " .. tostring(SendaNav.Busy())
	"#,
		)
		.eval()?;
	check("Cancel: no callback, queue empty", cancelled == "false false", cancelled.clone());

	// ---------------------------------------------------------------- the corpus
	let doc: serde_json::Value = serde_json::from_slice(&std::fs::read(root.join("nav/eval/routes.json"))?)?;
	let routes: Vec<serde_json::Value> = doc["routes"].as_array().unwrap().iter().filter(|r| only.as_deref().map_or(true, |o| r["id"].as_str() == Some(o))).cloned().collect();
	let frame: Function = lua.load("return navsim.frame").eval()?;
	let default_budget: f64 = lua.load("return SendaNav.budget").eval()?;
	let combat_budget: f64 = lua.load("return SendaNav.combatBudget").eval()?;
	let mut sweeps: Vec<(String, f64, bool)> = vec![(format!("{default_budget}"), default_budget, false)];
	for b in &budgets {
		if (*b - default_budget).abs() > 1e-9 {
			sweeps.push((format!("{b}"), *b, false));
		}
	}
	sweeps.push((format!("{combat_budget} (in combat)"), combat_budget, true));

	let run_route = |r: &serde_json::Value, budget: f64, combat: bool| -> Result<Run, mlua::Error> {
		lua.load(format!("SendaNav.budget = {budget}; navsim.combat = {combat}")).exec()?;
		// cold: a quiet frame past idleAfter makes the driver drop every decoded sector
		lua.load("navsim.frame(SendaNav.idleAfter + 1); collectgarbage('collect')").exec()?;
		let res = lua.create_table()?;
		g.set("navsim_res", res.clone())?;
		let (f, t) = (&r["from"], &r["to"]);
		let z = |v: &serde_json::Value| v.as_f64().map(|x| x.to_string()).unwrap_or("nil".into());
		let code = format!(
			"local R = navsim_res; R.job = SendaNav.Route({}, {}, {}, {}, {}, {}, function(p, c, j) R.path, R.cost, R.done = p, c, true end, {{ fz = {}, tz = {} }})",
			f["uiMap"], f["x"], f["y"], t["uiMap"], t["x"], t["y"], z(&f["z"]), z(&t["z"])
		);
		if std::env::var("NAVSIM_NOGC").is_ok() {
			lua.load("collectgarbage('stop')").exec()?;
		}
		if let Ok(l) = std::env::var("NAVSIM_LOOK") {
			lua.load(format!("SendaNav.look = {l}")).exec()?;
		}
		let wall = Instant::now();
		lua.load(code).exec()?;
		let mut out = Run::default();
		let mut n = 0;
		while !res.get::<bool>("done").unwrap_or(false) && n < 200_000 {
			let trace = std::env::var("NAVSIM_TRACE").is_ok();
			let jb: Option<Table> = if trace { res.get("job").ok() } else { None };
			let before = jb.as_ref().map(|j| (j.get::<f64>("decodes").unwrap_or(0.0), j.get::<f64>("decodeMs").unwrap_or(0.0), j.get::<f64>("ops").unwrap_or(0.0)));
			let kb0: f64 = if trace { lua.load("return collectgarbage('count')").eval()? } else { 0.0 };
			let t = Instant::now();
			frame.call::<i32>(1.0 / 60.0)?;
			let ms = t.elapsed().as_secs_f64() * 1000.0;
			out.frames.push(ms);
			if let (Some(j), Some(b)) = (jb, before) {
				if ms > 1.8 {
					let kb1: f64 = lua.load("return collectgarbage('count')").eval()?;
					eprintln!("  slow frame {n}: {ms:.2} ms, decodes +{} ({:.2} ms), ops +{}, kb {kb0:.0} -> {kb1:.0}", j.get::<f64>("decodes").unwrap_or(0.0) - b.0, j.get::<f64>("decodeMs").unwrap_or(0.0) - b.1, j.get::<f64>("ops").unwrap_or(0.0) - b.2);
				}
			}
			n += 1;
		}
		out.wall = wall.elapsed().as_secs_f64() * 1000.0;
		lua.load("collectgarbage('restart')").exec()?;
		lua.load("navsim.combat = false").exec()?;
		if let Ok(job) = res.get::<Table>("job") {
			out.cpu = job.get("cpu").unwrap_or(0.0);
			out.decodes = job.get("decodes").unwrap_or(0);
			out.decode_ms = job.get("decodeMs").unwrap_or(0.0);
			out.exp = job.get("exp").unwrap_or(0);
			out.aexp = job.get("aexp").unwrap_or(0);
		}
		match res.get::<Value>("path")? {
			Value::Table(p) => {
				out.found = "yes".into();
				out.path = Some(p.clone());
				out.cost = res.get("cost")?;
				for w in p.sequence_values::<Table>() {
					let w = w?;
					let lift: Value = w.get("lift")?;
					out.pts.push(Wp { wx: w.get("wx")?, wy: w.get("wy")?, st: (w.get("gx")?, w.get("gy")?, w.get("li")?), lift: !matches!(lift, Value::Nil | Value::Boolean(false)) });
				}
			}
			_ => out.found = res.get::<Value>("cost").map(|v| format!("{v:?}")).unwrap_or_default(),
		}
		Ok(out)
	};

	// the Rust side: the same packs (the shipped copies in addon/), the evaluator's query
	let mut grids: HashMap<u32, (hpa::Grid, hpa::Abstract, Option<Ref>)> = HashMap::new();
	for (m, dir) in [(0u32, "addon/Senda_Nav_EK"), (1, "addon/Senda_Nav_Kalimdor")] {
		let gr = pack::read(&root.join(dir), m)?;
		let ab = hpa::Abstract::build(&gr);
		let rf = Ref::load(&root.join(format!("nav/out/ref/{m}.bin.gz")));
		grids.insert(m, (gr, ab, rf));
	}
	let to_world = |v: &serde_json::Value| -> Option<(u32, f64, f64, Option<f64>)> {
		let f = frames.get(&v["uiMap"].as_u64()?)?;
		let (x, y) = (v["x"].as_f64()?, v["y"].as_f64()?);
		Some((f.map, f.top + (f.bottom - f.top) * y / 100.0, f.left + (f.right - f.left) * x / 100.0, v["z"].as_f64()))
	};

	let walk: Function = lua.load("return navsim.walk").eval()?;
	let mut rows = String::new();
	let mut sweep_rows = String::new();
	let mut primary: Vec<(String, Run)> = Vec::new();
	let mut peak_kb = 0f64;
	for (si, (label, budget, combat)) in sweeps.iter().enumerate() {
		let mut all = Vec::new();
		let mut walls = Vec::new();
		let mut cpus = Vec::new();
		let (mut found, mut max_frames, mut worst_id, mut worst) = (0, 0usize, String::new(), 0f64);
		let mut over2 = 0usize;
		for r in &routes {
			let id = r["id"].as_str().unwrap_or("?").to_string();
			let run = run_route(r, *budget, *combat)?;
			let w = run.frames.iter().cloned().fold(0f64, f64::max);
			if w > worst {
				worst = w;
				worst_id = id.clone();
			}
			over2 += run.frames.iter().filter(|&&f| f > 2.0).count();
			max_frames = max_frames.max(run.frames.len());
			all.extend(run.frames.iter().cloned());
			walls.push(run.wall);
			cpus.push(run.cpu);
			if run.found == "yes" {
				found += 1;
			}
			peak_kb = peak_kb.max(lua.load("return collectgarbage('count')").eval::<f64>()?);
			eprintln!("[{label}] {id}: {} {} pts, {} frames, worst {w:.2} ms, cpu {:.1} ms", run.found, run.pts.len(), run.frames.len(), run.cpu);
			if si == 0 {
				primary.push((id, run));
			}
		}
		let nfr = all.len();
		let p50 = pct(&mut all, 0.5);
		let p99 = pct(&mut all, 0.99);
		let p999 = pct(&mut all, 0.999);
		let _ = writeln!(
			sweep_rows,
			"| {label} | {found}/{} | {nfr} | {p50:.2} | {p99:.2} | {p999:.2} | {worst:.2} ({worst_id}) | {over2} | {max_frames} | {:.1} | {:.1} |",
			routes.len(),
			pct(&mut cpus, 0.5),
			pct(&mut walls, 0.5)
		);
	}

	// ---------------------------------------------------------------- compare, check, follow
	let (mut n_found, mut n_same_cost, mut crossings, mut fine_off, mut samples) = (0, 0, 0usize, 0usize, 0usize);
	let mut walks_ok = 0;
	let mut len_ratios = Vec::new();
	let mut hd = Vec::new();
	let mut next_worst = 0f64;
	let mut cost_diff = 0f64;
	let mut next_calls = 0f64;
	let mut next_total = 0f64;
	for (i, (id, run)) in primary.iter().enumerate() {
		let r = &routes[i];
		let (Some(a), Some(b)) = (to_world(&r["from"]), to_world(&r["to"])) else { continue };
		let (gr, ab, rf) = &grids[&a.0];
		let s = gr.snap(a.1, a.2, a.3, 8);
		let t = gr.snap(b.1, b.2, b.3, 8);
		let mut st = hpa::QueryStats::default();
		let rust = if s.is_empty() || t.is_empty() { None } else { hpa::query(gr, ab, &s, &t, &mut st) };
		let rust_pts: Vec<Wp> = rust
			.as_ref()
			.map(|route| {
				let line = hpa::smooth(gr, route, 400);
				let is_lift = |p: &hpa::St, q: &hpa::St| gr.lifts.iter().any(|l| (l.a == *p && l.b == *q) || (l.b == *p && l.a == *q));
				let mut v: Vec<Wp> = line
					.iter()
					.map(|st| {
						let (wx, wy) = hpa::cell_to_world(st.0 as f64, st.1 as f64);
						Wp { wx, wy, st: *st, lift: false }
					})
					.collect();
				for k in 0..v.len().saturating_sub(1) {
					if is_lift(&v[k].st, &v[k + 1].st) {
						v[k].lift = true;
					}
				}
				v
			})
			.unwrap_or_default();
		let rust_cost = rust.as_ref().map(|r| r.cost).unwrap_or(f64::NAN);
		let rust_len = length(&rust_pts);
		let lua_len = length(&run.pts);
		let (mut cross, mut foff, mut samp) = (0, 0, 0);
		for w in run.pts.windows(2) {
			if w[0].lift {
				continue;
			}
			if !hpa::sight(gr, w[0].st, w[1].st) {
				cross += 1;
			}
			if let Some(rf) = rf {
				let len = (w[1].wx - w[0].wx).hypot(w[1].wy - w[0].wy);
				let n = len.ceil().max(1.0) as usize;
				for k in 0..=n {
					let f = k as f64 / n as f64;
					samp += 1;
					if !rf.walk(w[0].wx + (w[1].wx - w[0].wx) * f, w[0].wy + (w[1].wy - w[0].wy) * f) {
						foff += 1;
					}
				}
			}
		}
		let (h1, m1) = directed(&run.pts, &rust_pts);
		let (h2, m2) = directed(&rust_pts, &run.pts);
		let haus = h1.max(h2);
		let same_cost = run.found == "yes" && rust.is_some() && (run.cost - rust_cost).abs() <= 0.01 * rust_cost.max(1.0);
		let mut wres = String::from("-");
		if run.found == "yes" {
			n_found += 1;
			if same_cost {
				n_same_cost += 1;
			}
			cost_diff = cost_diff.max((run.cost - rust_cost).abs());
			crossings += cross;
			fine_off += foff;
			samples += samp;
			if rust_len > 0.0 {
				len_ratios.push(lua_len / rust_len);
			}
			hd.push(haus);
			// follow it with Next
			let path = run.path.clone().expect("path");
			let (ok, why, calls, worst_ms, total_ms, _ahead): (bool, String, f64, f64, f64, f64) = walk.call(path)?;
			next_worst = next_worst.max(worst_ms);
			next_calls += calls;
			next_total += total_ms;
			if ok {
				walks_ok += 1;
				wres = "ok".into();
			} else {
				wres = why;
			}
		}
		let fw = run.frames.iter().cloned().fold(0f64, f64::max);
		let _ = writeln!(
			rows,
			"| {id} | {} | {} | {:.1} | {:.1} | {} | {:.0} | {:.0} | {:.0} / {:.1} | {} | {}/{} | {} | {:.2} | {:.1} | {} | {} |",
			r["map"],
			run.found,
			run.cost,
			rust_cost,
			if same_cost { "=" } else { "≠" },
			lua_len,
			rust_len,
			haus,
			(m1 + m2) / 2.0,
			cross,
			foff,
			samp,
			run.frames.len(),
			fw,
			run.cpu,
			run.decodes,
			wres
		);
	}

	// ---------------------------------------------------------------- memory
	let kb_both = count();
	lua.load("navsim.frame(SendaNav.idleAfter + 1)").exec()?;
	let kb_idle = count();
	let unl: bool = lua.load("return SendaNav.Unload(0)").eval()?;
	let kb_unload = count();
	let reload: String = lua.load("local ok, r = SendaNav.Load(0); return tostring(ok) .. ' ' .. tostring(r)").eval()?;
	check("Unload(0) frees the pack; a later Load says unloaded", unl && reload == "false unloaded", format!("{} -> {}", mb(kb_idle), mb(kb_unload)));
	let still: bool = lua.load("return SendaNav.IsLoaded(1)").eval()?;
	check("Kalimdor still loaded after unloading EK", still, String::new());
	let driver_off: bool = lua.load("return not navsim.updating()").eval()?;
	check("OnUpdate driver off when idle", driver_off, String::new());

	// ---------------------------------------------------------------- report
	let mut s = String::new();
	let ok_checks = checks.iter().filter(|c| c.1).count();
	let _ = writeln!(s, "# Senda_Nav: the in-game runtime, tested headless\n");
	let _ = writeln!(s, "Generated by `tests/navsim` (`cargo run --release` there): the addons `addon/Senda_Nav`, `addon/Senda_Nav_EK` and `addon/Senda_Nav_Kalimdor` loaded as the client loads them (C_AddOns.LoadAddOn over each .toc, mocked in `tests/navsim/wow.lua`) into the official Lua 5.1 (mlua, vendored), and every route of `nav/eval/routes.json` asked through `SendaNav.Route` from cold (decoded caches dropped), one rendered frame at a time by the addon's own OnUpdate driver. The Rust side is the evaluator's own query (`nav/crates/senda-nav/src/hpa.rs`, `pack.rs`, compiled in unchanged) over the same shipped pack files. Timings are this machine's (desktop CPU, one thread); the client's Lua is the same interpreter family. Not run in the real client.\n");
	let _ = writeln!(s, "## Summary\n");
	let _ = writeln!(s, "- Routes found: {n_found} of {}; same cost as the Rust query (within 1 %): {n_same_cost} of {n_found}; largest cost difference {cost_diff:.2} yd (the same search: equal-cost ties and the string pulling's look-ahead, 200 here and 400 in Rust, are what can make the lines differ).", primary.len());
	let _ = writeln!(s, "- Segments of the Lua lines off the coarse links (Rust `hpa::sight`, rides left out): **{crossings}** (must be 0).");
	let _ = writeln!(s, "- One-yard samples over fine columns with no reachable ground (reference grid, not shipped): {fine_off} of {samples} ({:.2} %).", if samples > 0 { fine_off as f64 * 100.0 / samples as f64 } else { 0.0 });
	let mut lr = len_ratios.clone();
	let mut hdm = hd.clone();
	let _ = writeln!(s, "- Line length Lua / Rust: median {:.3}, min {:.3}, max {:.3}. Largest distance between the two lines (Hausdorff, 2 yd samples): median {:.1} yd, max {:.1} yd.", pct(&mut lr.clone(), 0.5), lr.iter().cloned().fold(f64::INFINITY, f64::min), lr.iter().cloned().fold(0.0, f64::max), pct(&mut hdm, 0.5), hd.iter().cloned().fold(0.0, f64::max));
	lr.clear();
	let _ = writeln!(s, "- Following each path with `SendaNav.Next` (walk.lua): {walks_ok} of {n_found} without a problem; {next_calls:.0} calls, {:.1} µs a call on average, longest {:.0} µs.", next_total * 1000.0 / next_calls.max(1.0), next_worst * 1000.0);
	let _ = writeln!(s, "- API checks: {ok_checks} of {} pass.", checks.len());
	let _ = writeln!(s, "\n## Frame time (one `SendaNav.Route` at a time, from cold)\n");
	let _ = writeln!(s, "The time of a whole rendered frame of the addon's driver (OnUpdate: the slice, its decodes and the garbage collection it triggers). Slice = `SendaNav.budget` (or `combatBudget` in combat).\n");
	let _ = writeln!(s, "| slice ms | found | frames | median ms | p99 ms | p99.9 ms | longest ms (route) | frames > 2 ms | most frames for one route | median CPU per route ms | median wall per route ms |\n|---|---|---|---|---|---|---|---|---|---|---|");
	s.push_str(&sweep_rows);
	let _ = writeln!(s, "\nWall time assumes one frame per call here; in game a route takes `frames` frames (at 60 fps, frames / 60 s).\n");
	let _ = writeln!(s, "## Loading and memory (`collectgarbage(\"count\")` after a full collection)\n");
	let _ = writeln!(s, "| step | time | Lua memory |\n|---|---|---|");
	let _ = writeln!(s, "| `LoadAddOn(\"Senda_Nav\")` (runtime) | {runtime_ms:.1} ms | +{:.0} KB |", kb_runtime);
	let _ = writeln!(s, "| Eastern Kingdoms pack (`Senda_Nav_EK`, deferred from combat) | {ek_ms:.0} ms | +{} |", mb(kb_ek));
	let _ = writeln!(s, "| Kalimdor pack (`Senda_Nav_Kalimdor`) | {kal_ms:.0} ms | +{} |", mb(kb_kal));
	let _ = writeln!(s, "| both packs + caches left by the last route | | {} |", mb(kb_both));
	let _ = writeln!(s, "| after the idle drop (`idleAfter` s without searches) | | {} |", mb(kb_idle));
	let _ = writeln!(s, "| after `SendaNav.Unload(0)` | | {} |", mb(kb_unload));
	let _ = writeln!(s, "| highest count seen right after a route (garbage included) | | {} |", mb(peak_kb));
	let _ = writeln!(s, "\nLoad time is the Lua parse of the pack files in this interpreter; the client adds its own file reading.\n");
	let _ = writeln!(s, "## API checks\n\n| check | result | detail |\n|---|---|---|");
	for (n, ok, d) in &checks {
		let _ = writeln!(s, "| {n} | {} | {d} |", if *ok { "ok" } else { "FAIL" });
	}
	let _ = writeln!(s, "\n## Routes (slice {default_budget} ms)\n");
	let _ = writeln!(s, "Cost in yards (the search's, swimming ×3, rides 175 yd); `=` when Lua and Rust agree within 1 %. Line lengths leave rides out. Distance: largest / mean distance between the Lua and Rust lines. Off links: Lua segments `hpa::sight` rejects. Fine off: one-yard samples on fine columns with no ground. Walk: `SendaNav.Next` along the path.\n");
	let _ = writeln!(s, "| route | map | found | Lua cost | Rust cost | | Lua yd | Rust yd | distance yd max / mean | off links | fine off | frames | longest frame ms | CPU ms | decodes | walk |\n|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|");
	s.push_str(&rows);
	std::fs::write(&report, s)?;
	eprintln!("wrote {}", report.display());
	let failed = checks.iter().filter(|c| !c.1).count();
	if failed > 0 || crossings > 0 || n_found < primary.len() {
		std::process::exit(1);
	}
	Ok(())
}
