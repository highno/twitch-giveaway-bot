import argparse
import asyncio

from giveaway_bot.config import Config
from giveaway_bot.db import Database
from giveaway_bot.raffle import run_draw


async def amain():
    ap = argparse.ArgumentParser()
    ap.add_argument("--list", action="store_true", help="List latest sessions")
    ap.add_argument("--channel-id", type=int, default=0, help="Optional channel_id filter for --list")
    ap.add_argument("--sessions", type=str, default="", help="Comma-separated session_ids to include in the draw")
    ap.add_argument("--winners", type=int, default=1, help="Number of winners to draw")
    ap.add_argument("--desc", type=str, default="", help="Description stored with draw run")
    ap.add_argument(
        "--exclude-previous-winners",
        action="store_true",
        help="Exclude users that have already won in any previous draw.",
    )
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
        draw_id, picks = await run_draw(
            db,
            session_ids=session_ids,
            winners=args.winners,
            description=args.desc,
            exclude_past_winners=args.exclude_previous_winners,
        )

        print(f"draw_id={draw_id}")
        for user, w in picks:
            print(f"WINNER: {user} (tickets={w})")

    finally:
        await db.close()


def main():
    asyncio.run(amain())


if __name__ == "__main__":
    main()
