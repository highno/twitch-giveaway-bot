import random
from datetime import datetime
from typing import Optional

from giveaway_bot.db import Database


def weighted_sample_without_replacement(items: list[tuple[str, int]], k: int):
    keys = []
    for user, weight in items:
        if weight <= 0:
            continue
        value = random.random() ** (1.0 / weight)
        keys.append((value, user, weight))
    keys.sort(reverse=True, key=lambda x: x[0])
    return [(user, weight) for _, user, weight in keys[:k]]


async def run_draw(
    db: Database,
    session_ids: list[int],
    winners: int,
    description: Optional[str],
    exclude_past_winners: bool,
) -> tuple[int, list[tuple[str, int]]]:
    agg = await db.tickets_aggregate_for_sessions(
        session_ids,
        exclude_past_winners=exclude_past_winners,
    )
    if not agg:
        raise ValueError("No tickets found for given sessions.")

    items = [(row["user_login"], int(row["tickets"])) for row in agg]
    picks = weighted_sample_without_replacement(items, winners)

    draw_id = await db.create_draw_run(description or f"Draw {datetime.utcnow().isoformat()}Z")
    await db.add_draw_sessions(draw_id, session_ids)
    for user_login, ticket_weight in picks:
        await db.add_winner(draw_id, user_login, ticket_weight)

    return draw_id, picks
