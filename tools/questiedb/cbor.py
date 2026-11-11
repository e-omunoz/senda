"""Minimal CBOR (RFC 8949) decoder, enough for QuestieDB's baked TOC store.

QuestieDB serializes values with the WoW client's C_EncodingUtil.SerializeCBOR. Lua strings
come out as CBOR byte strings (major type 2); this decoder turns them into Python ``str``
(UTF-8, replacing invalid bytes). Lua tables with keys 1..n become CBOR arrays (Python lists,
whose index 0 is Lua key 1); any other table becomes a map (Python dict).
"""

from __future__ import annotations

import struct

__all__ = ["decode", "CBORError"]


class CBORError(ValueError):
    pass


_BREAK = object()


class _Decoder:
    __slots__ = ("data", "pos")

    def __init__(self, data: bytes):
        self.data = data
        self.pos = 0

    def _take(self, n: int) -> bytes:
        end = self.pos + n
        if end > len(self.data):
            raise CBORError("truncated CBOR input")
        chunk = self.data[self.pos:end]
        self.pos = end
        return chunk

    def _arg(self, info: int) -> int | None:
        if info < 24:
            return info
        if info == 24:
            return self._take(1)[0]
        if info == 25:
            return struct.unpack(">H", self._take(2))[0]
        if info == 26:
            return struct.unpack(">I", self._take(4))[0]
        if info == 27:
            return struct.unpack(">Q", self._take(8))[0]
        if info == 31:
            return None  # indefinite length
        raise CBORError(f"reserved additional info {info}")

    def item(self):
        if self.pos >= len(self.data):
            raise CBORError("unexpected end of CBOR input")
        initial = self.data[self.pos]
        self.pos += 1
        major, info = initial >> 5, initial & 0x1F

        if major == 7:
            if info == 20:
                return False
            if info == 21:
                return True
            if info in (22, 23):
                return None
            if info == 25:
                return _half(self._take(2))
            if info == 26:
                return struct.unpack(">f", self._take(4))[0]
            if info == 27:
                return struct.unpack(">d", self._take(8))[0]
            if info == 31:
                return _BREAK
            if info < 24:
                return None  # unassigned simple value
            if info == 24:
                self._take(1)
                return None
            raise CBORError(f"unsupported simple value {info}")

        arg = self._arg(info)
        if major == 0:
            return arg
        if major == 1:
            return -1 - arg
        if major in (2, 3):
            if arg is None:
                parts = []
                while True:
                    part = self.item()
                    if part is _BREAK:
                        break
                    parts.append(part.encode("utf-8") if isinstance(part, str) else part)
                raw = b"".join(parts)
            else:
                raw = self._take(arg)
            return raw.decode("utf-8", errors="replace")
        if major == 4:
            out = []
            if arg is None:
                while True:
                    value = self.item()
                    if value is _BREAK:
                        break
                    out.append(value)
            else:
                for _ in range(arg):
                    out.append(self.item())
            return out
        if major == 5:
            out = {}
            count = 0
            while arg is None or count < arg:
                key = self.item()
                if key is _BREAK:
                    break
                if isinstance(key, list):
                    key = tuple(key)
                out[key] = self.item()
                count += 1
            return out
        if major == 6:
            return self.item()  # ignore tags
        raise CBORError(f"bad major type {major}")


def _half(b: bytes) -> float:
    h = (b[0] << 8) | b[1]
    exp = (h >> 10) & 0x1F
    mant = h & 0x3FF
    if exp == 0:
        val = mant * 2.0 ** -24
    elif exp == 31:
        val = float("inf") if mant == 0 else float("nan")
    else:
        val = (mant + 1024) * 2.0 ** (exp - 25)
    return -val if h & 0x8000 else val


def decode(data: bytes):
    """Decode one CBOR data item. Trailing bytes are an error."""
    dec = _Decoder(data)
    value = dec.item()
    if value is _BREAK:
        raise CBORError("unexpected break")
    if dec.pos != len(data):
        raise CBORError(f"{len(data) - dec.pos} trailing bytes after CBOR item")
    return value
