"""
MongoStorage — Pyrogram 2.0.x storage backend menggunakan MongoDB.
Menggantikan SQLite session file sehingga sesi persisten di semua device.

Collections yang digunakan (dalam database 'fessbot'):
  - sessions   : satu dokumen per session_name, menyimpan auth data
  - peers      : cache peer (user/channel/group) untuk resolusi ID

Cara kerja:
  - Saat bot start, load session dari MongoDB (bukan dari file .session)
  - Saat session diperbarui Pyrogram, langsung disimpan ke MongoDB
  - Peer cache juga disimpan ke MongoDB agar persist antar restart
"""
import asyncio
import logging
import struct
import time
from typing import List, Tuple, Any

from pyrogram.storage import Storage

log = logging.getLogger("fessbot.mongo_storage")

# Sentinel untuk membedakan "belum diload" vs None
_UNSET = object()


class MongoStorage(Storage):
    """
    Storage backend MongoDB untuk Pyrogram 2.0.x.
    Gunakan sebagai pengganti nama session string di Client().
    """

    SESSION_KEY = "session_data"
    PEER_PREFIX = "peer_"

    def __init__(self, name: str, collection_session, collection_peers):
        """
        name              : nama unik session (misal "fessbot_session")
        collection_session: pymongo Collection untuk data session
        collection_peers  : pymongo Collection untuk peer cache
        """
        super().__init__(name)
        self._name      = name
        self._sessions  = collection_session
        self._peers_col = collection_peers

        # Cache in-memory
        self._dc_id     = _UNSET
        self._api_id    = _UNSET
        self._test_mode = _UNSET
        self._auth_key  = _UNSET
        self._date      = _UNSET
        self._user_id   = _UNSET
        self._is_bot    = _UNSET

    # ─── Internal helpers ──────────────────────────────────

    def _load_session(self):
        """Baca session dari MongoDB ke cache memory."""
        doc = self._sessions.find_one({"_id": self._name})
        if doc:
            self._dc_id     = doc.get("dc_id",     2)
            self._api_id    = doc.get("api_id",     None)
            self._test_mode = doc.get("test_mode",  False)
            self._auth_key  = bytes(doc["auth_key"]) if doc.get("auth_key") else b""
            self._date      = doc.get("date",       0)
            self._user_id   = doc.get("user_id",    None)
            self._is_bot    = doc.get("is_bot",     True)
            log.info(f"[MongoStorage] Session '{self._name}' loaded from MongoDB "
                     f"(user_id={self._user_id})")
        else:
            # Session baru / belum ada
            self._dc_id     = 2
            self._api_id    = None
            self._test_mode = False
            self._auth_key  = b""
            self._date      = 0
            self._user_id   = None
            self._is_bot    = True
            log.info(f"[MongoStorage] Session '{self._name}' tidak ditemukan, mulai baru.")

    def _save_session(self):
        """Tulis cache memory ke MongoDB."""
        if self._auth_key is _UNSET:
            return
        self._sessions.update_one(
            {"_id": self._name},
            {"$set": {
                "dc_id":     self._dc_id,
                "api_id":    self._api_id,
                "test_mode": self._test_mode,
                "auth_key":  list(self._auth_key) if self._auth_key else [],
                "date":      self._date,
                "user_id":   self._user_id,
                "is_bot":    self._is_bot,
            }},
            upsert=True,
        )

    # ─── Storage interface ────────────────────────────────

    async def open(self):
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, self._load_session)

    async def save(self):
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, self._save_session)

    async def close(self):
        await self.save()

    async def delete(self):
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(
            None,
            lambda: self._sessions.delete_one({"_id": self._name})
        )

    # ─── Peer cache ───────────────────────────────────────

    async def update_peers(self, peers: List[Tuple[int, int, str, str, str]]):
        """
        peers: list of (id, access_hash, type, username, phone_number)
        """
        if not peers:
            return
        loop = asyncio.get_event_loop()

        def _write():
            for peer in peers:
                peer_id, access_hash, peer_type, username, phone = peer
                doc = {
                    "_id":         peer_id,
                    "access_hash": access_hash,
                    "type":        peer_type,
                    "username":    username.lower() if username else None,
                    "phone":       phone,
                    "updated_at":  int(time.time()),
                }
                self._peers_col.update_one(
                    {"_id": peer_id},
                    {"$set": doc},
                    upsert=True,
                )

        await loop.run_in_executor(None, _write)

    async def get_peer_by_id(self, peer_id: int):
        loop = asyncio.get_event_loop()
        doc = await loop.run_in_executor(
            None,
            lambda: self._peers_col.find_one({"_id": peer_id})
        )
        if not doc:
            raise KeyError(f"Peer {peer_id} not found")
        return doc["_id"], doc.get("access_hash"), doc.get("type")

    async def get_peer_by_username(self, username: str):
        loop = asyncio.get_event_loop()
        doc = await loop.run_in_executor(
            None,
            lambda: self._peers_col.find_one({"username": username.lower()})
        )
        if not doc:
            raise KeyError(f"Peer @{username} not found")
        return doc["_id"], doc.get("access_hash"), doc.get("type")

    async def get_peer_by_phone_number(self, phone_number: str):
        loop = asyncio.get_event_loop()
        doc = await loop.run_in_executor(
            None,
            lambda: self._peers_col.find_one({"phone": phone_number})
        )
        if not doc:
            raise KeyError(f"Peer phone {phone_number} not found")
        return doc["_id"], doc.get("access_hash"), doc.get("type")

    # ─── Properties (baca/tulis cache + auto-save) ────────

    @property
    def dc_id(self):
        return self._dc_id if self._dc_id is not _UNSET else 2

    @dc_id.setter
    def dc_id(self, value):
        self._dc_id = value

    @property
    def api_id(self):
        return self._api_id if self._api_id is not _UNSET else None

    @api_id.setter
    def api_id(self, value):
        self._api_id = value

    @property
    def test_mode(self):
        return self._test_mode if self._test_mode is not _UNSET else False

    @test_mode.setter
    def test_mode(self, value):
        self._test_mode = value

    @property
    def auth_key(self):
        return self._auth_key if self._auth_key is not _UNSET else b""

    @auth_key.setter
    def auth_key(self, value):
        self._auth_key = value

    @property
    def date(self):
        return self._date if self._date is not _UNSET else 0

    @date.setter
    def date(self, value):
        self._date = value

    @property
    def user_id(self):
        return self._user_id if self._user_id is not _UNSET else None

    @user_id.setter
    def user_id(self, value):
        self._user_id = value

    @property
    def is_bot(self):
        return self._is_bot if self._is_bot is not _UNSET else True

    @is_bot.setter
    def is_bot(self, value):
        self._is_bot = value
