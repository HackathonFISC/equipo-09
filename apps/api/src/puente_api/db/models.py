"""Modelos SQLAlchemy 2 según docs/05-esquema-backend.md.

Convenciones de esta capa (para seeds y solvers):
- `id` es UUID guardado como texto de 36 caracteres (`str(uuid4())`), portable
  entre SQLite y Postgres.
- Columnas `jsonb` del esquema usan `JSON` (JSONB en Postgres).
- Horarios (`schedule`, `availability`) son listas de franjas `{"day", "start", "end"}`
  con `day` en lun..dom y horas "HH:MM", igual que `TimeSlot` en openapi.yaml.
- Dinero en balboas como Numeric(8,2); tiempos en minutos.
"""

from datetime import date, datetime
from decimal import Decimal
from typing import Any
from uuid import uuid4

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

JSONType = JSON().with_variant(JSONB(), "postgresql")
Money = Numeric(8, 2)


def new_id() -> str:
    return str(uuid4())


class Base(DeclarativeBase):
    type_annotation_map = {dict[str, Any]: JSONType, list[Any]: JSONType}


class Timestamps:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


def uuid_pk() -> Mapped[str]:
    return mapped_column(String(36), primary_key=True, default=new_id)


def fk(target: str, **kwargs: Any) -> Any:
    return mapped_column(String(36), ForeignKey(target, ondelete="CASCADE"), **kwargs)


# --- Catálogos ---------------------------------------------------------------


class Location(Timestamps, Base):
    __tablename__ = "location"

    id: Mapped[str] = uuid_pk()
    corregimiento: Mapped[str] = mapped_column(String(120))
    distrito: Mapped[str] = mapped_column(String(120))
    provincia: Mapped[str] = mapped_column(String(120))
    lat: Mapped[float | None] = mapped_column(Float)
    lng: Mapped[float | None] = mapped_column(Float)


class CommuteMatrix(Base):
    __tablename__ = "commute_matrix"
    __table_args__ = (CheckConstraint("mode IN ('bus','metro','mixto')", name="ck_commute_mode"),)

    origin_id: Mapped[str] = fk("location.id", primary_key=True)
    dest_id: Mapped[str] = fk("location.id", primary_key=True)
    minutes: Mapped[int] = mapped_column(Integer)
    cost_daily: Mapped[Decimal] = mapped_column(Money)
    mode: Mapped[str] = mapped_column(String(10))


class Skill(Timestamps, Base):
    __tablename__ = "skill"

    id: Mapped[str] = uuid_pk()
    esco_uri: Mapped[str | None] = mapped_column(String(255), unique=True)
    label_es: Mapped[str] = mapped_column(String(200))
    group: Mapped[str | None] = mapped_column(String(120))
    aliases: Mapped[list[Any]] = mapped_column(default=list)


# --- Lado joven --------------------------------------------------------------


class Youth(Timestamps, Base):
    __tablename__ = "youth"

    id: Mapped[str] = uuid_pk()
    display_name: Mapped[str] = mapped_column(String(120))
    birth_year: Mapped[int] = mapped_column(Integer)
    gender: Mapped[str | None] = mapped_column(String(30))
    location_id: Mapped[str] = fk("location.id")
    max_commute_min: Mapped[int] = mapped_column(Integer)
    transport_budget_daily: Mapped[Decimal] = mapped_column(Money)
    availability: Mapped[list[Any]] = mapped_column(default=list)
    min_salary: Mapped[Decimal | None] = mapped_column(Money)
    studying: Mapped[bool] = mapped_column(Boolean, default=False)
    cv_raw_text: Mapped[str | None] = mapped_column(Text)
    is_synthetic: Mapped[bool] = mapped_column(Boolean, default=True)

    location: Mapped[Location] = relationship()
    skills: Mapped[list["ProfileSkill"]] = relationship(cascade="all, delete-orphan")


