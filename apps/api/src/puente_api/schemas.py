"""Esquemas de respuesta: reflejan `components/schemas` de packages/api-spec/openapi.yaml."""

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
