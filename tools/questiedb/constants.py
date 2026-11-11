"""Race/class bitmasks as used by QuestieDB for the Forever flavor.

Source: QuestieDB src/corrections/enum/constants.lua (raceMaskById) and expansions.lua
(Classic classKeys). Forever assigns Skyborne race IDs 95/96 to bits 32/33.
"""

RACE_MASK = {
    "Human": 1,
    "Orc": 2,
    "Dwarf": 4,
    "NightElf": 8,
    "Scourge": 16,
    "Tauren": 32,
    "Gnome": 64,
    "Troll": 128,
    "SkyborneAlliance": 1 << 32,
    "SkyborneHorde": 1 << 33,
}

RACE_FACTION = {
    "Human": "Alliance", "Dwarf": "Alliance", "NightElf": "Alliance", "Gnome": "Alliance",
    "SkyborneAlliance": "Alliance",
    "Orc": "Horde", "Scourge": "Horde", "Tauren": "Horde", "Troll": "Horde",
    "SkyborneHorde": "Horde",
}

ALLIANCE_MASK = sum(m for r, m in RACE_MASK.items() if RACE_FACTION[r] == "Alliance")
HORDE_MASK = sum(m for r, m in RACE_MASK.items() if RACE_FACTION[r] == "Horde")

_RACE_ALIASES = {
    "human": "Human", "orc": "Orc", "dwarf": "Dwarf", "nightelf": "NightElf",
    "night_elf": "NightElf", "night elf": "NightElf", "scourge": "Scourge", "undead": "Scourge",
    "tauren": "Tauren", "gnome": "Gnome", "troll": "Troll",
    "skyborne_alliance": "SkyborneAlliance", "skybornealliance": "SkyborneAlliance",
    "skyborne_horde": "SkyborneHorde", "skybornehorde": "SkyborneHorde",
}

CLASS_MASK = {
    "WARRIOR": 1,
    "PALADIN": 2,
    "HUNTER": 4,
    "ROGUE": 8,
    "PRIEST": 16,
    "SHAMAN": 64,
    "MAGE": 128,
    "WARLOCK": 256,
    "DRUID": 1024,
}

# Forever npcFlags (src/corrections/enum/expansions.lua, Forever block).
NPC_FLAGS = {
    "GOSSIP": 1, "QUEST_GIVER": 2, "VENDOR": 4, "FLIGHT_MASTER": 8, "TRAINER": 16,
    "SPIRIT_HEALER": 32, "SPIRIT_GUIDE": 64, "INNKEEPER": 128, "BANKER": 256,
    "PETITIONER": 512, "TABARD_DESIGNER": 1024, "BATTLEMASTER": 2048, "AUCTIONEER": 4096,
    "STABLEMASTER": 8192, "REPAIR": 16384,
}


def race_key(name: str, faction: str | None = None) -> str:
    """Normalize a race name ("Gnome", "night elf", "Skyborne") to a RACE_MASK key."""
    if name in RACE_MASK:
        return name
    low = name.strip().lower()
    if low == "skyborne":
        return "SkyborneHorde" if (faction or "").lower() == "horde" else "SkyborneAlliance"
    if low in _RACE_ALIASES:
        return _RACE_ALIASES[low]
    raise KeyError(f"unknown race {name!r}")


def race_mask(name: str, faction: str | None = None) -> int:
    return RACE_MASK[race_key(name, faction)]


def class_mask(name: str) -> int:
    key = name.strip().upper().replace(" ", "")
    if key not in CLASS_MASK:
        raise KeyError(f"unknown class {name!r}")
    return CLASS_MASK[key]


def races_in_mask(mask: int) -> list[str]:
    if not mask:
        return ["ALL"]
    out = [r for r, m in RACE_MASK.items() if mask & m]
    if mask & ALLIANCE_MASK == ALLIANCE_MASK and not mask & HORDE_MASK:
        return ["ALLIANCE"]
    if mask & HORDE_MASK == HORDE_MASK and not mask & ALLIANCE_MASK:
        return ["HORDE"]
    return out


def classes_in_mask(mask: int) -> list[str]:
    if not mask:
        return ["ALL"]
    return [c for c, m in CLASS_MASK.items() if mask & m]


def race_allowed(quest_races: int, race: str, faction: str | None = None) -> bool:
    return quest_races == 0 or bool(quest_races & race_mask(race, faction))


def class_allowed(quest_classes: int, cls: str) -> bool:
    return quest_classes == 0 or bool(quest_classes & class_mask(cls))
