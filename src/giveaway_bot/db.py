from __future__ import annotations

from datetime import datetime
import asyncio
import aiomysql
from typing import Any, Optional, Callable, Awaitable

MYSQL_DUPLICATE_KEY = 1062
MYSQL_LOCK_WAIT_TIMEOUT = 1205
MYSQL_DEADLOCK = 1213
TRANSIENT = {MYSQL_LOCK_WAIT_TIMEOUT, MYSQL_DEADLOCK}

def _mysql_err_code(exc: Exception) -> Optional[int]:
    try:
        return int(getattr(exc, "args", [None])[0])
    except Exception:
        return None

async def with_mysql_retry(fn: Callable[[], Awaitable[Any]], *, attempts: int = 5, base_delay: float = 0.2):
    delay = base_delay
    for i in range(attempts):
        try:
            return await fn()
        except Exception as e:
            code = _mysql_err_code(e)
            if code in TRANSIENT and i < attempts - 1:
                await asyncio.sleep(delay)
                delay = min(delay * 2, 2.0)
                continue
            raise

class Database:
    def __init__(self, host: str, port: int, user: str, password: str, db: str):
        self._pool: Optional[aiomysql.Pool] = None
        self._cfg = dict(host=host, port=port, user=user, password=password, db=db, autocommit=True)

    async def connect(self):
        self._pool = await aiomysql.create_pool(**self._cfg, minsize=1, maxsize=10)

    async def close(self):
        if self._pool:
            self._pool.close()
            await self._pool.wait_closed()

    async def exec(self, sql: str, args: tuple[Any, ...] = ()):
        assert self._pool
        async def _do():
            async with self._pool.acquire() as conn:
                async with conn.cursor() as cur:
                    await cur.execute(sql, args)
                    return cur.rowcount
        return await with_mysql_retry(_do)

    async def fetchone(self, sql: str, args: tuple[Any, ...] = ()):
        assert self._pool
        async def _do():
            async with self._pool.acquire() as conn:
                async with conn.cursor(aiomysql.DictCursor) as cur:
                    await cur.execute(sql, args)
                    return await cur.fetchone()
        return await with_mysql_retry(_do)

    async def fetchall(self, sql: str, args: tuple[Any, ...] = ()):
        assert self._pool
        async def _do():
            async with self._pool.acquire() as conn:
                async with conn.cursor(aiomysql.DictCursor) as cur:
                    await cur.execute(sql, args)
                    return await cur.fetchall()
        return await with_mysql_retry(_do)

    # --- Logging / channels ---
    async def log_event(self, event_type: str, channel_id: int | None, payload_json: str | None):
        await self.exec(
            "INSERT INTO event_log(channel_id, event_type, payload) VALUES(%s,%s,%s)",
            (channel_id, event_type, payload_json),
        )

    async def upsert_channel(self, channel_id: int, login: str, display_name: str | None):
        await self.exec(
            "INSERT INTO channels(id, login, display_name) VALUES(%s,%s,%s) "
            "ON DUPLICATE KEY UPDATE login=VALUES(login), display_name=VALUES(display_name)",
            (channel_id, login, display_name),
        )

    # --- sessions ---
    async def open_session(self, channel_id: int, started_at: datetime, title: str | None, category: str | None) -> int:
        await self.exec(
            "UPDATE stream_sessions SET is_live=0, ended_at=IFNULL(ended_at,%s) "
            "WHERE channel_id=%s AND is_live=1",
            (started_at, channel_id),
        )
        await self.exec(
            "INSERT INTO stream_sessions(channel_id, started_at, title, category, is_live) "
            "VALUES(%s,%s,%s,%s,1)",
            (channel_id, started_at, title, category),
        )
        row = await self.fetchone(
            "SELECT session_id FROM stream_sessions WHERE channel_id=%s AND is_live=1 ORDER BY session_id DESC LIMIT 1",
            (channel_id,),
        )
        return int(row["session_id"])

    async def close_session(self, channel_id: int, ended_at: datetime):
        await self.exec(
            "UPDATE stream_sessions SET is_live=0, ended_at=%s WHERE channel_id=%s AND is_live=1",
            (ended_at, channel_id),
        )

    async def current_session_id(self, channel_id: int) -> int | None:
        row = await self.fetchone(
            "SELECT session_id FROM stream_sessions WHERE channel_id=%s AND is_live=1 ORDER BY session_id DESC LIMIT 1",
            (channel_id,),
        )
        return int(row["session_id"]) if row else None

    # --- chat / heartbeats ---
    async def record_chat_message(
        self,
        channel_id: int,
        session_id: int | None,
        user_login: str,
        user_display: str | None,
        message: str,
        msg_ts: datetime,
        raw_tags: str | None,
    ):
        await self.exec(
            "INSERT INTO chat_messages(channel_id, session_id, user_login, user_display, message, msg_ts, raw_tags) "
            "VALUES(%s,%s,%s,%s,%s,%s,%s)",
            (channel_id, session_id, user_login, user_display, message, msg_ts, raw_tags),
        )
        await self.exec(
            "INSERT INTO activity_heartbeats(channel_id, session_id, user_login, last_msg_ts) "
            "VALUES(%s,%s,%s,%s) "
            "ON DUPLICATE KEY UPDATE session_id=VALUES(session_id), last_msg_ts=VALUES(last_msg_ts)",
            (channel_id, session_id, user_login, msg_ts),
        )

    # --- global opt-in ---
    async def set_global_opt_in(self, user_login: str, ts: datetime):
        await self.exec(
            "INSERT INTO global_opt_ins(user_login, opted_in_at, is_active) "
            "VALUES(%s,%s,1) "
            "ON DUPLICATE KEY UPDATE is_active=1, revoked_at=NULL",
            (user_login, ts),
        )

    async def get_all_globally_opted_in(self) -> list[str]:
        rows = await self.fetchall("SELECT user_login FROM global_opt_ins WHERE is_active=1", ())
        return [r["user_login"] for r in rows]

    # --- tickets (idempotent) ---
    async def issue_ticket_bucketed(self, channel_id: int, session_id: int, user_login: str, issued_at: datetime, bucket_start: datetime):
        try:
            await self.exec(
                "INSERT INTO tickets(channel_id, session_id, user_login, issued_at, bucket_start, reason) "
                "VALUES(%s,%s,%s,%s,%s,'present_10min')",
                (channel_id, session_id, user_login, issued_at, bucket_start),
            )
        except Exception as e:
            if _mysql_err_code(e) == MYSQL_DUPLICATE_KEY:
                return
            raise

    # --- draw helpers ---
    async def list_sessions(self, channel_id: int | None = None, limit: int = 50):
        if channel_id:
            return await self.fetchall(
                "SELECT session_id, channel_id, started_at, ended_at, title, category "
                "FROM stream_sessions WHERE channel_id=%s ORDER BY started_at DESC LIMIT %s",
                (channel_id, limit),
            )
        return await self.fetchall(
            "SELECT session_id, channel_id, started_at, ended_at, title, category "
            "FROM stream_sessions ORDER BY started_at DESC LIMIT %s",
            (limit,),
        )

    async def tickets_aggregate_for_sessions(self, session_ids: list[int]) -> list[dict]:
        if not session_ids:
            return []
        placeholders = ",".join(["%s"] * len(session_ids))
        sql = (
            f"SELECT user_login, COUNT(*) AS tickets "
            f"FROM tickets WHERE session_id IN ({placeholders}) "
            f"GROUP BY user_login"
        )
        return await self.fetchall(sql, tuple(session_ids))

    async def create_draw_run(self, description: str | None):
        await self.exec("INSERT INTO draw_runs(description) VALUES(%s)", (description,))
        row = await self.fetchone("SELECT LAST_INSERT_ID() AS id")
        return int(row["id"])

    async def add_draw_sessions(self, draw_id: int, session_ids: list[int]):
        for sid in session_ids:
            await self.exec(
                "INSERT IGNORE INTO draw_run_sessions(draw_id, session_id) VALUES(%s,%s)",
                (draw_id, sid),
            )

    async def add_winner(self, draw_id: int, user_login: str, weight_tickets: int):
        await self.exec(
            "INSERT INTO winners(draw_id, user_login, weight_tickets) VALUES(%s,%s,%s)",
            (draw_id, user_login, weight_tickets),
        )
