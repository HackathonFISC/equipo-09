"""Esquemas de respuesta: reflejan `components/schemas` de packages/api-spec/openapi.yaml."""

from datetime import datetime
from typing import Any, Literal

from pydantic import AliasChoices, BaseModel, ConfigDict, Field, field_validator
from pydantic.alias_generators import to_camel

Day = Literal["lun", "mar", "mie", "jue", "vie", "sab", "dom"]
PostingStatus = Literal["borrador", "bloqueada", "publicada", "cerrada"]


class ApiModel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, from_attributes=True)


class Location(ApiModel):
    id: str
    corregimiento: str
    distrito: str
    provincia: str
    lat: float | None = None
    lng: float | None = None


class Skill(ApiModel):
    id: str
    esco_uri: str | None = None
    label_es: str
    group: str | None = None


class TimeSlot(ApiModel):
    day: Day
    start: str
    end: str


def normalize_slots(value: Any) -> list[dict[str, Any]]:
    """Acepta franjas `{day,start,end}` (OpenAPI) o `{dia,inicio,fin}` (doc 05)."""
    return [
        {
            "day": slot.get("day", slot.get("dia")),
            "start": slot.get("start", slot.get("inicio")),
            "end": slot.get("end", slot.get("fin")),
        }
        for slot in value or []
    ]


class PostingRequirement(ApiModel):
    skill: Skill
    weight: int
    required: bool


class AuditCheck(ApiModel):
    id: str
    kind: Literal["discriminacion", "contrafactual"]
    variable: Literal["nombre", "genero", "corregimiento"] | None = None
    parity: float | None = None
    passed: bool
    findings: list[str] = []

    @field_validator("findings", mode="before")
    @classmethod
    def _findings_as_text(cls, value: Any) -> list[str]:
        if not value:
            return []
        if isinstance(value, dict):
            return [f"{k}: {v}" for k, v in value.items()]
        return [item if isinstance(item, str) else str(item) for item in value]


class JobPosting(ApiModel):
    id: str
    company_id: str
    title: str
    input_type: Literal["texto", "foto", "pdf"]
    location: Location | None = None
    schedule: list[TimeSlot] = []
    salary_min: float | None = None
    salary_max: float | None = None
    vacancies: int | None = None
    status: PostingStatus
    requirements: list[PostingRequirement] = []
    # En el ORM la relación se llama `audit_checks`; en el contrato, `auditFindings`.
    audit_findings: list[AuditCheck] = Field(
        default=[], validation_alias=AliasChoices("audit_checks", "auditFindings", "audit_findings")
    )

    @field_validator("schedule", mode="before")
    @classmethod
    def _normalize_schedule(cls, value: Any) -> list[dict[str, Any]]:
        return normalize_slots(value)


# --- Jóvenes -----------------------------------------------------------------

HHMM = r"^([01]\d|2[0-3]):[0-5]\d$"
Gender = Literal["femenino", "masculino", "otro", "prefiero_no_decir"]


class TimeSlotIn(ApiModel):
    day: Day
    start: str = Field(pattern=HHMM)
    end: str = Field(pattern=HHMM)


class ProfileSkill(ApiModel):
    skill: Skill
    level: int = Field(ge=1, le=3)
    source: Literal["cv", "entrevista", "orientador"]
    evidence: str


class YouthCreate(ApiModel):
    display_name: str = Field(min_length=1, max_length=120)
    birth_year: int = Field(ge=1990, le=2010)
    gender: Gender | None = None
    location_id: str
    max_commute_min: int = Field(ge=5, le=180)
    transport_budget_daily: float = Field(ge=0, le=50)
    min_salary: float | None = Field(default=None, ge=0, le=5000)
    studying: bool | None = None
    availability: list[TimeSlotIn]


class Youth(ApiModel):
    id: str
    display_name: str
    birth_year: int
    gender: Gender | None = None
    location_id: str
    max_commute_min: int
    transport_budget_daily: float
    min_salary: float | None = None
    studying: bool | None = None
    availability: list[TimeSlot] = []
    skills: list[ProfileSkill] = []
    is_synthetic: bool

    @field_validator("availability", mode="before")
    @classmethod
    def _normalize_availability(cls, value: Any) -> list[dict[str, Any]]:
        return normalize_slots(value)


