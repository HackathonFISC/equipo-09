"""Modelos Pydantic de los archivos semilla.

Los archivos referencian entidades por `key` legible (p. ej. `barrio-balboa`); el loader
deriva el UUID con `seed_uuid`. `SeedBundle` valida además las claves foráneas.
"""

from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

Day = Literal["lun", "mar", "mie", "jue", "vie", "sab", "dom"]
HHMM = r"^([01]\d|2[0-3]):[0-5]\d$"


class _Seed(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class TimeSlot(_Seed):
    day: Day
    start: str = Field(pattern=HHMM)
    end: str = Field(pattern=HHMM)

    @model_validator(mode="after")
    def _start_before_end(self) -> "TimeSlot":
        if self.start >= self.end:
            raise ValueError(
                f"franja {self.day} {self.start}-{self.end}: inicio debe ser menor que fin"
            )
        return self


class LocationSeed(_Seed):
    key: str
    corregimiento: str
    distrito: str
    provincia: Literal["Panamá", "Panamá Oeste"]
    lat: float = Field(ge=8.5, le=9.5)
    lng: float = Field(ge=-80.2, le=-79.0)
    metro: bool
    zona: Literal["urbana", "periurbana"]


class CommuteSeed(_Seed):
    origin: str
    dest: str
    minutes: int = Field(ge=1, le=300)
    cost_daily: float = Field(ge=0, le=20)
    mode: Literal["bus", "metro", "mixto"]


class SkillSeed(_Seed):
    key: str
    label_es: str
    group: str
    aliases: list[str] = []
    esco_uri: str | None = None

    @field_validator("aliases", mode="before")
    @classmethod
    def _split_aliases(cls, v: object) -> object:
        if isinstance(v, str):
            return [a.strip() for a in v.split("|") if a.strip()]
        return v

    @field_validator("esco_uri", mode="before")
    @classmethod
    def _empty_uri(cls, v: object) -> object:
        return v or None


class CompanySeed(_Seed):
    key: str
    name: str
    location: str
    contact_email: str
    is_synthetic: bool


class RequirementSeed(_Seed):
    skill: str
    weight: int = Field(ge=1, le=3)
    required: bool


class PostingSeed(_Seed):
    key: str
    company: str
    title: str
    raw_input: str
    input_type: Literal["texto", "foto", "pdf"]
    location: str
    schedule: list[TimeSlot] = Field(min_length=1)
    salary_min: float = Field(ge=0)
    salary_max: float = Field(ge=0)
    vacancies: int = Field(ge=1)
    status: Literal["borrador", "bloqueada", "publicada", "cerrada"]
    requirements: list[RequirementSeed] = Field(min_length=1)
    is_synthetic: bool
    source: str

    @model_validator(mode="after")
    def _salary_range(self) -> "PostingSeed":
        if self.salary_min > self.salary_max:
            raise ValueError(f"{self.key}: salary_min > salary_max")
        return self


class DiscriminationFinding(_Seed):
    kind: Literal[
        "edad",
        "genero",
        "apariencia",
        "foto",
        "estado_civil",
        "embarazo",
        "residencia",
        "nacionalidad",
    ]
    text: str


class DiscriminationLabel(_Seed):
    posting: str
    discriminatory: bool
    findings: list[DiscriminationFinding] = []
    notes: str | None = None


class TrainingCenterSeed(_Seed):
    key: str
    name: str
    location: str
    is_synthetic: bool
    source: str | None = None


class SessionSeed(_Seed):
    key: str
    start_date: date
    seats_total: int = Field(ge=1)
    seats_taken: int = Field(ge=0)
    schedule: list[TimeSlot] = Field(min_length=1)

    @model_validator(mode="after")
    def _seats(self) -> "SessionSeed":
        if self.seats_taken > self.seats_total:
            raise ValueError(f"sesión {self.key}: seats_taken > seats_total")
        return self


class CourseSeed(_Seed):
    key: str
    center: str
    title: str
    hours: int = Field(ge=1)
    cost: float = Field(ge=0)
    skills: list[str] = Field(min_length=1)
    is_synthetic: bool
    sessions: list[SessionSeed] = Field(min_length=1, max_length=3)


class ProfileSkillSeed(_Seed):
    skill: str
    level: int = Field(ge=1, le=3)
    source: Literal["cv", "entrevista", "orientador"]
    evidence: str = Field(min_length=1)


class YouthSeed(_Seed):
    key: str
    display_name: str
    birth_year: int = Field(ge=1990, le=2010)
    gender: Literal["femenino", "masculino", "otro", "prefiero_no_decir"] | None = None
    location: str
    max_commute_min: int = Field(ge=5, le=180)
    transport_budget_daily: float = Field(ge=0, le=50)
    min_salary: float = Field(ge=0, le=5000)
    studying: bool
    availability: list[TimeSlot] = Field(min_length=1)
    cv_raw_text: str | None
    is_synthetic: bool
    persona: str
    skills: list[ProfileSkillSeed] = Field(min_length=1)


class SeedBundle(_Seed):
    locations: list[LocationSeed]
    commute: list[CommuteSeed]
    skills: list[SkillSeed]
    companies: list[CompanySeed]
    postings: list[PostingSeed]
    discrimination_labels: list[DiscriminationLabel]
    training_centers: list[TrainingCenterSeed]
    courses: list[CourseSeed]
    youth: list[YouthSeed]

    @model_validator(mode="after")
    def _foreign_keys(self) -> "SeedBundle":
        errors: list[str] = []

        def unique(name: str, keys: list[str]) -> set[str]:
            if len(keys) != len(set(keys)):
                dupes = sorted({k for k in keys if keys.count(k) > 1})
                errors.append(f"{name}: claves duplicadas {dupes}")
            return set(keys)

        locs = unique("locations", [x.key for x in self.locations])
        skills = unique("skills", [x.key for x in self.skills])
        companies = unique("companies", [x.key for x in self.companies])
        postings = unique("postings", [x.key for x in self.postings])
        centers = unique("training_centers", [x.key for x in self.training_centers])
        unique("courses", [x.key for x in self.courses])
        unique("youth", [x.key for x in self.youth])

        def check(owner: str, ref: str, pool: set[str], kind: str) -> None:
            if ref not in pool:
                errors.append(f"{owner}: {kind} '{ref}' no existe")

        for c in self.commute:
            check("commute", c.origin, locs, "location")
            check("commute", c.dest, locs, "location")
        for c in self.companies:
            check(f"company {c.key}", c.location, locs, "location")
        for p in self.postings:
            check(f"posting {p.key}", p.company, companies, "company")
            check(f"posting {p.key}", p.location, locs, "location")
            for r in p.requirements:
                check(f"posting {p.key}", r.skill, skills, "skill")
            if len({r.skill for r in p.requirements}) != len(p.requirements):
                errors.append(f"posting {p.key}: requisito de habilidad repetido")
        for lab in self.discrimination_labels:
            check("discrimination_labels", lab.posting, postings, "posting")
        for t in self.training_centers:
            check(f"center {t.key}", t.location, locs, "location")
        for c in self.courses:
            check(f"course {c.key}", c.center, centers, "center")
            for s in c.skills:
                check(f"course {c.key}", s, skills, "skill")
            unique(f"course {c.key} sessions", [s.key for s in c.sessions])
        for y in self.youth:
            check(f"youth {y.key}", y.location, locs, "location")
            for s in y.skills:
                check(f"youth {y.key}", s.skill, skills, "skill")
            if len({s.skill for s in y.skills}) != len(y.skills):
                errors.append(f"youth {y.key}: habilidad repetida")

        if errors:
            raise ValueError("Seeds inconsistentes:\n- " + "\n- ".join(errors))
        return self
