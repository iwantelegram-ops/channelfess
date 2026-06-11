"""
MongoStorage — Pyrogram 2.0.x storage backend menggunakan MongoDB.

Di Pyrogram 2.0.x, storage fields adalah async methods dengan pola:
  await storage.dc_id()        # getter — return nilai
  await storage.dc_id(5)       # setter — simpan nilai

Collections:
  sessions  — auth data bot (dc_id, auth_key, user_id, dst)
  peers     — cache peer Telegram (untuk resolusi ID/username)
"""
import asyncio
import logging
import time
from typing import List, Tuple

from pyrogram.storage import Storage

log = logging.getLogger("fessbot.mongo_storage")


class MongoStorage(Storage):

    def __init__(self, name: str, collection_session, collection_peers):
        super().__init__(name)
        self._name      = name
        self._sessions  = collection_session
        self._peers_col = collection_peers

        # In-memory cache
        self._dc_id     = 2
        self._api_id    = None
        self._test_mode = False
        self._auth_key  = b""
        self._date      = 0
        self._user_id   = None
        self._is_bot    = True

    # ── Load / Save ────────────────────────────────────────

    def _load(self):
        doc = self._sessions.find_one({"_id": self._name})
        if doc:
            self._dc_id     = doc.get("dc_id",     2)
            self._api_id    = doc.get("api_id",     None)
            self._test_mode = doc.get("test_mode",  False)
            raw_key         = doc.get("auth_key",   [])
            self._auth_key  = bytes(raw_key) if raw_key else b""
            self._date      = doc.get("date",       0)
            self._user_id   = doc.get("user_id",    None)
            self._is_bot    = doc.get("is_bot",     True)
            log.info(f"[MongoStorage] Session '{self._name}' loaded "
                     f"(user_id={self._user_id})")
        else:
            log.info(f"[MongoStorage] Session '{self._name}' tidak ditemukan, mulai baru.")

    def _dump(self):
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

    # ── Storage interface ──────────────────────────────────

    async def open(self):
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, self._load)

    async def save(self):
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, self._dump)

    async def close(self):
        await self.save()

    async def delete(self):
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(
            None, lambda: self._sessions.delete_one({"_id": self._name})
        )

    # ── Peer cache ─────────────────────────────────────────

    async def update_peers(self, peers: List[Tuple[int, int, str, str, str]]):
        if not peers:
            return
        loop = asyncio.get_event_loop()

        def _write():
            for peer in peers:
                peer_id, access_hash, peer_type, username, phone = peer
                self._peers_col.update_one(
                    {"_id": peer_id},
                    {"$set": {
                        "access_hash": access_hash,
                        "type":        peer_type,
                        "username":    username.lower() if username else None,
                        "phone":       phone,
                        "updated_at":  int(time.time()),
                    }},
                    upsert=True,
                )

        await loop.run_in_executor(None, _write)

    async def get_peer_by_id(self, peer_id: int):
        loop = asyncio.get_event_loop()
        doc = await loop.run_in_executor(
            None, lambda: self._peers_col.find_one({"_id": peer_id})
        )
        if not doc:
            raise KeyError(f"ID {peer_id} not in peer cache")
        return doc["_id"], doc.get("access_hash"), doc.get("type")

    async def get_peer_by_username(self, username: str):
        loop = asyncio.get_event_loop()
        doc = await loop.run_in_executor(
            None, lambda: self._peers_col.find_one({"username": username.lower()})
        )
        if not doc:
            raise KeyError(f"@{username} not in peer cache")
        return doc["_id"], doc.get("access_hash"), doc.get("type")

    async def get_peer_by_phone_number(self, phone_number: str):
        loop = asyncio.get_event_loop()
        doc = await loop.run_in_executor(
            None, lambda: self._peers_col.find_one({"phone": phone_number})
        )
        if not doc:
            raise KeyError(f"Phone {phone_number} not in peer cache")
        return doc["_id"], doc.get("access_hash"), doc.get("type")

    # ── Async getter/setter methods (Pyrogram 2.0.106) ──
    #
    # Pyrogram menggunakan sentinel `object` sebagai default:
    #   await storage.dc_id()        → getter (value is object)
    #   await storage.dc_id(5)       → setter (value is not object)

    async def dc_id(self, value=object):
        if value is object:
            return self._dc_id
        self._dc_id = value

    async def api_id(self, value=object):
        if value is object:
            return self._api_id
        self._api_id = value

    async def test_mode(self, value=object):
        if value is object:
            return self._test_mode
        self._test_mode = value

    async def auth_key(self, value=object):
        if value is object:
            return self._auth_key
        self._auth_key = value

    async def date(self, value=object):
        if value is object:
            return self._date
        self._date = value

    async def user_id(self, value=object):
        if value is object:
            return self._user_id
        self._user_id = value

    async def is_bot(self, value=object):
        if value is object:
            return self._is_bot
        self._is_bot = value
