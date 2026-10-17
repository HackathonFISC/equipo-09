"""H5: `GET /courses` (contrato `listCourses`), que usan `/centro` y la ruta de formación."""

from datetime import date

from puente_api.db import models
from tests.unit.conftest import LOC_A, SK_ATENCION, SK_CAJA

CENTER = "00000000-0000-0000-0006-0000000000c1"
COURSE = "00000000-0000-0000-0007-0000000000c1"


def _add_course(session_factory) -> None:
    with session_factory() as s:
        s.add(models.TrainingCenter(id=CENTER, name="INADEH Chorrera", location_id=LOC_A))
        s.flush()
        s.add(
            models.Course(
                id=COURSE,
                center_id=CENTER,
                title="Caja y atención al cliente",
                hours=40,
                cost=0,
                skills=[
                    models.CourseSkill(skill_id=SK_CAJA),
                    models.CourseSkill(skill_id=SK_ATENCION),
                ],
                sessions=[
                    models.CourseSession(
                        schedule=[{"day": "sab", "start": "08:00", "end": "12:00"}],
                        start_date=date(2026, 11, 7),
                        seats_total=20,
                        seats_taken=5,
                    ),
                    models.CourseSession(
                        schedule=[{"day": "mar", "start": "18:00", "end": "21:00"}],
                        start_date=date(2026, 11, 3),
                        seats_total=15,
                    ),
                ],
            )
        )
        s.commit()


def test_list_courses_matches_the_contract(client, session_factory):
    _add_course(session_factory)
    res = client.get("/api/v1/courses")
    assert res.status_code == 200
    [course] = res.json()
    assert course["id"] == COURSE
    assert course["centerId"] == CENTER
    assert course["hours"] == 40
    assert course["cost"] == 0
    assert sorted(course["skillIds"]) == sorted([SK_CAJA, SK_ATENCION])
    # Sesiones ordenadas por fecha de inicio, con cupos.
    assert [s["startDate"] for s in course["sessions"]] == ["2026-11-03", "2026-11-07"]
    assert course["sessions"][1]["seatsTaken"] == 5
    assert course["sessions"][1]["schedule"] == [{"day": "sab", "start": "08:00", "end": "12:00"}]


def test_list_courses_is_empty_without_catalog(client):
    assert client.get("/api/v1/courses").json() == []
