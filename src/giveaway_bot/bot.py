import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import Optional

from giveaway_bot.config import Config
from giveaway_bot.db import Database
from giveaway_bot.twitch_api import TwitchAPI
from giveaway_bot.token_manager import TokenManager
from giveaway_bot.eventsub_ws import EventSubWS
from giveaway_bot.irc_chat import IRCChat
from giveaway_bot.scheduler import TicketScheduler

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("giveaway-bot")

async def run_with_backoff(coro_factory, name: str):
    delay = 1
    while True:
        try:
            log.info("Starting %s", name)
            await coro_factory()
            delay = 1
        except asyncio.CancelledError:
            raise
        except Exception as e:
            log.exception("%s crashed: %s", name, e)
            await asyncio.sleep(delay)
            delay = min(delay * 2, 60)

def is_ignored_user(cfg: Config, user_login: str, tags: Optional[str]) -> bool:
    ul = user_login.lower()
    if ul in cfg.ignored_logins:
        return True
    if cfg.ignore_verified_bots and tags:
        # Best-effort heuristics; keep conservative.
        if "bot=1" in tags or "user-type=bot" in tags:
            return True
    return False

async def amain():
    cfg = Config()

    db = Database(cfg.mysql_host, cfg.mysql_port, cfg.mysql_user, cfg.mysql_password, cfg.mysql_db)
    await db.connect()

    token_mgr = TokenManager(
        client_id=cfg.twitch_client_id,
        client_secret=cfg.twitch_client_secret,
        access_token=cfg.twitch_user_access_token,
        refresh_token=cfg.twitch_user_refresh_token,
    )

    helix = TwitchAPI(cfg.twitch_client_id, cfg.twitch_client_secret)
    users = await helix.get_users_by_logins(cfg.channel_logins)
    if not users:
        raise RuntimeError("No channels resolved. Check CHANNEL_LOGINS.")

    channel_login_to_id = {}
    for u in users:
        cid = int(u["id"])
        login = u["login"].lower()
        channel_login_to_id[login] = cid
        await db.upsert_channel(cid, login, u.get("display_name"))

    channel_ids = list(channel_login_to_id.values())
    presence: dict[int, set[str]] = {cid: set() for cid in channel_ids}

    # IRC
    irc = IRCChat(cfg.bot_nick, cfg.irc_oauth_token)

    async def on_join(ev: dict):
        cid = channel_login_to_id.get(ev["channel"])
        if not cid:
            return
        if is_ignored_user(cfg, ev["user_login"], ev.get("tags")):
            return
        presence.setdefault(cid, set()).add(ev["user_login"])

    async def on_part(ev: dict):
        cid = channel_login_to_id.get(ev["channel"])
        if not cid:
            return
        presence.setdefault(cid, set()).discard(ev["user_login"])

    async def on_privmsg(m: dict):
        cid = channel_login_to_id.get(m["channel"])
        if not cid:
            return

        if is_ignored_user(cfg, m["user_login"], m["tags"]):
            return

        session_id = await db.current_session_id(cid)
        await db.record_chat_message(
            channel_id=cid,
            session_id=session_id,
            user_login=m["user_login"],
            user_display=None,
            message=m["message"],
            msg_ts=m["ts"].astimezone(timezone.utc).replace(tzinfo=None),
            raw_tags=m["tags"],
        )

        if m["message"].strip().lower() == cfg.optin_codeword:
            await db.set_global_opt_in(
                user_login=m["user_login"],
                ts=datetime.now(timezone.utc).replace(tzinfo=None),
            )
            log.info("Global opt-in: %s", m["user_login"])

    async def irc_loop():
        await irc.connect()
        for login in cfg.channel_logins:
            await irc.join(login)
        await irc.listen(on_privmsg=on_privmsg, on_join=on_join, on_part=on_part)

    # EventSub (reconnect + token refresh)
    eventsub = EventSubWS(cfg.twitch_client_id, token_mgr)

    async def subscribe_all():
        for _, cid in channel_login_to_id.items():
            await eventsub.create_subscription("stream.online", "1", {"broadcaster_user_id": str(cid)})
            await eventsub.create_subscription("stream.offline", "1", {"broadcaster_user_id": str(cid)})

    async def on_eventsub(msg: dict):
        mtype = msg.get("metadata", {}).get("message_type")
        if mtype == "session_reconnect":
            log.warning("EventSub requested reconnect.")
            return

        if mtype != "notification":
            return

        sub_type = msg.get("metadata", {}).get("subscription_type")
        event = msg.get("payload", {}).get("event", {})
        bid = event.get("broadcaster_user_id")
        if not bid:
            return
        cid = int(bid)

        if sub_type == "stream.online":
            started_at = datetime.now(timezone.utc).replace(tzinfo=None)
            title = event.get("title")
            category = event.get("category_name") or event.get("game_name")
            await db.open_session(cid, started_at, title, category)
            log.info("LIVE: channel_id=%s", cid)

        elif sub_type == "stream.offline":
            ended_at = datetime.now(timezone.utc).replace(tzinfo=None)
            await db.close_session(cid, ended_at)
            log.info("OFFLINE: channel_id=%s", cid)

    async def eventsub_loop():
        await eventsub.run(on_msg=on_eventsub, subscribe_fn=subscribe_all)

    scheduler = TicketScheduler(db, cfg.ticket_interval_minutes, presence)

    await asyncio.gather(
        run_with_backoff(irc_loop, "irc"),
        run_with_backoff(eventsub_loop, "eventsub"),
        run_with_backoff(lambda: scheduler.run(channel_ids), "scheduler"),
    )

def main():
    asyncio.run(amain())

if __name__ == "__main__":
    main()
