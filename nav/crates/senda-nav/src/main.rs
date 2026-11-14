//! senda-nav: Senda's offline navigation pipeline (docs/NAV.md).
//!
//!   senda-nav prep  --foreverdb DIR --out DIR             frames, lift objects for the grid build
//!   senda-nav grid  --wow DIR --product wowf --defs DIR --data DIR --out DIR [--jobs N] [--continents 0,1]
//!   senda-nav bake  --grid DIR --frames DIR --out DIR [--continents 0,1] [--skip climb] [--block FILE]
//!   senda-nav eval  --packs DIR --frames DIR --routes FILE --report FILE [--grid DIR]
//!   senda-nav walkgraph --packs DIR --travel DIR --out DIR [--grid DIR] [--continents 0,1]   travel planner walk graph
//!
//! Copyright (C) 2026 Senda contributors. GPL-3.0-only.

mod bake;
mod coords;
mod eval;
mod hpa;
mod pack;
mod walkgraph;

use std::collections::HashMap;
use std::path::PathBuf;

fn args() -> (String, HashMap<String, String>) {
	let mut it = std::env::args().skip(1);
	let cmd = it.next().unwrap_or_default();
	let mut kv = HashMap::new();
	let rest: Vec<String> = it.collect();
	let mut i = 0;
	while i < rest.len() {
		let k = rest[i].trim_start_matches("--").to_string();
		let v = rest.get(i + 1).cloned().unwrap_or_default();
		kv.insert(k, v);
		i += 2;
	}
	(cmd, kv)
}

fn continents(kv: &HashMap<String, String>) -> Vec<u32> {
	kv.get("continents").map_or(vec![0, 1], |s| s.split(',').filter_map(|x| x.trim().parse().ok()).collect())
}

fn main() {
	let (cmd, kv) = args();
	let get = |k: &str| -> PathBuf { PathBuf::from(kv.get(k).unwrap_or_else(|| panic!("--{k} missing"))) };
	let r = match cmd.as_str() {
		"prep" => coords::prep(&get("foreverdb"), &get("out")),
		"grid" => {
			let opts = forge_navbuild::build::Opts {
				out: get("out"),
				client: forge_navbuild::build::Client::Install { wow: get("wow"), defs: get("defs") },
				product: kv.get("product").cloned().unwrap_or_else(|| "wowf".into()),
				data: get("data"),
				continents: Some(continents(&kv)),
				force: kv.contains_key("force"),
				jobs: kv.get("jobs").and_then(|s| s.parse().ok()).unwrap_or_else(|| std::thread::available_parallelism().map_or(4, |n| n.get())),
			};
			let say = |m: &str| eprintln!("grid: {m}");
			forge_navbuild::build::run(&opts, &say).map(|o| {
				for w in &o.warnings {
					eprintln!("grid: warning: {w}");
				}
				eprintln!("grid: build {} done", o.build);
			})
		}
		"bake" => bake::set_skip(kv.get("skip").map_or("", |s| s.as_str())).and_then(|_| bake::set_blocks(kv.get("block").map(std::path::Path::new))).and_then(|_| bake::run(&get("grid"), &get("out"), &continents(&kv), kv.get("teleports").map(std::path::Path::new))),
		"eval" => eval::run(&get("packs"), &get("frames"), &get("routes"), &get("report"), kv.get("grid").map(PathBuf::from)),
		"walkgraph" => walkgraph::run(&get("packs"), &get("travel"), &get("out"), kv.get("grid").map(std::path::Path::new), &continents(&kv)),
		"zprof" => walkgraph::zprof(&get("grid"), kv.get("map").and_then(|m| m.parse().ok()).unwrap_or(0), &get("file")),
		"probe" => {
			let f = |k: &str| kv.get(k).and_then(|v| v.parse::<f64>().ok());
			eval::probe(&get("packs"), f("map").unwrap_or(0.0) as u32, f("wx").unwrap(), f("wy").unwrap(), f("tx").zip(f("ty")), f("sz"), f("tz"))
		}
		_ => Err("usage: senda-nav prep|grid|bake|eval|walkgraph|probe ... (see docs/NAV.md)".into()),
	};
	if let Err(e) = r {
		eprintln!("senda-nav: {e}");
		std::process::exit(1);
	}
}
