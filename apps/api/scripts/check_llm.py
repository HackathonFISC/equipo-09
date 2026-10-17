"""¿Funciona el LLM configurado en `.env`? Una llamada real, con el mismo cliente que los agentes.

    cd apps/api
    uv run python scripts/check_llm.py

Imprime el modelo que respondió, la latencia y si hubo que usar el valor por defecto. Úsalo
antes de cada ensayo: si falla, los agentes siguen funcionando, pero con plantillas (sin LLM).
"""

import sys
import time

from pydantic import BaseModel

from puente_api.config import get_settings
from puente_api.llm import LLMClient


class Ping(BaseModel):
    ok: bool
    idioma: str


def main() -> int:
    settings = get_settings()
    print(f"LLM_MODEL={settings.llm_model} · respaldo={settings.llm_fallback_model or '(auto)'}")
    llm = LLMClient(settings)
    start = time.perf_counter()
    out = llm.structured(
        "Responde ok=true e idioma='es'.", Ping, default=Ping(ok=False, idioma="?")
    )
    secs = time.perf_counter() - start
    for call in llm.call_log:
        state = "OK" if call.ok else f"FALLA ({call.note})"
        print(f"  {call.model}: {state} en {call.duration_ms} ms")
    if not out.ok:
        print(f"El LLM NO respondió ({secs:.1f} s). Revisa LLM_API_KEY y LLM_MODEL en .env.")
        return 1
    print(f"El LLM respondió en {secs:.1f} s.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
