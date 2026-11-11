"""Readers for QuestieDB support data (zones, enums) and for corrections not baked into the TOC.

Correction layers and how this package treats them:

* Static Corrections (QuestieDB ``*Fixes.lua:Load``) are folded into the TOC at generation time;
  the installed copies are stripped to ``return {}``. Nothing to do: the decoded TOC has them.
* Dynamic Corrections (``LoadDynamic`` / ``LoadFactionFixes``) depend on the player's faction
  (and sometimes class). We evaluate their literal tables for the chosen faction; any field whose
  value depends on runtime state (e.g. ``({...})[playerClass]``) is skipped and reported.
* Questie's own layer (``Questie/Database/Corrections``): the quest blacklist
  (``QuestieQuestBlacklist``) is read and exposed as ``hidden`` flags. Questie's policy
  corrections (Darkmoon Faire location, gathering-node display, TBC content phases) do not
  affect Forever leveling data and are not applied.
"""

from __future__ import annotations

import re
from pathlib import Path

from . import luaparse
from .luaparse import UNRESOLVED

_ZONE_BLOCK_RE = re.compile(r"ZoneDB\.private\.(\w+)\s*=\s*\[\[return\s*(\{.*?\n\})\]\]", re.S)
_ZONE_LINE_RE = re.compile(r"^\s*\[(-?\d+)\]\s*=\s*(-?\d+)\s*,?\s*(?:--\s*(.*))?$")


def _zone_file(path: Path) -> tuple[dict[str, dict[int, int]], dict[int, str]]:
    text = path.read_text(encoding="utf-8", errors="replace")
    tables: dict[str, dict[int, int]] = {}
    comments: dict[int, str] = {}
    for m in _ZONE_BLOCK_RE.finditer(text):
        table: dict[int, int] = {}
        for line in m.group(2).splitlines():
            lm = _ZONE_LINE_RE.match(line)
            if lm:
                table[int(lm.group(1))] = int(lm.group(2))
                if lm.group(3):
                    comments.setdefault(int(lm.group(1)), lm.group(3).strip())
        tables[m.group(1)] = table
    return tables, comments


class Zones:
    """areaId <-> uiMapID tables of the Forever flavor, plus names from the table comments."""

    def __init__(self, root: Path):
        zdir = Path(root) / "support" / "Forever" / "Zones"
        a2u, a2u_names = _zone_file(zdir / "areaIdToUiMapId.lua")
        u2a, u2a_names = _zone_file(zdir / "uiMapIdToAreaId.lua")
        sub, sub_names = _zone_file(zdir / "subZoneToParentZone.lua")
        self.area_to_uimap = {**a2u.get("areaIdToUiMapId", {}), **a2u.get("areaIdToUiMapIdOverride", {})}
        self.uimap_to_area = {**u2a.get("uiMapIdToAreaId", {}), **u2a.get("uiMapIdToAreaIdOverride", {})}
        self.sub_to_parent = {**sub.get("subZoneToParentZone", {}), **sub.get("subZoneToParentZoneOverride", {})}
        # Area names: "Anvilmar -> Dun Morogh" => "Anvilmar".
        self.area_names: dict[int, str] = {}
        for src in (sub_names, a2u_names):
            for area, comment in src.items():
                name = comment.split("->")[0].strip()
                if name and not name.startswith(("Referenced", "Synthetic", "Existing", "Deeprun", "Hall of", "Champions'")):
                    self.area_names.setdefault(area, name)
        self.uimap_names: dict[int, str] = {}
        for uimap, comment in u2a_names.items():
            if not comment.startswith("Referenced"):
                self.uimap_names[uimap] = comment.split("->")[0].strip()
        for uimap, area in self.uimap_to_area.items():
            if uimap not in self.uimap_names and area in self.area_names:
                self.uimap_names[uimap] = self.area_names[area]
        self.uimap_names.setdefault(1414, "Kalimdor")
        self.uimap_names.setdefault(1415, "Eastern Kingdoms")

    def uimap(self, area_id: int) -> int | None:
        if area_id in self.area_to_uimap:
            return self.area_to_uimap[area_id] or None
        seen = set()
        a = area_id
        while a in self.sub_to_parent and a not in seen:
            seen.add(a)
            a = self.sub_to_parent[a]
            if a in self.area_to_uimap:
                return self.area_to_uimap[a] or None
        return None

    def to_dict(self):
        return {"area_to_uimap": self.area_to_uimap, "uimap_to_area": self.uimap_to_area,
                "sub_to_parent": self.sub_to_parent, "area_names": self.area_names,
                "uimap_names": self.uimap_names}


# --------------------------------------------------------------------------------------------
# Enums and dynamic corrections
# --------------------------------------------------------------------------------------------

_ENUM_RE = re.compile(r"constants\.(\w+)\s*=\s*\{")

# Locals used by correction files -> enum table name (QuestieDB.<x> aliases).
_ENV_ALIASES = {
    "zoneIDs": "zoneIDs", "factionIDs": "factionIDs", "sortKeys": "sortKeys",
    "specialFlags": "specialFlags", "questFlags": "questFlags", "profKeys": "professionKeys",
    "specKeys": "specializationKeys", "rankKeys": "rankNames", "phases": "phases",
    "waypointPresets": "waypointPresets", "iconTypes": "iconTypes", "itemClasses": "itemClasses",
}


