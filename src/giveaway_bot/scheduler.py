import asyncio
from datetime import datetime, timedelta, timezone
from typing import Optional

def bucket_start_utc(now: datetime, minutes: int) -> datetime:
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    epoch = int(now.timestamp())
    bucket = (epoch // (minutes * 60)) * (minutes * 60)
    return datetime.fromtimestamp(bucket, tz=timezone.utc).replace(tzinfo=None)

class TicketScheduler:
    def __init__(self, db, ticket_interval_minutes: int, presence_map: dict[int, set[str]], on_ticket_issued=None):
        self.db = db
        self.minutes = ticket_interval_minutes
        self.presence_map = presence_map
        self.on_ticket_issued = on_ticket_issued

    async def run(self, channel_ids: list[int]):
        last_processed_bucket: Optional[datetime] = None
        bucket_step = timedelta(minutes=self.minutes)

        while True:
            now = datetime.now(timezone.utc)
            current_bucket = bucket_start_utc(now, self.minutes)

            if last_processed_bucket is None:
                bucket_starts = [current_bucket]
            else:
                bucket_starts = []
                next_bucket = last_processed_bucket + bucket_step
                while next_bucket <= current_bucket:
                    bucket_starts.append(next_bucket)
                    next_bucket += bucket_step

            globally_opted_in = set(await self.db.get_all_globally_opted_in())

            for bstart in bucket_starts:
                for cid in channel_ids:
                    session_id = await self.db.current_session_id(cid)
                    if not session_id:
                        continue
                    present = self.presence_map.get(cid, set())
                    candidates = present & globally_opted_in
                    for u in candidates:
                        inserted = await self.db.issue_ticket_bucketed(
                            channel_id=cid,
                            session_id=session_id,
                            user_login=u,
                            issued_at=now.replace(tzinfo=None),
                            bucket_start=bstart,
                        )
                        if self.on_ticket_issued and inserted:
                            await self.on_ticket_issued(cid, session_id, u, bstart)

            last_processed_bucket = current_bucket
            await asyncio.sleep(20)
