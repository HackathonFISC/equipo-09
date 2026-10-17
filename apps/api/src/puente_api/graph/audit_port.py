"""Puerto del auditor contrafactual (lo implementa Sebastian en `solvers/auditor.py`).

Interfaz que el nodo `auditor` espera de él:

    def audit_matching(
        matching_input: MatchingInput,        # solvers.matching_adapter
        result: MatchingResult,               # solvers.matching
        attributes: Mapping[str, YouthAttributes],   # youth_id → atributos protegidos
    ) -> Sequence[AuditFinding-like]

Cada hallazgo debe exponer `variable` ("nombre" | "genero" | "corregimiento"), `parity`
(0..1 o None), `passed` (bool) y `findings` (lista de textos), el mismo contenido que el schema
`AuditCheck` del contrato. Se acepta un objeto con esos atributos o un dict.

La implementación real (`solvers.auditor.audit_matching`) tiene otra firma; `_real` la adapta.
Si `puente_api.solvers.auditor` no se puede importar se usa un STUB que NO audita nada: devuelve
una verificación aprobada con un aviso explícito para que la traza y la UI no lo confundan con
un resultado real.
"""

from collections.abc import Mapping, Sequence
from importlib import import_module
from typing import Any, Literal, TypedDict

from pydantic import BaseModel, Field

from puente_api.solvers.matching import MatchingResult
from puente_api.solvers.matching_adapter import MatchingInput

Variable = Literal["nombre", "genero", "corregimiento"]
VARIABLES: tuple[Variable, ...] = ("nombre", "genero", "corregimiento")


class YouthAttributes(TypedDict):
    display_name: str
    gender: str | None
    corregimiento: str | None
    location_id: str
    birth_year: int | None


class AuditFinding(BaseModel):
    variable: Variable | None = None
    parity: float | None = Field(default=None, ge=0, le=1)
    passed: bool
    findings: list[str] = Field(default_factory=list)

    @classmethod
    def from_any(cls, raw: Any) -> "AuditFinding":
        if isinstance(raw, cls):
            return raw

        def get(key: str) -> Any:
            return raw.get(key) if isinstance(raw, Mapping) else getattr(raw, key, None)

        passed = get("passed")
        return cls(
            variable=get("variable"),
            parity=get("parity"),
            passed=True if passed is None else bool(passed),
            findings=[str(f) for f in (get("findings") or [])],
        )


STUB_NOTICE = "STUB: auditor contrafactual no instalado; no se ejecutó ninguna verificación real"


def _stub(
    _input: MatchingInput, _result: MatchingResult, _attrs: Mapping[str, YouthAttributes]
) -> list[AuditFinding]:
    return [
        AuditFinding(variable=v, parity=None, passed=True, findings=[STUB_NOTICE])
        for v in VARIABLES
    ]


def _load_impl():
    try:
        auditor = import_module("puente_api.solvers.auditor")
    except ImportError:
        return None

    def _real(
        inp: MatchingInput, result: MatchingResult, attrs: Mapping[str, YouthAttributes]
    ) -> list[Any]:
        protected = {
            youth_id: auditor.ProtectedAttrs(
                display_name=a["display_name"], gender=a["gender"], birth_year=a["birth_year"]
            )
            for youth_id, a in attrs.items()
        }
        report = auditor.audit_matching(
            inp.youths, inp.postings, inp.commute, result, protected=protected, variables=VARIABLES
        )
        return list(report.checks)

    return _real


def is_stub() -> bool:
    return _load_impl() is None


def audit_matching(
    matching_input: MatchingInput,
    result: MatchingResult,
    attributes: Mapping[str, YouthAttributes],
) -> list[AuditFinding]:
    impl = _load_impl() or _stub
    raw: Sequence[Any] = impl(matching_input, result, attributes)
    return [AuditFinding.from_any(item) for item in raw]
