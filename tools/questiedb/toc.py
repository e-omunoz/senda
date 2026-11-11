"""Reader for QuestieDB's "baked" TOC metadata store.

Format (see QuestieDB src/read/baked.lua and src/meta/codec.lua):

* Every value is a ``## X-<key>: <value>`` line in ``QuestieDB_<Flavor>.toc``.
* A value longer than ``maxValueLength`` is Chunked: the base key holds ``~N~`` and the parts
  live in ``<key>-1`` .. ``<key>-N``; concatenating them yields the real value.
* ``X-<Type>-IDS``: base64 -> zlib (C_EncodingUtil CompressionMethod 1) -> CBOR array of IDs.
* ``X-<Type>-<id>-S``: base64 -> CBOR "Scalar row": {fieldIndex: value, ..., "p": presenceMask}.
  Bit (fieldIndex-1) of ``p`` says whether table field ``fieldIndex`` has a stored value.
* ``X-<Type>-<id>-<fieldIndex>``: base64 -> CBOR value of one table field.
"""

from __future__ import annotations

import base64
import re
import zlib

from . import cbor

_CHUNK_RE = re.compile(r"^~(\d+)~$")


def read_metadata(path) -> dict[str, str]:
    """Parse all ``## X-...: value`` lines of a TOC into {key-without-X-: value}."""
    out: dict[str, str] = {}
    with open(path, "r", encoding="utf-8", errors="replace") as fh:
        for line in fh:
            if not line.startswith("## X-"):
                continue
            sep = line.find(":", 5)
            if sep < 0:
                continue
            out[line[5:sep].strip()] = line[sep + 1:].strip()
    return out


class MetaStore:
    def __init__(self, metadata: dict[str, str]):
        self.meta = metadata

    def get(self, key: str) -> str | None:
        value = self.meta.get(key)
        if value is None or not value.startswith("~"):
            return value
        m = _CHUNK_RE.match(value)
        if not m:
            return value
        parts = []
        for i in range(1, int(m.group(1)) + 1):
            part = self.meta.get(f"{key}-{i}")
            if part is None:
                raise ValueError(f"metadata key {key} declares {m.group(1)} parts but part {i} is missing")
            parts.append(part)
        return "".join(parts)

    def ids(self, prefix: str) -> list[int]:
        encoded = self.get(f"{prefix}IDS")
        if encoded is None:
            raise KeyError(f"missing metadata key X-{prefix}IDS")
        return decode_ids(encoded)

    def entity(self, prefix: str, entity_id: int, types: dict[int, str]) -> dict[int, object] | None:
        """Decode one entity's raw fields {fieldIndex: value} (no normalization)."""
        stored = self.get(f"{prefix}{entity_id}-S")
        if stored is None:
            return None
        row = decode_value(stored)
        fields: dict[int, object] = {}
        presence = 0
        if isinstance(row, dict):
            presence = int(row.get("p", 0) or 0)
            for k, v in row.items():
                if isinstance(k, int):
                    fields[k] = v
        elif isinstance(row, list):  # contiguous 1..n row
            for i, v in enumerate(row, 1):
                if v is not None:
                    fields[i] = v
        for index, kind in types.items():
            if kind != "table":
                continue
            if not (presence >> (index - 1)) & 1:
                continue
            raw = self.get(f"{prefix}{entity_id}-{index}")
            if raw is not None:
                fields[index] = decode_value(raw)
        return fields


def decode_ids(encoded: str) -> list[int]:
    raw = base64.b64decode(encoded)
    try:
        data = zlib.decompress(raw)
    except zlib.error:
        data = zlib.decompress(raw, -15)  # raw deflate fallback
    ids = cbor.decode(data)
    if isinstance(ids, dict):
        ids = list(ids.values())
    return [int(i) for i in ids]


def decode_value(encoded: str):
    return cbor.decode(base64.b64decode(encoded))
