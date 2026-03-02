import argparse
import random
from datetime import datetime
import asyncio

from giveaway_bot.config import Config
from giveaway_bot.db import Database

def weighted_sample_without_replacement(items, k):
    # Efraimidis–Spirakis: key = U^(1/w); pick top-k
    keys = []
    for user, w in items:
        if w <= 0:
            continue
        u = random.random()
        key = u ** (1.0 / w)
        keys.append((key, user, w))
    keys.sort(reverse=True, key=lambda x: x[0])
    return [(user, w) for _, user, w in keys[:k]]

async def amain():
    ap = argparse.ArgumentParser()
    ap.add_argument("--list", action="store_true", help="List latest sessions")
    ap.add_argument("--channel-id", type=int, default=0, help="Optional channel_id filter for --list")
    ap.add_argument("--sessions", type=str, default="", help="Comma-separated session_ids to include in the draw")
    ap.add_argument("--winners", type=int, default=1, help="Number of winners to draw")
    ap.add_argument("--desc", type=str, default="", help="Description stored with draw run")
    args = ap.parse_args()

    cfg = Config()
    db = Database(cfg.mysql_host, cfg.mysql_port, cfg.mysql_user, cfg.mysql_password, cfg.mysql_db)
    await db.connect()

    try:
        if args.list:
            sessions = await db.list_sessions(channel_id=args.channel_id or None, limit=50)
            for s in sessions:
                print(
                    f"session_id={s['session_id']} channel_id={s['channel_id']} "
                    f"start={s['started_at']} end={s['ended_at']} title={s['title']}"
                )
            return

        if not args.sessions.strip():
            raise SystemExit("Provide --sessions 123,124,... or use --list")

        session_ids = [int(x.strip()) for x in args.sessions.split(",") if x.strip()]
        agg = await db.tickets_aggregate_for_sessions(session_ids)
        if not agg:
            raise SystemExit("No tickets found for given sessions.")

        items = [(r["user_login"], int(r["tickets"])) for r in agg]
        picks = weighted_sample_without_replacement(items, args.winners)

        draw_id = await db.create_draw_run(args.desc or f"Draw {datetime.utcnow().isoformat()}Z")
        await db.add_draw_sessions(draw_id, session_ids)

        print(f"draw_id={draw_id}")
        for user, w in picks:
            await db.add_winner(draw_id, user, w)
            print(f"WINNER: {user} (tickets={w})")

    finally:
        await db.close()

def main():
    asyncio.run(amain())

if __name__ == "__main__":
    main()