class ProfileSkill(Base):
    __tablename__ = "profile_skill"
    __table_args__ = (
        CheckConstraint("level BETWEEN 1 AND 3", name="ck_profile_skill_level"),
        CheckConstraint(
            "source IN ('cv','entrevista','orientador')", name="ck_profile_skill_source"
        ),
        Index("ix_profile_skill_skill_id", "skill_id"),
    )

    youth_id: Mapped[str] = fk("youth.id", primary_key=True)
    skill_id: Mapped[str] = fk("skill.id", primary_key=True)
    level: Mapped[int] = mapped_column(Integer)
    source: Mapped[str] = mapped_column(String(20))
    evidence: Mapped[str] = mapped_column(Text)

    skill: Mapped[Skill] = relationship()


class InterviewTurn(Base):
    __tablename__ = "interview_turn"

    youth_id: Mapped[str] = fk("youth.id", primary_key=True)
    idx: Mapped[int] = mapped_column(Integer, primary_key=True)
    question: Mapped[str] = mapped_column(Text)
    answer: Mapped[str | None] = mapped_column(Text)


# --- Lado empresa ------------------------------------------------------------


class Company(Timestamps, Base):
    __tablename__ = "company"

    id: Mapped[str] = uuid_pk()
    name: Mapped[str] = mapped_column(String(200))
    location_id: Mapped[str | None] = fk("location.id")
    contact_email: Mapped[str | None] = mapped_column(String(200))

    location: Mapped[Location | None] = relationship()


class JobPosting(Timestamps, Base):
    __tablename__ = "job_posting"
    __table_args__ = (
        CheckConstraint("input_type IN ('texto','foto','pdf')", name="ck_posting_input_type"),
        CheckConstraint(
            "status IN ('borrador','bloqueada','publicada','cerrada')", name="ck_posting_status"
        ),
        CheckConstraint("vacancies >= 1", name="ck_posting_vacancies"),
        Index("ix_job_posting_status", "status"),
    )

    id: Mapped[str] = uuid_pk()
    company_id: Mapped[str] = fk("company.id")
    title: Mapped[str] = mapped_column(String(200))
    raw_input: Mapped[str | None] = mapped_column(Text)
    input_type: Mapped[str] = mapped_column(String(10), default="texto")
    location_id: Mapped[str | None] = fk("location.id")
    schedule: Mapped[list[Any]] = mapped_column(default=list)
    salary_min: Mapped[Decimal | None] = mapped_column(Money)
    salary_max: Mapped[Decimal | None] = mapped_column(Money)
    vacancies: Mapped[int] = mapped_column(Integer, default=1)
    status: Mapped[str] = mapped_column(String(12), default="borrador")

    company: Mapped[Company] = relationship()
    location: Mapped[Location | None] = relationship()
    requirements: Mapped[list["PostingRequirement"]] = relationship(cascade="all, delete-orphan")
    audit_checks: Mapped[list["AuditCheck"]] = relationship(
        primaryjoin="JobPosting.id == AuditCheck.posting_id", viewonly=True
    )


class PostingRequirement(Base):
    __tablename__ = "posting_requirement"
    __table_args__ = (
        CheckConstraint("weight BETWEEN 1 AND 3", name="ck_requirement_weight"),
        Index("ix_posting_requirement_skill_id", "skill_id"),
    )

    posting_id: Mapped[str] = fk("job_posting.id", primary_key=True)
    skill_id: Mapped[str] = fk("skill.id", primary_key=True)
    weight: Mapped[int] = mapped_column(Integer, default=1)
    required: Mapped[bool] = mapped_column(Boolean, default=True)

    skill: Mapped[Skill] = relationship()


# --- Lado formación ----------------------------------------------------------


class TrainingCenter(Timestamps, Base):
    __tablename__ = "training_center"

    id: Mapped[str] = uuid_pk()
    name: Mapped[str] = mapped_column(String(200))
    location_id: Mapped[str] = fk("location.id")

    location: Mapped[Location] = relationship()


