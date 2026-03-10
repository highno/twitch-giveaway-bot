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
    async def log_event(self, event_type: str, channel_id: Optional[int], payload_json: Optional[str]):
        await self.exec(
            "INSERT INTO event_log(channel_id, event_type, payload) VALUES(%s,%s,%s)",
            (channel_id, event_type, payload_json),
        )

    async def record_presence_event(
        self,
        channel_id: int,
        session_id: Optional[int],
        user_login: str,
        event_type: str,
        event_ts: datetime,
    ):
        await self.exec(
            "INSERT INTO presence_events(channel_id, session_id, user_login, event_type, event_ts) VALUES(%s,%s,%s,%s,%s)",
            (channel_id, session_id, user_login, event_type, event_ts),
        )

    async def upsert_channel(self, channel_id: int, login: str, display_name: Optional[str]):
        await self.exec(
            "INSERT INTO channels(id, login, display_name) VALUES(%s,%s,%s) "
            "ON DUPLICATE KEY UPDATE login=VALUES(login), display_name=VALUES(display_name)",
            (channel_id, login, display_name),
        )

    # --- sessions ---
    async def open_session(self, channel_id: int, started_at: datetime, title: Optional[str], category: Optional[str]) -> int:
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

    async def current_session_id(self, channel_id: int) -> Optional[int]:
        row = await self.fetchone(
            "SELECT session_id FROM stream_sessions WHERE channel_id=%s AND is_live=1 ORDER BY session_id DESC LIMIT 1",
            (channel_id,),
        )
        return int(row["session_id"]) if row else None

    # --- chat / heartbeats ---
    async def record_chat_message(
        self,
        channel_id: int,
        session_id: Optional[int],
        user_login: str,
        user_display: Optional[str],
        message: str,
        msg_ts: datetime,
        raw_tags: Optional[str],
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

    async def is_user_globally_opted_in(self, user_login: str) -> bool:
        row = await self.fetchone(
            "SELECT 1 AS ok FROM global_opt_ins WHERE user_login=%s AND is_active=1 LIMIT 1",
            (user_login,),
        )
        return bool(row)
    async def pause_global_opt_in(self, user_login: str, ts: datetime) -> bool:
        rc = await self.exec(
            "UPDATE global_opt_ins SET is_active=0, revoked_at=%s WHERE user_login=%s AND is_active=1",
            (ts, user_login),
        )
        return rc > 0

    async def has_global_opt_in_record(self, user_login: str) -> bool:
        row = await self.fetchone(
            "SELECT 1 AS ok FROM global_opt_ins WHERE user_login=%s LIMIT 1",
            (user_login,),
        )
        return bool(row)

    async def delete_all_user_data(self, user_login: str) -> None:
        await self.exec("DELETE FROM winners WHERE user_login=%s", (user_login,))
        await self.exec("DELETE FROM tickets WHERE user_login=%s", (user_login,))
        await self.exec("DELETE FROM activity_heartbeats WHERE user_login=%s", (user_login,))
        await self.exec("DELETE FROM chat_messages WHERE user_login=%s", (user_login,))
        await self.exec("DELETE FROM presence_events WHERE user_login=%s", (user_login,))
        await self.exec("DELETE FROM global_opt_ins WHERE user_login=%s", (user_login,))


    # --- tickets (idempotent) ---
    async def issue_ticket_bucketed(self, channel_id: int, session_id: int, user_login: str, issued_at: datetime, bucket_start: datetime) -> bool:
        try:
            await self.exec(
                "INSERT INTO tickets(channel_id, session_id, user_login, issued_at, bucket_start, reason) "
                "VALUES(%s,%s,%s,%s,%s,'present_10min')",
                (channel_id, session_id, user_login, issued_at, bucket_start),
            )
            return True
        except Exception as e:
            if _mysql_err_code(e) == MYSQL_DUPLICATE_KEY:
                return False
            raise

    async def count_tickets_for_user(
        self,
        user_login: str,
        channel_id: Optional[int] = None,
        start_ts: Optional[datetime] = None,
        end_ts: Optional[datetime] = None,
    ) -> int:
        sql = "SELECT COUNT(*) AS c FROM tickets WHERE user_login=%s"
        args: list[Any] = [user_login]
        if channel_id is not None:
            sql += " AND channel_id=%s"
            args.append(channel_id)
        if start_ts is not None:
            sql += " AND issued_at >= %s"
            args.append(start_ts)
        if end_ts is not None:
            sql += " AND issued_at <= %s"
            args.append(end_ts)
        row = await self.fetchone(sql, tuple(args))
        return int(row["c"]) if row else 0

    async def ticket_stats_per_user_channel(
        self,
        channel_id: Optional[int] = None,
        start_ts: Optional[datetime] = None,
        end_ts: Optional[datetime] = None,
    ) -> list[dict[str, Any]]:
        sql = (
            "SELECT t.user_login, t.channel_id, c.login AS channel_login, COUNT(*) AS tickets "
            "FROM tickets t "
            "JOIN channels c ON c.id=t.channel_id "
            "WHERE 1=1"
        )
        args: list[Any] = []
        if channel_id is not None:
            sql += " AND t.channel_id=%s"
            args.append(channel_id)
        if start_ts is not None:
            sql += " AND t.issued_at >= %s"
            args.append(start_ts)
        if end_ts is not None:
            sql += " AND t.issued_at <= %s"
            args.append(end_ts)
        sql += " GROUP BY t.user_login, t.channel_id, c.login ORDER BY tickets DESC, t.user_login ASC"
        return await self.fetchall(sql, tuple(args))

    async def delete_tickets_for_user(
        self,
        user_login: str,
        channel_id: Optional[int] = None,
        start_ts: Optional[datetime] = None,
        end_ts: Optional[datetime] = None,
    ) -> int:
        sql = "DELETE FROM tickets WHERE user_login=%s"
        args: list[Any] = [user_login]
        if channel_id is not None:
            sql += " AND channel_id=%s"
            args.append(channel_id)
        if start_ts is not None:
            sql += " AND issued_at >= %s"
            args.append(start_ts)
        if end_ts is not None:
            sql += " AND issued_at <= %s"
            args.append(end_ts)
        return int(await self.exec(sql, tuple(args)))

    async def delete_all_tickets(self) -> int:
        return int(await self.exec("DELETE FROM tickets", ()))

    async def reset_all_state(self):
        await self.exec("DELETE FROM winners", ())
        await self.exec("DELETE FROM draw_run_sessions", ())
        await self.exec("DELETE FROM draw_runs", ())
        await self.exec("DELETE FROM tickets", ())
        await self.exec("DELETE FROM activity_heartbeats", ())
        await self.exec("DELETE FROM chat_messages", ())
        await self.exec("DELETE FROM presence_events", ())
        await self.exec("DELETE FROM global_opt_ins", ())
        await self.exec("DELETE FROM stream_sessions", ())
        await self.exec("DELETE FROM event_log", ())
        await self.exec("DELETE FROM channels", ())

    # --- draw helpers ---
    async def list_sessions(self, channel_id: Optional[int] = None, limit: int = 50):
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

    async def tickets_aggregate_for_sessions(self, session_ids: list[int], exclude_past_winners: bool = False) -> list[dict]:
        if not session_ids:
            return []
        placeholders = ",".join(["%s"] * len(session_ids))
        sql = (
            f"SELECT t.user_login, COUNT(*) AS tickets "
            f"FROM tickets t WHERE t.session_id IN ({placeholders}) "
        )
        if exclude_past_winners:
            sql += "AND NOT EXISTS (SELECT 1 FROM winners w WHERE w.user_login=t.user_login) "
        sql += "GROUP BY t.user_login"
        return await self.fetchall(sql, tuple(session_ids))

    async def create_draw_run(self, description: Optional[str]):
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


    async def draw_runs(self, limit: int = 100) -> list[dict[str, Any]]:
        sql = (
            "SELECT dr.draw_id, dr.created_at, dr.description, COUNT(w.winner_id) AS winner_count "
            "FROM draw_runs dr "
            "LEFT JOIN winners w ON w.draw_id=dr.draw_id "
            "GROUP BY dr.draw_id, dr.created_at, dr.description "
            "ORDER BY dr.draw_id DESC LIMIT %s"
        )
        return await self.fetchall(sql, (limit,))

    async def draw_winners(self, draw_id: int) -> list[dict[str, Any]]:
        return await self.fetchall(
            "SELECT winner_id, user_login, weight_tickets, created_at FROM winners WHERE draw_id=%s ORDER BY winner_id ASC",
            (draw_id,),
        )

    async def delete_draw(self, draw_id: int) -> None:
        await self.exec("DELETE FROM winners WHERE draw_id=%s", (draw_id,))
        await self.exec("DELETE FROM draw_run_sessions WHERE draw_id=%s", (draw_id,))
        await self.exec("DELETE FROM draw_runs WHERE draw_id=%s", (draw_id,))

    async def detected_viewer_minutes_total(
        self,
        ticket_interval_minutes: int,
        channel_id: Optional[int] = None,
        start_ts: Optional[datetime] = None,
        end_ts: Optional[datetime] = None,
    ) -> int:
        sql = "SELECT COUNT(*) AS c FROM tickets WHERE 1=1"
        args: list[Any] = []
        if channel_id is not None:
            sql += " AND channel_id=%s"
            args.append(channel_id)
        if start_ts is not None:
            sql += " AND issued_at >= %s"
            args.append(start_ts)
        if end_ts is not None:
            sql += " AND issued_at <= %s"
            args.append(end_ts)
        row = await self.fetchone(sql, tuple(args))
        return int((int(row["c"]) if row else 0) * ticket_interval_minutes)

    async def user_ticket_leaderboard(self, limit: int = 200) -> list[dict[str, Any]]:
        return await self.fetchall(
            "SELECT user_login, COUNT(*) AS tickets FROM tickets GROUP BY user_login ORDER BY tickets DESC, user_login ASC LIMIT %s",
            (limit,),
        )

    async def user_minutes_leaderboard(self, ticket_interval_minutes: int, limit: int = 200) -> list[dict[str, Any]]:
        rows = await self.user_ticket_leaderboard(limit=limit)
        return [
            {"user_login": r["user_login"], "minutes": int(r["tickets"]) * ticket_interval_minutes, "tickets": int(r["tickets"])}
            for r in rows
        ]

    async def user_ticket_timeline(
        self,
        user_login: str,
        channel_id: Optional[int] = None,
        start_ts: Optional[datetime] = None,
        end_ts: Optional[datetime] = None,
        sort_by: str = "time",
    ) -> list[dict[str, Any]]:
        sql = (
            "SELECT t.ticket_id, t.channel_id, c.login AS channel_login, t.session_id, t.issued_at, t.bucket_start "
            "FROM tickets t JOIN channels c ON c.id=t.channel_id WHERE t.user_login=%s"
        )
        args: list[Any] = [user_login]
        if channel_id is not None:
            sql += " AND t.channel_id=%s"
            args.append(channel_id)
        if start_ts is not None:
            sql += " AND t.issued_at >= %s"
            args.append(start_ts)
        if end_ts is not None:
            sql += " AND t.issued_at <= %s"
            args.append(end_ts)
        if sort_by == "channel_time":
            sql += " ORDER BY t.channel_id ASC, t.issued_at DESC"
        else:
            sql += " ORDER BY t.issued_at DESC"
        return await self.fetchall(sql, tuple(args))


    async def currently_present_users(self, channel_id: Optional[int] = None) -> list[dict[str, Any]]:
        sql = (
            "SELECT pe.channel_id, c.login AS channel_login, pe.user_login, pe.event_ts AS joined_at "
            "FROM presence_events pe "
            "JOIN channels c ON c.id=pe.channel_id "
            "JOIN ("
            "  SELECT channel_id, user_login, MAX(event_ts) AS max_ts "
            "  FROM presence_events GROUP BY channel_id, user_login"
            ") latest ON latest.channel_id=pe.channel_id AND latest.user_login=pe.user_login AND latest.max_ts=pe.event_ts "
            "WHERE pe.event_type='join'"
        )
        args: list[Any] = []
        if channel_id is not None:
            sql += " AND pe.channel_id=%s"
            args.append(channel_id)
        sql += " ORDER BY pe.channel_id ASC, pe.event_ts DESC, pe.user_login ASC"
        return await self.fetchall(sql, tuple(args))

    async def user_presence_timeline(
        self,
        user_login: str,
        channel_id: Optional[int] = None,
        start_ts: Optional[datetime] = None,
        end_ts: Optional[datetime] = None,
        sort_by: str = "time",
    ) -> list[dict[str, Any]]:
        sql = (
            "SELECT pe.presence_event_id, pe.channel_id, c.login AS channel_login, pe.session_id, pe.event_type, pe.event_ts "
            "FROM presence_events pe JOIN channels c ON c.id=pe.channel_id WHERE pe.user_login=%s"
        )
        args: list[Any] = [user_login]
        if channel_id is not None:
            sql += " AND pe.channel_id=%s"
            args.append(channel_id)
        if start_ts is not None:
            sql += " AND pe.event_ts >= %s"
            args.append(start_ts)
        if end_ts is not None:
            sql += " AND pe.event_ts <= %s"
            args.append(end_ts)
        if sort_by == "channel_time":
            sql += " ORDER BY pe.channel_id ASC, pe.event_ts DESC"
        else:
            sql += " ORDER BY pe.event_ts DESC"
        return await self.fetchall(sql, tuple(args))
