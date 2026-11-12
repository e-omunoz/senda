//! senda-nav-lua: runs the reference Lua router (nav/lua/SendaNavRouter.lua) in Lua 5.1 (the
//! official C Lua 5.1 the WoW client's interpreter derives from; vendored by mlua) over the
//! shipped packs and nav/eval/routes.json, one Step(budget) per simulated frame, and writes
//! nav/eval/report-lua.md: frames per walk, the longest frame, total time, Lua memory.
//! C_EncodingUtil.DecodeBase64 / DecompressString and debugprofilestop are provided here as the
//! client provides them. Copyright (C) 2026 Senda contributors. GPL-3.0-only.
//!
//!   senda-nav-lua --packs out --frames out/data --routes eval/routes.json --lua lua/SendaNavRouter.lua
//!                 --report eval/report-lua.md [--budget 2]

use mlua::{Function, Lua, Table, Value};
use std::collections::HashMap;
use std::fmt::Write as _;
use std::io::Read;
use std::path::PathBuf;
use std::time::Instant;

fn b64(s: &[u8]) -> Vec<u8> {
	let mut v = [255u8; 256];
	for (i, &c) in b"ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/".iter().enumerate() {
		v[c as usize] = i as u8;
	}
	let mut out = Vec::with_capacity(s.len() / 4 * 3);
	for c in s.chunks(4) {
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

fn main() -> Result<(), Box<dyn std::error::Error>> {
	let mut kv: HashMap<String, String> = HashMap::new();
	let a: Vec<String> = std::env::args().skip(1).collect();
	for p in a.chunks(2) {
		kv.insert(p[0].trim_start_matches("--").into(), p.get(1).cloned().unwrap_or_default());
	}
	let get = |k: &str| PathBuf::from(kv.get(k).unwrap_or_else(|| panic!("--{k}")));
	let budget: f64 = kv.get("budget").and_then(|s| s.parse().ok()).unwrap_or(2.0);
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
	cm.set("Zlib", 1)?;
	en.set("CompressionMethod", cm)?;
	g.set("Enum", en)?;
	g.set("debugprofilestop", lua.create_function(move |_, ()| Ok(t0.elapsed().as_secs_f64() * 1000.0))?)?;
	let packs = get("packs");
	let mut mem_maps = Vec::new();
	for m in [0u32, 1] {
		let before = lua.used_memory();
		let tl = Instant::now();
		for part in ["graph", "cells"] {
			let p = packs.join(format!("SendaNav_{m}_{part}.lua"));
			let src = std::fs::read(&p)?;
			lua.load(&src[..]).set_name(p.display().to_string()).exec()?;
		}
		lua.gc_collect()?;
		mem_maps.push((m, lua.used_memory() - before, tl.elapsed().as_secs_f64()));
	}
	let router: Table = lua.load(&std::fs::read(get("lua"))?[..]).set_name("SendaNavRouter.lua").eval()?;
	let find: Function = router.get("Find")?;
	let step: Function = router.get("Step")?;
	let busy: Function = router.get("Busy")?;
	let idle: Function = router.get("Idle")?;
	// frames
	let mut frames: HashMap<u64, (u32, f64, f64, f64, f64)> = HashMap::new();
	for line in std::fs::read_to_string(get("frames").join("ui_map.jsonl"))?.lines() {
		let r: serde_json::Value = serde_json::from_str(line)?;
		let f = |k: &str| r[k].as_f64().unwrap_or(0.0);
		frames.insert(r["ui_map"].as_u64().unwrap_or(0), (r["map"].as_u64().unwrap_or(0) as u32, f("left"), f("right"), f("top"), f("bottom")));
	}
	let to_world = |v: &serde_json::Value| -> Option<(u32, f64, f64, Option<f64>)> {
		let b = frames.get(&v["uiMap"].as_u64()?)?;
		let (x, y) = (v["x"].as_f64()?, v["y"].as_f64()?);
		Some((b.0, b.3 + (b.4 - b.3) * y / 100.0, b.1 + (b.2 - b.1) * x / 100.0, v["z"].as_f64()))
	};
	let doc: serde_json::Value = serde_json::from_slice(&std::fs::read(get("routes"))?)?;
	let mut rows = String::new();
	let (mut found, mut total, mut worst_frame, mut max_frames) = (0, 0, 0f64, 0u32);
	let mut peak = 0usize;
	let mut retained = 0usize;
	let mut all_frames = Vec::new();
	for r in doc["routes"].as_array().unwrap() {
		let (Some(a), Some(b)) = (to_world(&r["from"]), to_world(&r["to"])) else { continue };
		total += 1;
		idle.call::<()>(())?;
		lua.gc_collect()?;
		let req = lua.create_table()?;
		req.set("sx", a.1)?;
		req.set("sy", a.2)?;
		req.set("sz", a.3)?;
		req.set("tx", b.1)?;
		req.set("ty", b.2)?;
		req.set("tz", b.3)?;
		let res = lua.create_table()?;
		let res2 = res.clone();
		let cb = lua.create_function(move |_, (pts, cost, job): (Value, Value, Table)| {
			res2.set("pts", pts)?;
			res2.set("cost", cost)?;
			res2.set("job", job)?;
			res2.set("done", true)?;
			Ok(())
		})?;
		find.call::<Value>((a.0, req, cb))?;
		let (mut nf, mut worst, mut sum) = (0u32, 0f64, 0f64);
		if std::env::var("SENDA_NOGC").is_ok() {
			lua.gc_stop();
		}
		while busy.call::<bool>(())? && nf < 100_000 {
			let t = Instant::now();
			step.call::<()>(budget)?;
			let ms = t.elapsed().as_secs_f64() * 1000.0;
			nf += 1;
			worst = worst.max(ms);
			sum += ms;
			all_frames.push(ms);
			peak = peak.max(lua.used_memory());
		}
		lua.gc_restart();
		lua.gc_collect()?;
		retained = retained.max(lua.used_memory());
		let id = r["id"].as_str().unwrap_or("?");
		let (mut yd, mut npts, mut ok) = (0f64, 0usize, "no".to_string());
		if let Value::Table(p) = res.get::<Value>("pts")? {
			ok = "yes".into();
			found += 1;
			// a point with `lift` is a lift's or teleporter's start: no walking to the next one
			let mut prev: Option<(f64, f64, bool)> = None;
			for pt in p.sequence_values::<Table>() {
				let pt = pt?;
				let (x, y): (f64, f64) = (pt.get("x")?, pt.get("y")?);
				let lift: Option<bool> = pt.get("lift")?;
				if let Some((px, py, false)) = prev {
					yd += (x - px).hypot(y - py);
				}
				prev = Some((x, y, lift.unwrap_or(false)));
				npts += 1;
			}
		} else if let Value::String(s) = res.get::<Value>("cost")? {
			ok = s.to_str()?.to_string();
		}
		let job: Option<Table> = res.get("job")?;
		let (exp, aexp): (u64, u64) = job.map(|j| (j.get("exp").unwrap_or(0), j.get("aexp").unwrap_or(0))).unwrap_or((0, 0));
		worst_frame = worst_frame.max(worst);
		max_frames = max_frames.max(nf);
		eprintln!("{id}: {ok}, {yd:.0} yd, {npts} points, {nf} frames, worst {worst:.2} ms, total {sum:.1} ms");
		let _ = writeln!(rows, "| {id} | {ok} | {yd:.0} | {npts} | {nf} | {worst:.2} | {sum:.1} | {exp} | {aexp} |");
	}
	all_frames.sort_by(|a, b| a.partial_cmp(b).unwrap());
	let p99 = all_frames.get(all_frames.len() * 99 / 100).copied().unwrap_or(0.0);
	let mut s = String::new();
	let _ = writeln!(s, "# Senda navigation: the Lua 5.1 router\n");
	let _ = writeln!(s, "Generated by `senda-nav-lua` (nav/crates/senda-nav-lua): `nav/lua/SendaNavRouter.lua` run by the official Lua 5.1 (mlua, vendored) over the packs in `nav/out` and `nav/eval/routes.json`, every walk from cold (decoded caches dropped), one `Step({budget})` per simulated frame. Timings are this machine's (desktop CPU); the client's Lua is the same interpreter family.\n");
	let _ = writeln!(s, "## Summary\n");
	let _ = writeln!(s, "- Walks found: {found} of {total}.");
	let _ = writeln!(s, "- `Step({budget})` a frame: longest frame {worst_frame:.2} ms; 99th percentile {p99:.2} ms over {} frames.", all_frames.len());
	let _ = writeln!(s, "- Most frames for one walk: {max_frames} (at {budget} ms a frame).");
	for (m, b, t) in &mem_maps {
		let _ = writeln!(s, "- Map {m} packs loaded: {:.1} MB of Lua memory ({t:.2} s to load).", *b as f64 / 1048576.0);
	}
	let _ = writeln!(s, "- Lua memory with both maps loaded, after a walk and a full collection (packs and the decoded caches the walk left): at most {:.1} MB; peak before collection, the searches' garbage included: {:.1} MB.
", retained as f64 / 1048576.0, peak as f64 / 1048576.0);
	let _ = writeln!(s, "## Walks\n\n| route | found | line yd | points | frames | longest frame ms | total ms | cell expansions | graph expansions |\n|---|---|---|---|---|---|---|---|---|");
	s.push_str(&rows);
	std::fs::write(get("report"), s)?;
	Ok(())
}