class Course(Timestamps, Base):
    __tablename__ = "course"

    id: Mapped[str] = uuid_pk()
    center_id: Mapped[str] = fk("training_center.id")
    title: Mapped[str] = mapped_column(String(200))
    hours: Mapped[int] = mapped_column(Integer)
    cost: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"))

    center: Mapped[TrainingCenter] = relationship()
    sessions: Mapped[list["CourseSession"]] = relationship(cascade="all, delete-orphan")
    skills: Mapped[list["CourseSkill"]] = relationship(cascade="all, delete-orphan")


class CourseSkill(Base):
    __tablename__ = "course_skill"

    course_id: Mapped[str] = fk("course.id", primary_key=True)
    skill_id: Mapped[str] = fk("skill.id", primary_key=True)

    skill: Mapped[Skill] = relationship()


class CourseSession(Timestamps, Base):
    __tablename__ = "course_session"
    __table_args__ = (
        CheckConstraint("seats_taken <= seats_total", name="ck_session_seats"),
        CheckConstraint("seats_taken >= 0", name="ck_session_seats_nonneg"),
    )

    id: Mapped[str] = uuid_pk()
    course_id: Mapped[str] = fk("course.id")
    schedule: Mapped[list[Any]] = mapped_column(default=list)
    start_date: Mapped[date] = mapped_column(Date)
    seats_total: Mapped[int] = mapped_column(Integer)
    seats_taken: Mapped[int] = mapped_column(Integer, default=0)


# --- Decisiones de agentes ---------------------------------------------------


class MatchRun(Timestamps, Base):
    __tablename__ = "match_run"

    id: Mapped[str] = uuid_pk()
    triggered_by: Mapped[str] = mapped_column(String(120))
    params: Mapped[dict[str, Any]] = mapped_column(default=dict)
    solver_status: Mapped[str | None] = mapped_column(String(30))
    solve_ms: Mapped[int | None] = mapped_column(Integer)
    graph_thread_id: Mapped[str | None] = mapped_column(String(64))


class MatchResult(Timestamps, Base):
    __tablename__ = "match_result"
    __table_args__ = (
        UniqueConstraint("run_id", "youth_id", "posting_id", name="uq_match_result"),
        CheckConstraint(
            "status IN ('propuesto','aprobado','rechazado')", name="ck_match_result_status"
        ),
        Index("ix_match_result_run_score", "run_id", "score"),
    )

    id: Mapped[str] = uuid_pk()
    run_id: Mapped[str] = fk("match_run.id")
    youth_id: Mapped[str] = fk("youth.id")
    posting_id: Mapped[str] = fk("job_posting.id")
    score: Mapped[float] = mapped_column(Float)
    score_breakdown: Mapped[dict[str, Any]] = mapped_column(default=dict)
    constraints_checked: Mapped[dict[str, Any]] = mapped_column(default=dict)
    explanation: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(12), default="propuesto")


class TrainingPlan(Timestamps, Base):
    __tablename__ = "training_plan"

    id: Mapped[str] = uuid_pk()
    youth_id: Mapped[str] = fk("youth.id")
    total_cost: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"))
    unlocked_postings: Mapped[int] = mapped_column(Integer, default=0)
    explanation: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default="propuesto")

    items: Mapped[list["TrainingPlanItem"]] = relationship(
        cascade="all, delete-orphan", order_by="TrainingPlanItem.order"
    )


class TrainingPlanItem(Base):
    __tablename__ = "training_plan_item"

    plan_id: Mapped[str] = fk("training_plan.id", primary_key=True)
    session_id: Mapped[str] = fk("course_session.id", primary_key=True)
    order: Mapped[int] = mapped_column(Integer)


