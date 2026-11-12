//! Senda (GPL-3.0): esES spell names and rank subtexts from the installed Forever client.
//!
//! Reads SpellName (`Name_lang`), Spell (`NameSubtext_lang`, «Rango 4») and SpellLevels (`SpellLevel`) with forge-gamedata (Polestar's
//! CASC/DB2 reader), lays the client's hotfix cache (`<flavor>/Cache/ADB/<locale>/DBCache.bin`) over them, and
//! writes the ids asked for (every `spell` and `prev` of `--trainer <dir>/*.json`, plus the numbers in each
//! `--ids` file) to `--out` as `{ source, locale, spells: { "<id>": { name, rank?, level? } }, missing: [...] }`.
//! Nothing of the client is written but those names. docs/TRAINER.md.
//!
//!     senda-spellnames --wow "E:/World of Warcraft" --product wowf --defs <WoWDBDefs> \
//!         --trainer ../data/knowledge/trainer --ids extra.txt --out ../data/knowledge/trainer/names.esES.json

use std::collections::{BTreeMap, BTreeSet};
use std::path::{Path, PathBuf};

use forge_gamedata::{dbd::Build, hotfix, Client, Table};

struct Args {
	wow: PathBuf,
	product: String,
	defs: PathBuf,
	locale: String,
	trainer: Vec<PathBuf>,
	ids: Vec<PathBuf>,
	out: PathBuf,
}

fn args() -> Result<Args, String> {
	let mut a = Args { wow: PathBuf::new(), product: "wowf".into(), defs: PathBuf::new(), locale: "esES".into(), trainer: vec![], ids: vec![], out: PathBuf::new() };
	let mut it = std::env::args().skip(1);
	while let Some(k) = it.next() {
		let mut v = || it.next().ok_or_else(|| format!("{k}: falta el valor"));
		match k.as_str() {
			"--wow" => a.wow = v()?.into(),
			"--product" => a.product = v()?,
			"--defs" => a.defs = v()?.into(),
			"--locale" => a.locale = v()?,
			"--trainer" => a.trainer.push(v()?.into()),
			"--ids" => a.ids.push(v()?.into()),
			"--out" => a.out = v()?.into(),
			_ => return Err(format!("argumento desconocido {k}")),
		}
	}
	if a.wow.as_os_str().is_empty() || a.defs.as_os_str().is_empty() || a.out.as_os_str().is_empty() {
		return Err("uso: senda-spellnames --wow <WoW> [--product wowf] --defs <WoWDBDefs> [--locale esES] [--trainer <dir>]... [--ids <archivo>]... --out <json>".into());
	}
	Ok(a)
}

/// The ids wanted: `spell` and `prev` of every trainer row, and every number in the `--ids` files.
fn wanted(a: &Args) -> Result<BTreeSet<u32>, String> {
	let mut ids = BTreeSet::new();
	for dir in &a.trainer {
		let rd = std::fs::read_dir(dir).map_err(|e| format!("{}: {e}", dir.display()))?;
		let mut files: Vec<PathBuf> = rd.filter_map(|e| e.ok()).map(|e| e.path()).collect();
		files.sort();
		for f in files {
			let name = f.file_name().and_then(|n| n.to_str()).unwrap_or("");
			if !name.ends_with(".json") || name.starts_with("names.") {
				continue;
			}
			let text = std::fs::read_to_string(&f).map_err(|e| format!("{}: {e}", f.display()))?;
			let v: serde_json::Value = serde_json::from_str(&text).map_err(|e| format!("{}: {e}", f.display()))?;
			for row in v["spells"].as_array().into_iter().flatten() {
				for k in ["spell", "prev"] {
					if let Some(id) = row[k].as_u64().filter(|&x| x > 0) {
						ids.insert(id as u32);
					}
				}
			}
		}
	}
	for f in &a.ids {
		let text = std::fs::read_to_string(f).map_err(|e| format!("{}: {e}", f.display()))?;
		ids.extend(text.split(|c: char| !c.is_ascii_digit()).filter_map(|t| t.parse::<u32>().ok()).filter(|&x| x > 0));
	}
	Ok(ids)
}

/// id -> the string of `column` (the client's text, NUL-trimmed, lossless UTF-8 or skipped).
fn strings(t: &Table, column: &str, into: &mut BTreeMap<u32, String>, only_valid_hotfix: bool) -> Result<(), String> {
	let c = t.column(column).ok_or_else(|| format!("sin columna {column}"))?;
	let idc = t.id_column.ok_or("sin columna de id")?;
	let status = if only_valid_hotfix { t.column("Status") } else { None };
	for r in 0..t.rows() {
		let row = t.row(r);
		if let Some(s) = status {
			if row[s].as_i64() != Some(hotfix::status::VALID as i64) {
				continue;
			}
		}
		let Some(id) = row[idc].as_i64() else { continue };
		let Some(b) = t.str(&row[c]) else { continue };
		let b = b.split(|&x| x == 0).next().unwrap_or(b);
		if let Ok(s) = std::str::from_utf8(b) {
			if !s.is_empty() {
				into.insert(id as u32, s.to_string());
			} else if only_valid_hotfix {
				into.remove(&(id as u32));
			}
		}
	}
	Ok(())
}

