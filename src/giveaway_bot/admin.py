import argparse
import asyncio
from datetime import datetime
from typing import Optional

from giveaway_bot.config import Config
from giveaway_bot.db import Database


def parse_dt(value: str) -> datetime:
    try:
        return datetime.fromisoformat(value)
    except ValueError as e:
        raise argparse.ArgumentTypeError(
            f"Invalid datetime '{value}'. Use ISO format, e.g. 2024-01-31 or 2024-01-31T23:59:59"
        ) from e


async def amain():
    ap = argparse.ArgumentParser(description="Admin utilities for giveaway ticket/state management")
    sub = ap.add_subparsers(dest="cmd", required=True)

    stats = sub.add_parser("stats", help="Show ticket counts per user and channel")
    stats.add_argument("--channel-id", type=int, default=0, help="Optional channel_id filter")
    stats.add_argument("--from", dest="from_ts", type=parse_dt, help="Optional lower bound (ISO datetime)")
    stats.add_argument("--to", dest="to_ts", type=parse_dt, help="Optional upper bound (ISO datetime)")

    purge_user = sub.add_parser("purge-user", help="Delete all tickets of a specific user")
    purge_user.add_argument("--user", required=True, type=str, help="Twitch login to delete tickets for")
    purge_user.add_argument("--channel-id", type=int, default=0, help="Optional channel_id filter")
    purge_user.add_argument("--from", dest="from_ts", type=parse_dt, help="Optional lower bound (ISO datetime)")
    purge_user.add_argument("--to", dest="to_ts", type=parse_dt, help="Optional upper bound (ISO datetime)")

    sub.add_parser("purge-all-tickets", help="Delete all tickets from the pot")

    reset = sub.add_parser("reset-all", help="Reset all runtime state as if freshly installed")
    reset.add_argument("--yes", action="store_true", help="Required safety flag")

    args = ap.parse_args()

    cfg = Config()
    db = Database(cfg.mysql_host, cfg.mysql_port, cfg.mysql_user, cfg.mysql_password, cfg.mysql_db)
    await db.connect()

    try:
        if args.cmd == "stats":
            rows = await db.ticket_stats_per_user_channel(
                channel_id=args.channel_id or None,
                start_ts=args.from_ts,
                end_ts=args.to_ts,
            )
            if not rows:
                print("No ticket rows found for the given filter.")
                return

            print("user_login\tchannel_id\tchannel_login\ttickets")
            for r in rows:
                print(f"{r['user_login']}\t{r['channel_id']}\t{r['channel_login']}\t{int(r['tickets'])}")
            print(f"rows={len(rows)}")
            return

        if args.cmd == "purge-user":
            deleted = await db.delete_tickets_for_user(
                user_login=args.user.strip().lower(),
                channel_id=args.channel_id or None,
                start_ts=args.from_ts,
                end_ts=args.to_ts,
            )
            print(f"deleted_tickets={deleted}")
            return

        if args.cmd == "purge-all-tickets":
            deleted = await db.delete_all_tickets()
            print(f"deleted_tickets={deleted}")
            return

        if args.cmd == "reset-all":
            if not args.yes:
                raise SystemExit("Refusing reset without --yes")
            await db.reset_all_state()
            print("ok=reset_all_state")
            return

        raise SystemExit(f"Unknown command: {args.cmd}")
    finally:
        await db.close()


def main():
    asyncio.run(amain())


if __name__ == "__main__":
    main()
