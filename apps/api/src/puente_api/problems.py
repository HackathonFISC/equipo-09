"""Errores `application/problem+json` con el campo opcional `guardrail` del contrato."""

from typing import Literal

from fastapi import HTTPException

Guardrail = Literal["inyeccion", "fuera_de_alcance", "dato_absurdo", "archivo_invalido", "pii"]


class ProblemError(HTTPException):
    def __init__(self, status: int, detail: str, guardrail: Guardrail | None = None) -> None:
        super().__init__(status_code=status, detail=detail)
        self.guardrail = guardrail
