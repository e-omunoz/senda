"""Choose the quest database for tools/enrich.py, tools/verify.py and tools/lookup.py.

    from foreverdb.backend import add_db_arguments, open_db
    add_db_arguments(parser)                 # --db, --questiedb, --foreverdb
    db = open_db(args, faction="Alliance")

``--db auto`` (default, or env SENDA_DB): QuestieDB when it is installed locally (same behaviour
as before), forever-db otherwise (CI, or a machine without the game). ``--db questiedb`` and
``--db foreverdb`` force one. The chosen database says which it is in ``db.SOURCE``
("questiedb" / "foreverdb") and what it lacks in ``db.MISSING``.
"""

from __future__ import annotations

import os
import sys

from questiedb import QuestDB, resolve_questiedb

from .db import ForeverDB, resolve_foreverdb

CHOICES = ("auto", "questiedb", "foreverdb")


def add_db_arguments(ap) -> None:
    ap.add_argument("--db", choices=CHOICES, default=os.environ.get("SENDA_DB") or "auto",
                    help="quest data: auto (QuestieDB if installed, else forever-db), questiedb or foreverdb "
                         "(default: env SENDA_DB or auto)")
    if not any("--questiedb" in a.option_strings for a in ap._actions):
        ap.add_argument("--questiedb", help="QuestieDB addon folder (or env SENDA_QUESTIEDB)")
    ap.add_argument("--foreverdb", help="forever-db folder (or env SENDA_FOREVERDB; default .cache/foreverdb)")


def pick(backend: str = "auto", questiedb=None, foreverdb=None) -> str:
    """Which backend ``open_db`` would use: "questiedb" or "foreverdb" (raises if neither exists)."""
    if backend in ("questiedb", "foreverdb"):
        return backend
    try:
        resolve_questiedb(questiedb)
        return "questiedb"
    except FileNotFoundError as q_err:
        try:
            resolve_foreverdb(foreverdb)
            return "foreverdb"
        except FileNotFoundError as f_err:
            raise FileNotFoundError(f"no quest database: {q_err}; {f_err}") from None


def open_db(args=None, faction: str = "Alliance", rebuild: bool = False, *, backend: str | None = None,
            questiedb=None, foreverdb=None, quiet: bool = False):
    """Open QuestieDB or forever-db. ``args`` is an argparse namespace from :func:`add_db_arguments`."""
    backend = backend or getattr(args, "db", None) or os.environ.get("SENDA_DB") or "auto"
    questiedb = questiedb or getattr(args, "questiedb", None)
    foreverdb = foreverdb or getattr(args, "foreverdb", None)
    which = pick(backend, questiedb, foreverdb)
    if which == "questiedb":
        db = QuestDB.open(questiedb, faction=faction, rebuild=rebuild)
    else:
        db = ForeverDB.open(foreverdb, faction=faction)
        if backend == "auto" and not quiet:
            print(f"[db] QuestieDB not installed: using forever-db {db.info.get('version')} "
                  f"(lacks {', '.join(sorted(db.MISSING))})", file=sys.stderr)
    return db


def source_of(db) -> str:
    """"questiedb" or "foreverdb" (QuestDB has no SOURCE attribute)."""
    return getattr(db, "SOURCE", "questiedb")


def missing(db) -> frozenset:
    return getattr(db, "MISSING", frozenset())
