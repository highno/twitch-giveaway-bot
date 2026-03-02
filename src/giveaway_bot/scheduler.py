import asyncio
from datetime import datetime, timezone

def bucket_start_utc(now: datetime, minutes: int) -> datetime:
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    epoch = int(now.timestamp())
    bucket = (epoch // (minutes * 60)) * (minutes * 60)
    return datetime.fromtimestamp(bucket, tz=timezone.utc).replace(tzinfo=None)

class TicketScheduler:
    def __init__(self, db, ticket_interval_minutes: int, presence_map: dict[int, set[str]]):
        self.db = db
        self.minutes = ticket_interval_minutes
        self.presence_map = presence_map

    async def run(self, channel_ids: list[int]):
        while True:
            now = datetime.now(timezone.utc)
            bstart = bucket_start_utc(now, self.minutes)

            globally_opted_in = set(await self.db.get_all_globally_opted_in())

            for cid in channel_ids:
                session_id = await self.db.current_session_id(cid)
                if not session_id:
                    continue
                present = self.presence_map.get(cid, set())
                candidates = present & globally_opted_in
                for u in candidates:
                    await self.db.issue_ticket_bucketed(
                        channel_id=cid,
                        session_id=session_id,
                        user_login=u,
                        issued_at=now.replace(tzinfo=None),
                        bucket_start=bstart,
                    )
            await asyncio.sleep(20)