def load_enums(root: Path) -> dict[str, dict]:
    enums: dict[str, dict] = {}
    for path in sorted((Path(root) / "src" / "corrections" / "enum").glob("*.lua")):
        if path.name in ("constants.lua", "expansions.lua"):
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        for m in _ENUM_RE.finditer(text):
            try:
                value, _ = luaparse.parse_table_at(text, m.end() - 1)
            except luaparse.LuaParseError:
                continue
            enums[m.group(1)] = dict(value)
    return enums


def _race_keys():
    from .constants import RACE_MASK, ALLIANCE_MASK, HORDE_MASK
    return {
        "NONE": 0, "HUMAN": RACE_MASK["Human"], "ORC": RACE_MASK["Orc"], "DWARF": RACE_MASK["Dwarf"],
        "NIGHT_ELF": RACE_MASK["NightElf"], "UNDEAD": RACE_MASK["Scourge"], "TAUREN": RACE_MASK["Tauren"],
        "GNOME": RACE_MASK["Gnome"], "TROLL": RACE_MASK["Troll"], "GOBLIN": 256,
        "SKYBORNE_ALLIANCE": RACE_MASK["SkyborneAlliance"], "SKYBORNE_HORDE": RACE_MASK["SkyborneHorde"],
        "ALL_ALLIANCE": ALLIANCE_MASK, "ALL_HORDE": HORDE_MASK,
    }


def _class_keys():
    from .constants import CLASS_MASK
    return {"NONE": 0, **CLASS_MASK, "ALL_CLASSES": 1503}


def make_env(schemas, enums):
    tables = {
        "questKeys": schemas["Quest"].keys, "npcKeys": schemas["Npc"].keys,
        "itemKeys": schemas["Item"].keys, "objectKeys": schemas["Object"].keys,
        "raceIDs": _race_keys(), "raceKeys": _race_keys(), "classIDs": _class_keys(),
        "classKeys": _class_keys(),
    }
    from .constants import NPC_FLAGS
    tables["npcFlags"] = {"NONE": 0, **NPC_FLAGS}
    for alias, enum_name in _ENV_ALIASES.items():
        if enum_name in enums:
            tables[alias] = enums[enum_name]

    def env(path):
        if len(path) != 2 or path[0] not in tables:
            return UNRESOLVED
        value = tables[path[0]].get(path[1], UNRESOLVED)
        return value

    return env


_DYN_FUNC_RE = re.compile(r"function\s+\w+:(LoadDynamic|LoadFactionFixes)\s*\(\s*\)")
_DATATYPE_BY_FILE = (("Quest", "Quest"), ("NPC", "Npc"), ("Npc", "Npc"), ("Item", "Item"), ("Object", "Object"))


def _correction_files(root: Path) -> list[Path]:
    """Forever correction providers in manifest order (legacy first, then authored Forever)."""
    base = Path(root) / "src" / "corrections" / "Forever"
    order = ["legacy/classicQuestFixes.lua", "legacy/classicNPCFixes.lua", "legacy/classicItemFixes.lua",
             "legacy/classicObjectFixes.lua", "foreverQuestFixes.lua", "foreverNPCFixes.lua",
             "foreverItemFixes.lua", "foreverObjectFixes.lua"]
    return [base / p for p in order if (base / p).exists()]


def load_dynamic_corrections(root: Path, schemas, enums, faction: str = "Alliance"):
    """Return ({datatype: {id: {fieldIndex: value}}}, skipped[list of (datatype, id, field, file)])."""
    env = make_env(schemas, enums)
    out: dict[str, dict[int, dict[int, object]]] = {"Quest": {}, "Npc": {}, "Item": {}, "Object": {}}
    skipped = []
    for path in _correction_files(root):
        datatype = next(dt for key, dt in _DATATYPE_BY_FILE if key in path.name)
        text = path.read_text(encoding="utf-8", errors="replace")
        fm = _DYN_FUNC_RE.search(text)
        if not fm:
            continue
        body = text[fm.end():]
        tables = []
        fac = re.search(r"local\s+(\w+?)" + faction + r"\s*=\s*\{", body)
        if fac:
            tables.append(fm.end() + fac.end() - 1)
        else:
            rm = re.search(r"\breturn\s*\{", body)
            if rm:
                tables.append(fm.end() + rm.end() - 1)
        for offset in tables:
            value, _ = luaparse.parse_table_at(text, offset, env)
            for entity_id, fields in value.items():
                if not isinstance(entity_id, int) or not isinstance(fields, dict):
                    continue
                target = out[datatype].setdefault(entity_id, {})
                for field, fval in fields.items():
                    if not isinstance(field, int) or not luaparse.is_resolved(fval):
                        skipped.append((datatype, entity_id, field, path.name))
                        continue
                    target[field] = luaparse.to_py(fval)
    return out, skipped


def load_questie_blacklist(questie_root: Path | None) -> dict[int, str]:
    """{questId: "hidden" | "hide_on_map"} from Questie's QuestieQuestBlacklist:Load()."""
    if questie_root is None:
        return {}
    path = Path(questie_root) / "Database" / "Corrections" / "QuestieQuestBlacklist.lua"
    if not path.exists():
        return {}
    text = path.read_text(encoding="utf-8", errors="replace")
    m = re.search(r"local\s+questsToBlacklist\s*=\s*\{", text)
    if not m:
        return {}

    def env(p):
        if p == ["HIDE_ON_MAP"]:
            return "HIDE_ON_MAP"
        return UNRESOLVED

    value, _ = luaparse.parse_table_at(text, m.end() - 1, env)
    out = {}
    for qid, flag in value.items():
        if not isinstance(qid, int):
            continue
        if flag is True:
            out[qid] = "hidden"
        elif flag == "HIDE_ON_MAP":
            out[qid] = "hide_on_map"
    return out
