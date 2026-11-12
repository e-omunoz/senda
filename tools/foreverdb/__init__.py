"""forever-db (Polestar's open quest data for WoW: Forever) with the QuestDB interface.

    from foreverdb import ForeverDB, open_db
    db = ForeverDB.open()          # --foreverdb path / SENDA_FOREVERDB env / <repo>/.cache/foreverdb
    db.quest(179); db.npc(234)     # same shapes as questiedb.QuestDB
    db = open_db(args)             # QuestieDB if installed, else forever-db (see backend.py)

Download the pinned release with ``python tools/fetch_foreverdb.py`` (version in tools/foreverdb/PIN).
forever-db is GPL-3.0 (tables) / CC BY 4.0 (its own layer): see THIRD_PARTY.md.
"""

from .db import DEFAULT_DIR, ForeverDB, Frames, resolve_foreverdb  # noqa: F401
from .backend import add_db_arguments, missing, open_db, pick, source_of  # noqa: F401
