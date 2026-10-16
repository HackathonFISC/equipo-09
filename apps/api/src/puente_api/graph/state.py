"""Estado compartido del grafo y dependencias de ejecución.

El estado solo lleva datos serializables (ids, textos, resultados). La sesión de BD y el
`LLMClient` viajan en `config["configurable"]`, así el estado puede ir a un checkpointer (H3).
"""

from typing import Any, Literal, TypedDict

from langchain_core.runnables import RunnableConfig
from sqlalchemy.orm import Session

from puente_api.llm import LLMClient

Event = Literal["posting.created", "profile.cv", "profile.interview"]
Route = Literal["mercado", "perfil"]


class PuenteState(TypedDict, total=False):
    thread_id: str
    event: Event
    payload: dict[str, Any]
    route: Route
    result: dict[str, Any]


def deps(config: RunnableConfig) -> tuple[Session, LLMClient, str]:
    conf = config.get("configurable", {})
    return conf["session"], conf["llm"], conf["thread_id"]
