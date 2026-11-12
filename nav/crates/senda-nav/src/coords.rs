//! uiMapId + percent <-> world yards on the client map, from forever-db's `ui_map.jsonl` (the
//! Forever client's UiMap / UiMapAssignment frames, as Polestar's forever-db publishes them;
//! CC BY 4.0). Same formula as Senda's tools/foreverdb/db.py `Frames`:
//!
//!   x% = (wy - left) / (right - left) * 100      y% = (wx - top) / (bottom - top) * 100
//!
//! `prep` also writes what forge-navbuild's `build::run` reads from its data folder:
//! map-frames.json (the frames, plus one identity frame per continent, uiMap 9000000 + c, whose
//! "percent" is world yards: x% = wy, y% = wx) and objects.json (the transport game objects of
//! forever-db with their spawns in those identity frames, for the lift links).

use serde_json::{json, Map, Value};
use std::io::BufRead;
use std::path::Path;

#[derive(Clone, Copy, Debug)]
pub struct Frame {
	pub ui: u32,
	pub map: u32,
	pub left: f64,
	pub right: f64,
	pub top: f64,
	pub bottom: f64,
}

pub struct Frames(pub Vec<Frame>);

pub fn jsonl(file: &Path) -> Result<Vec<Value>, String> {
	let f = std::fs::File::open(file).map_err(|e| format!("{}: {e}", file.display()))?;
	let mut out = Vec::new();
	for l in std::io::BufReader::new(f).lines() {
		let l = l.map_err(|e| e.to_string())?;
		if l.trim().is_empty() {
			continue;
		}
		out.push(serde_json::from_str(&l).map_err(|e| format!("{}: {e}", file.display()))?);
	}
	Ok(out)
}

impl Frames {
	pub fn load(file: &Path) -> Result<Frames, String> {
		let rows = jsonl(file)?;
		let f = |r: &Value, k: &str| r[k].as_f64().unwrap_or(f64::NAN);
		Ok(Frames(
			rows.iter()
				.map(|r| Frame { ui: f(r, "ui_map") as u32, map: f(r, "map") as u32, left: f(r, "left"), right: f(r, "right"), top: f(r, "top"), bottom: f(r, "bottom") })
				.collect(),
		))
	}

	pub fn get(&self, ui: u32) -> Option<&Frame> {
		self.0.iter().find(|f| f.ui == ui)
	}

	/// uiMap percent -> (map, wx north, wy west).
	pub fn to_world(&self, ui: u32, x: f64, y: f64) -> Option<(u32, f64, f64)> {
		let b = self.get(ui)?;
		Some((b.map, b.top + (b.bottom - b.top) * (y / 100.0), b.left + (b.right - b.left) * (x / 100.0)))
	}

	/// World -> percent on a given uiMap.
	pub fn to_percent(&self, ui: u32, wx: f64, wy: f64) -> Option<(f64, f64)> {
		let b = self.get(ui)?;
		Some(((wy - b.left) / (b.right - b.left) * 100.0, (wx - b.top) / (b.bottom - b.top) * 100.0))
	}
}

pub fn prep(foreverdb: &Path, out: &Path) -> Result<(), String> {
	let data = if foreverdb.join("data").is_dir() { foreverdb.join("data") } else { foreverdb.to_path_buf() };
	let frames = Frames::load(&data.join("ui_map.jsonl"))?;
	let mut live = Map::new();
	for f in &frames.0 {
		live.insert(f.ui.to_string(), json!({ "c": f.map, "left": f.left, "right": f.right, "top": f.top, "bottom": f.bottom }));
	}
	for c in [0u32, 1] {
		live.insert((9_000_000 + c).to_string(), json!({ "c": c, "left": 0.0, "right": 100.0, "top": 0.0, "bottom": 100.0 }));
	}
	std::fs::create_dir_all(out).map_err(|e| e.to_string())?;
	let w = |name: &str, v: &Value| std::fs::write(out.join(name), serde_json::to_string_pretty(v).unwrap()).map_err(|e| e.to_string());
	w("map-frames.json", &json!({ "forever": live }))?;
	w("zones.json", &json!({}))?;
	// Transport objects (GameObject type 11) and their spawns.
	let objects: Vec<Value> = jsonl(&data.join("object.jsonl"))?.into_iter().filter(|o| o["type"].as_u64() == Some(11)).collect();
	let ids: std::collections::HashSet<u64> = objects.iter().filter_map(|o| o["id"].as_u64()).collect();
	let mut pts: std::collections::HashMap<(u64, u64), Vec<Value>> = Default::default();
	for s in jsonl(&data.join("spawn.jsonl"))? {
		if s["kind"].as_str() != Some("object") {
			continue;
		}
		let (Some(id), Some(map)) = (s["id"].as_u64(), s["map"].as_u64()) else { continue };
		if !ids.contains(&id) || map > 1 {
			continue;
		}
		let (Some(x), Some(y)) = (s["x"].as_f64(), s["y"].as_f64()) else { continue };
		// Identity frame: pt[0] (x%) is wy, pt[1] (y%) is wx.
		pts.entry((id, map)).or_default().push(json!([y, x]));
	}
	let mut list = Vec::new();
	for o in &objects {
		let id = o["id"].as_u64().unwrap_or(0);
		let mut spawns = Map::new();
		for map in [0u64, 1] {
			if let Some(p) = pts.get(&(id, map)) {
				spawns.insert((9_000_000 + map).to_string(), json!({ "pts": p }));
			}
		}
		if !spawns.is_empty() {
			list.push(json!({ "id": id, "name": o["name"], "spawns": spawns }));
		}
	}
	eprintln!("prep: {} frames, {} transport objects with spawns", frames.0.len(), list.len());
	w("objects.json", &Value::Array(list))?;
	std::fs::copy(data.join("ui_map.jsonl"), out.join("ui_map.jsonl")).map_err(|e| e.to_string())?;
	Ok(())
}