class Application(Timestamps, Base):
    __tablename__ = "application"
    __table_args__ = (
        CheckConstraint(
            "status IN ('en_lista_corta','enviada','entrevista','descartada')",
            name="ck_application_status",
        ),
    )

    id: Mapped[str] = uuid_pk()
    match_result_id: Mapped[str] = fk("match_result.id", unique=True)
    tailored_cv: Mapped[str | None] = mapped_column(Text)
    cover_letter: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default="en_lista_corta")


class InterviewSlot(Timestamps, Base):
    __tablename__ = "interview_slot"

    id: Mapped[str] = uuid_pk()
    application_id: Mapped[str] = fk("application.id")
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(20), default="propuesto")


class AuditCheck(Timestamps, Base):
    __tablename__ = "audit_check"
    __table_args__ = (
        CheckConstraint(
            "run_id IS NOT NULL OR posting_id IS NOT NULL", name="ck_audit_check_subject"
        ),
        CheckConstraint("kind IN ('discriminacion','contrafactual')", name="ck_audit_check_kind"),
    )

    id: Mapped[str] = uuid_pk()
    run_id: Mapped[str | None] = fk("match_run.id")
    posting_id: Mapped[str | None] = fk("job_posting.id")
    kind: Mapped[str] = mapped_column(String(20))
    variable: Mapped[str | None] = mapped_column(String(20))
    parity: Mapped[float | None] = mapped_column(Float)
    findings: Mapped[list[Any]] = mapped_column(default=list)
    passed: Mapped[bool] = mapped_column(Boolean)


class ReviewTask(Timestamps, Base):
    __tablename__ = "review_task"
    __table_args__ = (
        CheckConstraint(
            "kind IN ('bloqueo_oferta','lista_corta','alerta_sesgo')", name="ck_review_kind"
        ),
        CheckConstraint(
            "status IN ('pendiente','aprobada','editada','rechazada')", name="ck_review_status"
        ),
        Index("ix_review_task_status_created", "status", "created_at"),
    )

    id: Mapped[str] = uuid_pk()
    kind: Mapped[str] = mapped_column(String(20))
    subject_id: Mapped[str] = mapped_column(String(36))
    proposal: Mapped[dict[str, Any]] = mapped_column(default=dict)
    explanation: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(12), default="pendiente")
    reviewer: Mapped[str | None] = mapped_column(String(120))
    comment: Mapped[str | None] = mapped_column(Text)
    graph_thread_id: Mapped[str | None] = mapped_column(String(64))
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AgentTrace(Base):
    __tablename__ = "agent_trace"
    __table_args__ = (Index("ix_agent_trace_thread_created", "thread_id", "created_at"),)

    id: Mapped[str] = uuid_pk()
    thread_id: Mapped[str] = mapped_column(String(64))
    agent: Mapped[str] = mapped_column(String(40))
    step: Mapped[str] = mapped_column(String(80))
    input_summary: Mapped[str | None] = mapped_column(Text)
    decision: Mapped[str | None] = mapped_column(Text)
    reason: Mapped[str | None] = mapped_column(Text)
    duration_ms: Mapped[int | None] = mapped_column(Integer)
    langfuse_trace_id: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class EvalCase(Base):
    __tablename__ = "eval_case"

    case_id: Mapped[str] = mapped_column(String(80), primary_key=True)
    group: Mapped[str] = mapped_column(String(40))
    input: Mapped[dict[str, Any]] = mapped_column(default=dict)
    expected: Mapped[dict[str, Any]] = mapped_column(default=dict)


class EvalResult(Base):
    __tablename__ = "eval_result"

    id: Mapped[str] = uuid_pk()
    case_id: Mapped[str] = mapped_column(String(80), ForeignKey("eval_case.case_id"))
    metric: Mapped[str] = mapped_column(String(60))
    value: Mapped[float] = mapped_column(Float)
    passed: Mapped[bool] = mapped_column(Boolean)
    run_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