class InterviewAnswer(ApiModel):
    answer: str | None = Field(default=None, max_length=2000)


class InterviewStep(ApiModel):
    done: bool
    question: str | None = None
    index: int | None = None
    discovered_skills: list[ProfileSkill] = []


# --- Agentes -----------------------------------------------------------------


class Accepted(ApiModel):
    thread_id: str
    resource_id: str | None = None


AgentName = Literal[
    "supervisor",
    "mercado",
    "perfil",
    "matching",
    "formacion",
    "postulacion",
    "entrevista",
    "auditor",
    "orientador",
]


class AgentTrace(ApiModel):
    agent: AgentName
    step: int
    input_summary: str | None = None
    decision: str
    reason: str | None = None
    duration_ms: int | None = None
    langfuse_trace_id: str | None = None
    created_at: datetime


class Trace(ApiModel):
    thread_id: str
    status: Literal["en_curso", "esperando_revision", "completado", "error"]
    steps: list[AgentTrace]


# --- Matching, revisión humana y postulaciones -------------------------------

MatchStatus = Literal["propuesto", "aprobado", "rechazado"]
ReviewKind = Literal["bloqueo_oferta", "lista_corta", "alerta_sesgo"]
ReviewStatus = Literal["pendiente", "aprobada", "editada", "rechazada"]


class ScoreBreakdown(ApiModel):
    skill_coverage: float = Field(ge=0, le=1)
    commute: float = Field(ge=0, le=1)
    cost: float = Field(ge=0, le=1)
    schedule: float = Field(ge=0, le=1)
    salary: float = Field(ge=0, le=1)
    missing_skills: list[str] = []


class ConstraintsChecked(ApiModel):
    commute_min: int
    daily_cost: float
    schedule_overlap: bool
    salary_ok: bool


class MatchResult(ApiModel):
    run_id: str
    youth_id: str
    posting_id: str
    score: float
    score_breakdown: ScoreBreakdown
    constraints_checked: ConstraintsChecked
    explanation: str = ""
    status: MatchStatus

    @field_validator("explanation", mode="before")
    @classmethod
    def _no_null_explanation(cls, value: Any) -> str:
        return value or ""


class MatchRun(ApiModel):
    id: str
    solver_status: Literal["OPTIMAL", "FEASIBLE", "INFEASIBLE", "TIMEOUT"]
    solve_ms: int | None = None
    thread_id: str | None = Field(
        default=None, validation_alias=AliasChoices("graph_thread_id", "thread_id", "threadId")
    )
    results: list[MatchResult]
    audit: list[AuditCheck]


class InterviewSlot(ApiModel):
    starts_at: datetime
    ends_at: datetime


class Application(ApiModel):
    id: str
    match_result: MatchResult
    tailored_cv: str | None = None
    cover_letter: str | None = None
    status: Literal["en_lista_corta", "enviada", "entrevista", "descartada"]
    interview_slots: list[InterviewSlot] = []


class ReviewTask(ApiModel):
    id: str
    kind: ReviewKind
    subject_id: str
    proposal: dict[str, Any]
    explanation: str
    agent: str | None = None
    status: ReviewStatus
    reviewer: str | None = None
    comment: str | None = None
    thread_id: str = Field(
        validation_alias=AliasChoices("graph_thread_id", "thread_id", "threadId")
    )
    created_at: datetime
    resolved_at: datetime | None = None


class ReviewDecision(ApiModel):
    decision: Literal["aprobar", "editar", "rechazar"]
    reviewer: str = Field(min_length=1, max_length=120)
    comment: str | None = Field(default=None, max_length=2000)
    edits: dict[str, Any] | None = None


class MatchRunRequest(ApiModel):
    youth_ids: list[str] | None = None
    posting_ids: list[str] | None = None
    time_limit_seconds: float = Field(default=5.0, ge=1, le=30)
