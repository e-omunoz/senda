#!/usr/bin/env python3
"""Validación estática de los datos de Senda (guías, secciones y conocimiento).

Uso:
    python tools/validate.py              # tabla de resumen + errores/avisos
    python tools/validate.py --json       # salida JSON (CI y web)
    python tools/validate.py --strict     # los avisos también hacen fallar
    python tools/validate.py --root RUTA  # validar otra raíz (fixtures)

Código de salida: 0 sin errores, 1 con errores (o avisos con --strict), 2 error de uso.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterator

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import Paths, load_toml, setup_stdio  # noqa: E402

STATUSES = ("verified", "unverified", "disputed")

# Campos obligatorios según `do` (además de id/do/text/status, que exige el esquema).
# Fichas de nombre en text/tip ({quest:155}): el addon las resuelve con el cliente (Core/Names.lua).
TOKEN_KINDS = {"quest", "npc", "item", "spell", "map", "obj"}
_TOKEN_ANY_RE = re.compile(r"\{([a-z]+):([^}\s]*)\}")

DO_REQUIRES: dict[str, tuple[str, ...]] = {
    "accept": ("quest",),
    "turnin": ("quest",),
    "complete": ("quest",),
    "train": ("spells",),
    "buy": ("item",),
    "have": ("item",),
    "loot": ("item",),
    "level": ("level",),
    "skill": ("prof", "skill"),
    "goto": ("at",),
    "getfp": ("node",),
    "hearth": ("zone",),
    "fly": ("zone",),
    "learn_prof": ("prof",),
}

KNOWLEDGE_KIND_ARRAY = {
    "page": "block",
    "talents": "pick",
    "spells": "train",
    "macros": "macro",
    "professions": "route",
    "rotation": "phase",
    "weights": "band",
    "bis": "bis",
}

# Claves de pesos de equipo que entiende Modules/Gear.lua (docs/GEAR.md).
WEIGHT_KEYS = {"SP", "SCHOOL_W", "INT", "SPI", "STA", "STR", "AGI", "AP", "RAP", "MP5", "ARMOR", "DPS", "RANGED_DPS",
               "WAND_DPS", "HIT", "CRIT", "SPELL_HIT", "SPELL_CRIT", "DEFENSE", "DODGE"}


# =========================================================================== mini JSON Schema
class SchemaError(Exception):
    """El propio esquema usa algo que este validador no soporta."""


_SUPPORTED = {
    "$schema", "$id", "$defs", "$ref", "$comment", "title", "description", "default", "examples",
    "type", "enum", "const", "required", "properties", "additionalProperties",
    "pattern", "minLength", "maxLength", "minimum", "maximum", "exclusiveMinimum", "exclusiveMaximum",
    "minItems", "maxItems", "items", "prefixItems", "uniqueItems",
}


def _type_ok(value: Any, t: str) -> bool:
    if t == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if t == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if t == "string":
        return isinstance(value, str)
    if t == "boolean":
        return isinstance(value, bool)
    if t == "array":
        return isinstance(value, list)
    if t == "object":
        return isinstance(value, dict)
    if t == "null":
        return value is None
    raise SchemaError(f"tipo desconocido en esquema: {t}")


def _resolve(ref: str, root: dict) -> dict:
    if not ref.startswith("#/"):
        raise SchemaError(f"$ref no soportado (solo locales): {ref}")
    node: Any = root
    for part in ref[2:].split("/"):
        part = part.replace("~1", "/").replace("~0", "~")
        if not isinstance(node, dict) or part not in node:
            raise SchemaError(f"$ref no resuelve: {ref}")
        node = node[part]
    return node


def _fmt(v: Any) -> str:
    return json.dumps(v, ensure_ascii=False)


def schema_errors(value: Any, schema: dict, root: dict | None = None,
                  path: tuple = ()) -> Iterator[tuple[tuple, str]]:
    """Valida `value` contra el subconjunto de JSON Schema usado en schema/*.json.
    Genera (ruta, mensaje)."""
    root = root if root is not None else schema
    unknown = set(schema) - _SUPPORTED
    if unknown:
        raise SchemaError(f"palabras clave no soportadas: {sorted(unknown)}")

    if "$ref" in schema:
        yield from schema_errors(value, _resolve(schema["$ref"], root), root, path)

    if "type" in schema:
        types = schema["type"] if isinstance(schema["type"], list) else [schema["type"]]
        if not any(_type_ok(value, t) for t in types):
            yield path, f"tipo incorrecto: se esperaba {'/'.join(types)}, hay {_fmt(value)}"
            return

    if "enum" in schema and value not in schema["enum"]:
        yield path, f"valor {_fmt(value)} no permitido; opciones: {', '.join(map(str, schema['enum']))}"
        return
    if "const" in schema and value != schema["const"]:
        yield path, f"debe ser {_fmt(schema['const'])}"

    if isinstance(value, str):
        if "minLength" in schema and len(value) < schema["minLength"]:
            yield path, "no puede estar vacío" if schema["minLength"] == 1 else f"longitud < {schema['minLength']}"
        if "maxLength" in schema and len(value) > schema["maxLength"]:
            yield path, f"longitud > {schema['maxLength']}"
        if "pattern" in schema and not re.search(schema["pattern"], value):
            yield path, f"{_fmt(value)} no cumple el patrón {schema['pattern']}"

    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if "minimum" in schema and value < schema["minimum"]:
            yield path, f"{value} < mínimo {schema['minimum']}"
        if "maximum" in schema and value > schema["maximum"]:
            yield path, f"{value} > máximo {schema['maximum']}"
        if "exclusiveMinimum" in schema and value <= schema["exclusiveMinimum"]:
            yield path, f"{value} debe ser > {schema['exclusiveMinimum']}"
        if "exclusiveMaximum" in schema and value >= schema["exclusiveMaximum"]:
            yield path, f"{value} debe ser < {schema['exclusiveMaximum']}"

    if isinstance(value, list):
        if "minItems" in schema and len(value) < schema["minItems"]:
            yield path, f"necesita al menos {schema['minItems']} elementos (hay {len(value)})"
        if "maxItems" in schema and len(value) > schema["maxItems"]:
            yield path, f"admite como máximo {schema['maxItems']} elementos (hay {len(value)})"
        prefix = schema.get("prefixItems", [])
        for i, item in enumerate(value):
            if i < len(prefix):
                yield from schema_errors(item, prefix[i], root, path + (i,))
            elif "items" in schema:
                if schema["items"] is False:
                    yield path + (i,), "elemento sobrante"
                elif isinstance(schema["items"], dict):
                    yield from schema_errors(item, schema["items"], root, path + (i,))
        if schema.get("uniqueItems"):
            seen = []
            for i, item in enumerate(value):
                if item in seen:
                    yield path + (i,), f"elemento repetido {_fmt(item)}"
                seen.append(item)

    if isinstance(value, dict):
        for req in schema.get("required", []):
            if req not in value:
                yield path, f"falta el campo obligatorio '{req}'"
        props = schema.get("properties", {})
        addl = schema.get("additionalProperties", True)
        for k, v in value.items():
            if k in props:
                yield from schema_errors(v, props[k], root, path + (k,))
            elif addl is False:
                yield path + (k,), f"campo desconocido '{k}'"
            elif isinstance(addl, dict):
                yield from schema_errors(v, addl, root, path + (k,))


# =========================================================================== modelo
@dataclass
class Issue:
    level: str  # "error" | "warning"
    file: str
    where: str
    msg: str

    def __str__(self) -> str:
        tag = "ERROR" if self.level == "error" else "AVISO"
        loc = f"{self.file}" + (f" [{self.where}]" if self.where else "")
        return f"{tag} {loc}: {self.msg}"

    def as_dict(self) -> dict:
        return {"level": self.level, "file": self.file, "where": self.where, "msg": self.msg}


@dataclass
class Section:
    key: str            # "shared:<stem>" o "<guide-id>/<stem>"
    stem: str
    path: Path
    data: dict
    shared: bool
    guide: str | None   # guía propietaria (secciones locales)

    @property
    def id(self) -> str:
        return self.data.get("id", "") if isinstance(self.data, dict) else ""


@dataclass
class Guide:
    id: str
    dir: Path
    path: Path
    data: dict
    sections: list[Section] = field(default_factory=list)  # resueltas, en orden


@dataclass
class KnowledgePage:
    path: Path
    group: str          # carpeta de primer nivel bajo data/knowledge (p. ej. "warlock", "general")
    data: dict


@dataclass
class Dataset:
    paths: Paths
    guides: list[Guide] = field(default_factory=list)
    sections: list[Section] = field(default_factory=list)
    knowledge: list[KnowledgePage] = field(default_factory=list)
    issues: list[Issue] = field(default_factory=list)
    local: dict[str, list[Section]] = field(default_factory=dict)       # guía -> secciones de su carpeta
    shared_by_stem: dict[str, Section] = field(default_factory=dict)
    unreadable: set[Path] = field(default_factory=set)                 # TOML que no se pudo leer

    def err(self, path: Path | str, where: str, msg: str) -> None:
        self.issues.append(Issue("error", self._rel(path), where, msg))

    def warn(self, path: Path | str, where: str, msg: str) -> None:
        self.issues.append(Issue("warning", self._rel(path), where, msg))

    def _rel(self, p: Path | str) -> str:
        return self.paths.rel(Path(p)) if isinstance(p, Path) else p

    @property
    def errors(self) -> list[Issue]:
        return [i for i in self.issues if i.level == "error"]

    @property
    def warnings(self) -> list[Issue]:
        return [i for i in self.issues if i.level == "warning"]


def _load_schema(paths: Paths, name: str) -> dict:
    with open(paths.schema / name, encoding="utf-8") as fh:
        return json.load(fh)


def _where(data: Any, path: tuple) -> str:
    """Convierte una ruta de esquema en algo legible: 'paso coldridge-001 · at[1]'."""
    if not path:
        return ""
    parts: list[str] = []
    rest = list(path)
    if len(rest) >= 2 and isinstance(rest[1], int) and isinstance(data, dict) \
            and rest[0] in ("step", "block", "pick", "train", "macro", "route", "phase"):
        arr = data.get(rest[0]) or []
        idx = rest[1]
        item = arr[idx] if idx < len(arr) else None
        label = "paso" if rest[0] == "step" else rest[0]
        ident = item.get("id") if isinstance(item, dict) and isinstance(item.get("id"), str) else None
        parts.append(f"{label} {ident}" if ident else f"{label} #{idx + 1}")
        rest = rest[2:]
    if rest:
        s = ""
        for p in rest:
            s += f"[{p}]" if isinstance(p, int) else (f".{p}" if s else str(p))
        parts.append(f"campo '{s}'")
    return " · ".join(parts)


def _numeric_prefix_key(p: Path) -> tuple:
    m = re.match(r"^(\d+)", p.stem)
    return (int(m.group(1)) if m else 10**9, p.name)


def _try_load(ds: Dataset, path: Path) -> dict | None:
    try:
        return load_toml(path)
    except Exception as exc:  # tomllib.TOMLDecodeError, UnicodeDecodeError, OSError
        ds.err(path, "", f"TOML inválido: {exc}")
        ds.unreadable.add(path)
        return None


# =========================================================================== carga
def collect(paths: Paths) -> Dataset:
    ds = Dataset(paths)
    shared_by_stem = ds.shared_by_stem

    if paths.shared.is_dir():
        for p in sorted(paths.shared.glob("*.toml")):
            data = _try_load(ds, p)
            if data is None:
                continue
            sec = Section(f"shared:{p.stem}", p.stem, p, data, True, None)
            ds.sections.append(sec)
            shared_by_stem[p.stem] = sec

    if paths.guides.is_dir():
        for gdir in sorted(d for d in paths.guides.iterdir() if d.is_dir()):
            gpath = gdir / "guide.toml"
            local: list[Section] = []
            for p in sorted((f for f in gdir.glob("*.toml") if f.name != "guide.toml"), key=_numeric_prefix_key):
                data = _try_load(ds, p)
                if data is None:
                    continue
                sec = Section(f"{gdir.name}/{p.stem}", p.stem, p, data, False, gdir.name)
                local.append(sec)
                ds.sections.append(sec)
            if not gpath.exists():
                ds.err(gdir, "", "carpeta de guía sin guide.toml")
                continue
            gdata = _try_load(ds, gpath)
            if gdata is None:
                continue
            ds.guides.append(Guide(gdir.name, gdir, gpath, gdata))
            ds.local[gdir.name] = local

    if paths.knowledge.is_dir():
        for p in sorted(paths.knowledge.rglob("*.toml"), key=lambda x: x.relative_to(paths.knowledge).as_posix()):
            rel = p.relative_to(paths.knowledge)
            group = rel.parts[0] if len(rel.parts) > 1 else "general"
            data = _try_load(ds, p)
            if data is not None:
                ds.knowledge.append(KnowledgePage(p, group, data))
    return ds


# =========================================================================== comprobaciones
def _check_schema(ds: Dataset, path: Path, data: dict, schema: dict) -> bool:
    ok = True
    for spath, msg in schema_errors(data, schema):
        ds.err(path, _where(data, spath), msg)
        ok = False
    return ok


def _check_provenance(ds: Dataset, path: Path, where: str, obj: dict) -> None:
    status = obj.get("status")
    sources = obj.get("sources") or []
    if status == "verified" and not sources:
        ds.err(path, where, "status = \"verified\" exige 'sources' no vacío")
    elif status == "disputed" and not sources:
        ds.warn(path, where, "status = \"disputed\" sin 'sources' (indica qué fuentes discrepan)")


def _check_point(ds: Dataset, path: Path, where: str, pt: Any, label: str) -> None:
    # El esquema ya lo cubre; esto es una red de seguridad si el esquema cambia.
    if isinstance(pt, list) and len(pt) >= 3:
        for i, c in ((1, "x"), (2, "y")):
            v = pt[i]
            if isinstance(v, (int, float)) and not isinstance(v, bool) and not (0 <= v <= 100):
                ds.err(path, where, f"'{label}' coordenada {c}={v} fuera de 0-100")


def run_checks(ds: Dataset) -> Dataset:
    paths = ds.paths
    sec_schema = _load_schema(paths, "section.schema.json")
    guide_schema = _load_schema(paths, "guide.schema.json")
    know_schema = _load_schema(paths, "knowledge.schema.json")

    # --- secciones: esquema, pasos
    step_ids: dict[str, Path] = {}
    section_ids: dict[str, Path] = {}
    for sec in ds.sections:
        data = sec.data
        _check_schema(ds, sec.path, data, sec_schema)
        if not isinstance(data, dict):
            continue
        sid = data.get("id")
        if isinstance(sid, str):
            if sid in section_ids:
                ds.err(sec.path, f"sección {sid}",
                       f"id de sección duplicado (también en {paths.rel(section_ids[sid])})")
            else:
                section_ids[sid] = sec.path
        lv = data.get("levels")
        if isinstance(lv, list) and len(lv) == 2 and all(isinstance(x, int) for x in lv) and lv[0] > lv[1]:
            ds.err(sec.path, "campo 'levels'", f"rango invertido {lv}")
        steps = data.get("step")
        if not isinstance(steps, list):
            continue
        for i, st in enumerate(steps):
            if not isinstance(st, dict):
                continue
            stid = st.get("id")
            where = f"paso {stid}" if isinstance(stid, str) else f"paso #{i + 1}"
            if isinstance(stid, str):
                if stid in step_ids:
                    ds.err(sec.path, where,
                           f"id de paso duplicado (también en {paths.rel(step_ids[stid])})")
                else:
                    step_ids[stid] = sec.path
            do = st.get("do")
            for req in DO_REQUIRES.get(do, ()):
                val = st.get(req)
                if val is None or val == [] or val == "":
                    ds.err(sec.path, f"{where} · campo '{req}'", f"do = \"{do}\" exige '{req}'")
            if "obj" in st and "quest" not in st:
                ds.err(sec.path, f"{where} · campo 'obj'", "'obj' sin 'quest'")
            if "at" in st:
                _check_point(ds, sec.path, where, st["at"], "at")
            for wp in st.get("wps") or []:
                _check_point(ds, sec.path, where, wp, "wps")
            flt = st.get("if")
            if isinstance(flt, dict) and isinstance(flt.get("minlevel"), int) \
                    and isinstance(flt.get("maxlevel"), int) and flt["minlevel"] > flt["maxlevel"]:
                ds.err(sec.path, f"{where} · campo 'if'", "minlevel > maxlevel")
            for fld in ("text", "tip"):
                val = st.get(fld)
                if isinstance(val, str):
                    for m in _TOKEN_ANY_RE.finditer(val):
                        if m.group(1) not in TOKEN_KINDS:
                            ds.err(sec.path, f"{where} · campo '{fld}'",
                                   f"ficha desconocida {m.group(0)} (tipos: {', '.join(sorted(TOKEN_KINDS))})")
                        elif not m.group(2).isdigit() or int(m.group(2)) <= 0:
                            ds.err(sec.path, f"{where} · campo '{fld}'", f"ficha sin id numérico: {m.group(0)}")
            _check_provenance(ds, sec.path, where, st)

    # --- guías
    guide_ids: dict[str, Path] = {}
    used: set[str] = set()
    local_map = ds.local
    shared_by_stem = ds.shared_by_stem
    for g in ds.guides:
        data = g.data
        _check_schema(ds, g.path, data, guide_schema)
        gid = data.get("id")
        if isinstance(gid, str):
            if gid != g.dir.name:
                ds.err(g.path, "campo 'id'", f"el id \"{gid}\" no coincide con la carpeta \"{g.dir.name}\"")
            if gid in guide_ids:
                ds.err(g.path, "campo 'id'", f"id de guía duplicado (también en {paths.rel(guide_ids[gid])})")
            guide_ids[gid] = g.path
        local = local_map.get(g.dir.name, [])
        by_stem = {s.stem: s for s in local}
        by_id = {s.id: s for s in local if s.id}
        shared_by_id = {s.id: s for s in shared_by_stem.values() if s.id}
        seen: set[str] = set()
        for entry in data.get("sections") or []:
            if not isinstance(entry, str):
                continue
            if entry.startswith("shared:"):
                name = entry[len("shared:"):]
                sec = shared_by_stem.get(name) or shared_by_id.get(name)
                hint = f"data/shared/{name}.toml"
            else:
                sec = by_stem.get(entry) or by_id.get(entry)
                hint = f"{paths.rel(g.dir)}/{entry}.toml"
            if sec is None:
                if (paths.root / hint) in ds.unreadable:
                    ds.err(g.path, f"sections · \"{entry}\"", f"la sección no se pudo leer ({hint})")
                else:
                    ds.err(g.path, f"sections · \"{entry}\"", f"la sección no existe ({hint})")
                continue
            if sec.key in seen:
                ds.err(g.path, f"sections · \"{entry}\"", "sección repetida en la guía")
                continue
            seen.add(sec.key)
            used.add(sec.key)
            g.sections.append(sec)
        # niveles no decrecientes
        prev: tuple[int, str] | None = None
        for sec in g.sections:
            lv = sec.data.get("levels") if isinstance(sec.data, dict) else None
            if not (isinstance(lv, list) and len(lv) == 2 and all(isinstance(x, int) for x in lv)):
                continue
            if prev and lv[0] < prev[0]:
                ds.warn(g.path, f"sections · {sec.id}",
                        f"los niveles bajan: {sec.id} empieza en {lv[0]} tras {prev[1]} (nivel {prev[0]})")
            prev = (lv[0], sec.id)
        _check_provenance(ds, g.path, "guía", data)

    for sec in ds.sections:
        if sec.key not in used:
            ds.warn(sec.path, f"sección {sec.id}", "ninguna guía usa esta sección")

    # --- conocimiento
    know_ids: dict[str, Path] = {}
    for kp in ds.knowledge:
        data = kp.data
        _check_schema(ds, kp.path, data, know_schema)
        kid = data.get("id")
        if isinstance(kid, str):
            if kid in know_ids:
                ds.err(kp.path, "campo 'id'", f"id de conocimiento duplicado (también en {paths.rel(know_ids[kid])})")
            know_ids[kid] = kp.path
        kind = data.get("kind")
        arr = KNOWLEDGE_KIND_ARRAY.get(kind)
        # professions admite también tablas de rangos/materiales sin rutas (p. ej. professions-materials).
        alt_ok = kind == "professions" and (data.get("rank") or data.get("material"))
        if arr and not data.get(arr) and not alt_ok:
            ds.err(kp.path, f"campo '{arr}'", f"kind = \"{kind}\" exige al menos un [[{arr}]]")
        lv = data.get("levels")
        if isinstance(lv, list) and len(lv) == 2 and all(isinstance(x, int) for x in lv) and lv[0] > lv[1]:
            ds.err(kp.path, "campo 'levels'", f"rango invertido {lv}")
        _check_provenance(ds, kp.path, "página", data)
        for name in KNOWLEDGE_KIND_ARRAY.values():
            for i, item in enumerate(data.get(name) or []):
                if isinstance(item, dict):
                    _check_provenance(ds, kp.path, f"{name} #{i + 1}", item)
                    if name == "phase" and isinstance(item.get("from"), int) and isinstance(item.get("to"), int) \
                            and item["from"] > item["to"]:
                        ds.err(kp.path, f"{name} #{i + 1}", "from > to")
                    if name == "route" and isinstance(item.get("trainer"), list):
                        _check_point(ds, kp.path, f"{name} #{i + 1}", item["trainer"], "trainer")
    _check_gear_weights(ds)
    _check_professions(ds)
    return ds


def _check_professions(ds: Dataset) -> None:
    """Rutas de profesión (las generadas por tools/gen_professions.py llevan `prof`): tramos de fabricación sin huecos
    ni solapes, que no cruzan un tope de rango (75/150/225), colores {aprende, amarillo, verde, gris} ordenados, la
    receta aprendida antes de su tramo, `n` >= 1, y los pasos de rango (`train`) con un [[rank]] de ese nombre."""
    for kp in ds.knowledge:
        d = kp.data
        if d.get("kind") != "professions" or not d.get("prof"):
            continue
        ranks = {r.get("name"): r for r in d.get("rank") or [] if isinstance(r, dict)}
        segs = []
        for i, s in enumerate(d.get("route") or []):
            if not isinstance(s, dict):
                continue
            where = f"route #{i + 1}"
            if s.get("train"):
                if s["train"] not in ranks:
                    ds.err(kp.path, where, f"train = \"{s['train']}\" sin [[rank]] de ese nombre")
                continue
            segs.append((where, s))
            fr, to = s.get("from"), s.get("to")
            if not (isinstance(fr, int) and isinstance(to, int)) or fr >= to:
                ds.err(kp.path, where, f"tramo vacío o invertido {fr}-{to}")
                continue
            for cap in (75, 150, 225):
                if fr < cap < to:
                    ds.err(kp.path, where, f"el tramo {fr}-{to} cruza el tope {cap}: pártelo para entrenar el rango")
            col = s.get("colors")
            if col is not None:
                if not (isinstance(col, list) and len(col) == 4 and all(isinstance(x, int) for x in col)
                        and col[0] <= col[1] <= col[2] <= col[3]):
                    ds.err(kp.path, where, f"colors debe ser [aprende, amarillo, verde, gris] ordenados: {col}")
                elif col[0] > fr or fr >= col[3]:
                    ds.err(kp.path, where, f"la receta no da puntos en {fr} (colores {col})")
            if not isinstance(s.get("n"), int) or s["n"] < 1:
                ds.err(kp.path, where, "n (fabricaciones esperadas) debe ser >= 1")
            if not (s.get("craft") or s.get("craft_spell")):
                ds.err(kp.path, where, "falta craft o craft_spell")
        segs.sort(key=lambda w: w[1].get("from", 0))
        for (_, a), (wb, b) in zip(segs, segs[1:]):
            if a.get("to") != b.get("from"):
                ds.err(kp.path, wb, f"hueco o solape entre {a.get('from')}-{a.get('to')} y {b.get('from')}-{b.get('to')}")


def _check_gear_weights(ds: Dataset) -> None:
    """kind = "weights": una build por defecto, tramos sin huecos ni solapes de 1 a 60 por build, claves conocidas.
    kind = "bis": cada build existe en los pesos de su clase y from <= to."""
    builds_by_class: dict[str, set[str]] = {}
    for kp in ds.knowledge:
        d = kp.data
        if d.get("kind") != "weights":
            continue
        builds = [b for b in (d.get("build") or []) if isinstance(b, dict) and isinstance(b.get("key"), str)]
        if not builds:
            ds.err(kp.path, "campo 'build'", 'kind = "weights" exige al menos un [[build]]')
        keys = [b["key"] for b in builds]
        if len(set(keys)) != len(keys):
            ds.err(kp.path, "campo 'build'", "build repetida")
        if builds and sum(1 for b in builds if b.get("default")) != 1:
            ds.err(kp.path, "campo 'build'", "exactamente una [[build]] con default = true")
        builds_by_class.setdefault(str(d.get("class")), set()).update(keys)
        per: dict[str, list[tuple[int, int]]] = {k: [] for k in keys}
        for i, b in enumerate(d.get("band") or []):
            if not isinstance(b, dict):
                continue
            where = f"band #{i + 1}"
            if b.get("build") not in per:
                ds.err(kp.path, where, f"build '{b.get('build')}' no está en [[build]]")
                continue
            if isinstance(b.get("from"), int) and isinstance(b.get("to"), int):
                if b["from"] > b["to"]:
                    ds.err(kp.path, where, "from > to")
                per[b["build"]].append((b["from"], b["to"]))
            for k in (b.get("w") or {}):
                if k not in WEIGHT_KEYS:
                    ds.err(kp.path, where, f"clave de peso desconocida '{k}' (válidas: {', '.join(sorted(WEIGHT_KEYS))})")
        for key, spans in per.items():
            spans.sort()
            nxt = 1
            for a, z in spans:
                if a != nxt:
                    ds.err(kp.path, f"build {key}", f"los tramos deben seguirse sin huecos ni solapes (esperado {nxt}, hay {a})")
                    break
                nxt = z + 1
            else:
                if nxt != 61:
                    ds.err(kp.path, f"build {key}", f"los tramos deben llegar al 60 (llegan al {nxt - 1})")
    for kp in ds.knowledge:
        d = kp.data
        if d.get("kind") != "bis":
            continue
        known = builds_by_class.get(str(d.get("class")), set())
        for i, b in enumerate(d.get("bis") or []):
            if not isinstance(b, dict):
                continue
            if b.get("build") not in known:
                ds.err(kp.path, f"bis #{i + 1}", f"build '{b.get('build')}' no está en los pesos de {d.get('class')}")
            if isinstance(b.get("from"), int) and isinstance(b.get("to"), int) and b["from"] > b["to"]:
                ds.err(kp.path, f"bis #{i + 1}", "from > to")


def load_and_check(paths: Paths) -> Dataset:
    return run_checks(collect(paths))


# =========================================================================== resumen
def summary(ds: Dataset) -> dict:
    def counts(steps: list[dict]) -> dict:
        c = {s: 0 for s in STATUSES}
        for st in steps:
            if isinstance(st, dict) and st.get("status") in c:
                c[st["status"]] += 1
        n = len(steps)
        out: dict[str, Any] = {"steps": n, **c}
        for s in STATUSES:
            out[f"pct_{s}"] = round(100.0 * c[s] / n, 1) if n else 0.0
        return out

    guides = []
    for g in ds.guides:
        steps = [st for sec in g.sections for st in (sec.data.get("step") or [])]
        guides.append({
            "id": g.data.get("id", g.id),
            "title": g.data.get("title", ""),
            "faction": g.data.get("faction"),
            "races": g.data.get("races", []),
            "classes": g.data.get("classes", []),
            "sections": [s.id for s in g.sections],
            **counts(steps),
        })
    all_steps = [st for sec in ds.sections for st in (sec.data.get("step") or [])]
    kn = []
    for kp in ds.knowledge:
        kn.append({"id": kp.data.get("id"), "class": kp.data.get("class"), "kind": kp.data.get("kind"),
                   "status": kp.data.get("status"), "file": ds.paths.rel(kp.path)})
    return {
        "ok": not ds.errors,
        "errors": len(ds.errors),
        "warnings": len(ds.warnings),
        "issues": [i.as_dict() for i in ds.issues],
        "guides": guides,
        "totals": {"guides": len(ds.guides), "sections": len(ds.sections), **counts(all_steps)},
        "knowledge": kn,
    }


def print_table(summ: dict) -> None:
    rows = [("Guía", "Secc.", "Pasos", "% verif.", "% sin verif.", "% disputa")]
    for g in summ["guides"]:
        rows.append((g["id"], str(len(g["sections"])), str(g["steps"]),
                     f"{g['pct_verified']:.1f}", f"{g['pct_unverified']:.1f}", f"{g['pct_disputed']:.1f}"))
    t = summ["totals"]
    rows.append(("TOTAL (pasos únicos)", str(t["sections"]), str(t["steps"]),
                 f"{t['pct_verified']:.1f}", f"{t['pct_unverified']:.1f}", f"{t['pct_disputed']:.1f}"))
    widths = [max(len(r[i]) for r in rows) for i in range(len(rows[0]))]
    sep = "-+-".join("-" * w for w in widths)
    for n, r in enumerate(rows):
        print(" | ".join(c.ljust(w) if i == 0 else c.rjust(w) for i, (c, w) in enumerate(zip(r, widths))))
        if n == 0 or n == len(rows) - 2:
            print(sep)
    print(f"Conocimiento: {len(summ['knowledge'])} páginas")


def main(argv: list[str] | None = None) -> int:
    setup_stdio()
    ap = argparse.ArgumentParser(description="Valida data/ contra schema/ y reglas semánticas.")
    ap.add_argument("--root", help="raíz alternativa (por defecto, el repo)")
    ap.add_argument("--json", action="store_true", help="salida JSON por stdout")
    ap.add_argument("--strict", action="store_true", help="los avisos cuentan como errores")
    args = ap.parse_args(argv)

    paths = Paths(args.root)
    ds = load_and_check(paths)
    summ = summary(ds)
    failed = bool(ds.errors) or (args.strict and bool(ds.warnings))
    if args.json:
        summ["ok"] = not failed
        print(json.dumps(summ, ensure_ascii=False, indent=2))
    else:
        for i in ds.issues:
            print(str(i), file=sys.stderr if i.level == "error" else sys.stdout)
        print_table(summ)
        print(f"{len(ds.errors)} errores, {len(ds.warnings)} avisos")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
