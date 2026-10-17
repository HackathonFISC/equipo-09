"""H5: las fechas salen en UTC explícito (con zona) para que el navegador no las corra 5 horas."""

from datetime import UTC, datetime, timedelta, timezone

from puente_api import schemas

PANAMA = timezone(timedelta(hours=-5))


def test_naive_datetimes_from_sqlite_are_marked_utc():
    slot = schemas.InterviewSlot(
        starts_at=datetime(2026, 10, 19, 14, 0), ends_at=datetime(2026, 10, 19, 14, 30)
    )
    dumped = slot.model_dump(mode="json", by_alias=True)
    assert dumped["startsAt"] == "2026-10-19T14:00:00Z"
    assert dumped["endsAt"] == "2026-10-19T14:30:00Z"


def test_aware_datetimes_are_converted_to_utc():
    slot = schemas.InterviewSlot(
        starts_at=datetime(2026, 10, 19, 9, 0, tzinfo=PANAMA),
        ends_at=datetime(2026, 10, 19, 9, 30, tzinfo=PANAMA),
    )
    assert slot.starts_at == datetime(2026, 10, 19, 14, 0, tzinfo=UTC)
