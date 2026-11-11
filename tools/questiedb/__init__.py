"""Local reader for the user's installed QuestieDB (WoW Forever flavor).

    from questiedb import QuestDB
    db = QuestDB.open()            # --questiedb path / SENDA_QUESTIEDB env / default install
    db.quest(179); db.npc(658); db.npc_quests(658)

QuestieDB is "all rights reserved": decoded data is cached only in <repo>/.cache/questiedb/
(gitignored) and must never be written elsewhere in the repository or committed.
"""

from .db import QuestDB, resolve_questiedb, CACHE_DIR  # noqa: F401
from . import constants  # noqa: F401
