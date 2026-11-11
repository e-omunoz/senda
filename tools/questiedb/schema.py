"""Field numbering for each QuestieDB entity type, read from src/meta/<entity>Meta.lua."""

from __future__ import annotations

import re
from pathlib import Path

ENTITY_TYPES = ("Quest", "Npc", "Item", "Object")
META_FILES = {"Quest": "questMeta.lua", "Npc": "npcMeta.lua", "Item": "itemMeta.lua", "Object": "objectMeta.lua"}

_BLOCK_RE = r"{name}\s*=\s*\{{(?P<body>[^}}]*)\}}"
_PAIR_RE = re.compile(r"\[(\d+)\]\s*=\s*'([A-Za-z0-9_]+)'")


class EntitySchema:
    def __init__(self, entity: str, names: dict[int, str], types: dict[int, str]):
        self.entity = entity
        self.prefix = f"{entity}-"
        self.names = names
        self.types = types
        self.keys = {v: k for k, v in names.items()}

    def __repr__(self):
        return f"EntitySchema({self.entity}, {len(self.names)} fields)"


def _block(text: str, name: str) -> dict[int, str]:
    m = re.search(_BLOCK_RE.format(name=name), text)
    if not m:
        raise ValueError(f"block {name} not found")
    return {int(k): v for k, v in _PAIR_RE.findall(m.group("body"))}


def load_schema(questiedb_root: Path) -> dict[str, EntitySchema]:
    out = {}
    for entity in ENTITY_TYPES:
        text = (Path(questiedb_root) / "src" / "meta" / META_FILES[entity]).read_text(encoding="utf-8")
        names = _block(text, "names")
        types = _block(text, "types")
        if set(names) != set(types):
            raise ValueError(f"{entity}: names/types mismatch in meta")
        out[entity] = EntitySchema(entity, names, types)
    return out
