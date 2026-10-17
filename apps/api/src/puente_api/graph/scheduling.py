"""Franjas de entrevista sin choques (código determinista, sin LLM)."""

from collections.abc import Sequence
from datetime import datetime, time, timedelta, timezone

PANAMA = timezone(timedelta(hours=-5))  # sin horario de verano
SLOT_MINUTES = 30
DAY_START = time(9, 0)
SLOTS_PER_DAY = 8  # 09:00–13:00


def next_business_day(now: datetime) -> datetime:
    """Primer día hábil posterior a `now`, a las 09:00 de Panamá."""
    day = now.astimezone(PANAMA).date() + timedelta(days=1)
    while day.weekday() >= 5:
        day += timedelta(days=1)
    return datetime.combine(day, DAY_START, tzinfo=PANAMA)


def assign_interview_slots(
    candidate_ids: Sequence[str], start: datetime
) -> dict[str, tuple[datetime, datetime]]:
    """Una franja de 30 min por candidato, consecutivas y sin traslapes, saltando fines de semana.

    El orden de `candidate_ids` es la prioridad: el primero recibe la franja más temprana.
    """
    slots: dict[str, tuple[datetime, datetime]] = {}
    cursor = start
    used_today = 0
    for cid in candidate_ids:
        if used_today == SLOTS_PER_DAY:
            cursor = next_business_day(cursor)
            used_today = 0
        end = cursor + timedelta(minutes=SLOT_MINUTES)
        slots[cid] = (cursor, end)
        cursor = end
        used_today += 1
    return slots