fn json_str(s: &str) -> String {
	serde_json::Value::String(s.to_string()).to_string()
}

fn run() -> Result<(), String> {
	let a = args()?;
	let ids = wanted(&a)?;
	let client = Client::open(&a.wow, &a.product, &a.defs)?;
	let version = client.storage.version.clone();
	let mut names = BTreeMap::new();
	let mut ranks = BTreeMap::new();
	let name_t = client.table("SpellName", &a.locale)?;
	strings(&name_t, "Name_lang", &mut names, false)?;
	let spell_t = client.table("Spell", &a.locale)?;
	strings(&spell_t, "NameSubtext_lang", &mut ranks, false)?;
	let mut notes: Vec<String> = name_t.notes.iter().chain(spell_t.notes.iter()).cloned().collect();
	// SpellLevels.SpellLevel (difficulty 0): the level the spell is learnt at, for rows the trainer lists lack.
	let mut levels: BTreeMap<u32, i64> = BTreeMap::new();
	match client.table("SpellLevels", &a.locale).or_else(|_| client.table("SpellLevels", "enUS")) {
		Ok(t) => {
			let (sc, dc, lc) = (t.column("SpellID"), t.column("DifficultyID"), t.column("SpellLevel"));
			if let (Some(sc), Some(dc), Some(lc)) = (sc, dc, lc) {
				for r in 0..t.rows() {
					let row = t.row(r);
					if row[dc].as_i64() == Some(0) {
						if let (Some(id), Some(l)) = (row[sc].as_i64(), row[lc].as_i64()) {
							if l > 0 {
								levels.insert(id as u32, l);
							}
						}
					}
				}
			}
		}
		Err(e) => notes.push(format!("SpellLevels: {e}")),
	}

	// Hotfixes the server pushed (the same text the game shows).
	let cache = forge_gamedata::flavor_dir(&a.wow, &a.product).map(|d| d.join("Cache").join("ADB").join(&a.locale).join("DBCache.bin"));
	let mut hot = 0usize;
	if let Ok(path) = cache.as_ref() {
		if path.exists() {
			let db = hotfix::DbCache::read(path)?;
			let b = client.build.0;
			let build = Build([b[0], b[1], b[2], db.build]);
			for (table, column, map, hash) in [("SpellName", "Name_lang", &mut names, name_t.table_hash), ("Spell", "NameSubtext_lang", &mut ranks, spell_t.table_hash)] {
				match client.definition(table, build) {
					Ok(def) => {
						let rows = hotfix::rows(&db, hash, &def, true);
						hot += rows.table.rows();
						strings(&rows.table, column, map, true).map_err(|e| format!("{table} (hotfix): {e}"))?;
					}
					Err(e) => notes.push(format!("hotfix {table}: {e}")),
				}
			}
		}
	}

	let mut out = String::new();
	out.push_str("{\n");
	out.push_str(&format!(" \"source\": {},\n", json_str(&format!("ingame-client:{version}"))));
	out.push_str(&format!(" \"locale\": {},\n", json_str(&a.locale)));
	out.push_str(" \"note\": \"SpellName.Name_lang, Spell.NameSubtext_lang y SpellLevels.SpellLevel (nivel de aprendizaje) del cliente instalado (con su caché de hotfixes), leídos por nav/crates/senda-spellnames. Regenerar; no editar a mano.\",\n");
	out.push_str(" \"spells\": {\n");
	let mut missing = vec![];
	let mut lines = vec![];
	for id in &ids {
		match names.get(id) {
			Some(n) => {
				let r = ranks.get(id).map(|r| format!(", \"rank\": {}", json_str(r))).unwrap_or_default();
				let l = levels.get(id).map(|l| format!(", \"level\": {l}")).unwrap_or_default();
				lines.push(format!("  \"{id}\": {{\"name\": {}{r}{l}}}", json_str(n)));
			}
			None => missing.push(id.to_string()),
		}
	}
	out.push_str(&lines.join(",\n"));
	out.push_str("\n },\n");
	out.push_str(&format!(" \"missing\": [{}]\n}}\n", missing.join(", ")));
	write(&a.out, out.as_bytes())?;
	eprintln!("{} {version}: {} nombres, {} sin nombre, {hot} filas de hotfix", a.product, lines.len(), missing.len());
	for n in notes {
		eprintln!("nota: {n}");
	}
	Ok(())
}

fn write(p: &Path, b: &[u8]) -> Result<(), String> {
	if let Some(d) = p.parent() {
		std::fs::create_dir_all(d).map_err(|e| format!("{}: {e}", d.display()))?;
	}
	std::fs::write(p, b).map_err(|e| format!("{}: {e}", p.display()))
}

fn main() {
	if let Err(e) = run() {
		eprintln!("senda-spellnames: {e}");
		std::process::exit(1);
	}
}
