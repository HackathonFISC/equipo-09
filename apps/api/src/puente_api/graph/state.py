"""Estado compartido del grafo y dependencias de ejecución.

El estado solo lleva datos serializables (ids, textos, resultados): el checkpointer lo guarda en
cada paso para poder pausar en `interrupt` y reanudar. La sesión de BD y el `LLMClient` viajan en
`config["configurable"]`, no en el estado.
"""

from typing import Any, Literal, TypedDict

from langchain_core.runnables import RunnableConfig
from sqlalchemy.orm import Session

from puente_api.llm import LLMClient

Event = Literal[
    "posting.created", "profile.cv", "profile.interview", "match.requested", "training.requested"
]
Route = Literal["mercado", "perfil", "matching", "formacion"]


class PuenteState(TypedDict, total=False):
    thread_id: str
    event: Event
    payload: dict[str, Any]
    route: Route
    result: dict[str, Any]
    # Corrida de matching: ids exactos de la entrada del solver y su resultado serializado.
    run_id: str
    youth_ids: list[str]
    posting_ids: list[str]
    matching_result: dict[str, Any]
    # `review_task` creadas por los nodos: el nodo `orientador` espera su decisión.
    review_ids: list[str]


def deps(config: RunnableConfig) -> tuple[Session, LLMClient, str]:
    conf = config.get("configurable", {})
    return conf["session"], conf["llm"], conf["thread_id"]
