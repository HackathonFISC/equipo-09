"""Lectura de archivos subidos (oferta o CV): texto plano o PDF. La foto (visión) es stretch."""

import io
from dataclasses import dataclass

from fastapi import UploadFile

from puente_api.problems import ProblemError

MAX_BYTES = 5 * 1024 * 1024
MAX_TEXT = 20_000
IMAGE_TYPES = {"image/jpeg", "image/png"}


@dataclass
class UploadedText:
    text: str
    input_type: str  # texto | pdf


def _pdf_text(data: bytes) -> str:
    from pypdf import PdfReader
    from pypdf.errors import PdfReadError

    try:
        reader = PdfReader(io.BytesIO(data))
        return "\n".join(page.extract_text() or "" for page in reader.pages)
    except (PdfReadError, ValueError, OSError) as exc:
        raise ProblemError(422, "No se pudo leer el PDF", "archivo_invalido") from exc


async def read_input(text: str | None, file: UploadFile | None) -> UploadedText:
    """Une el texto del formulario y el del archivo. Lanza 413/422 según el contrato."""
    parts: list[str] = []
    input_type = "texto"
    if text and text.strip():
        parts.append(text.strip())
    if file is not None and file.filename:
        data = await file.read(MAX_BYTES + 1)
        if len(data) > MAX_BYTES:
            raise ProblemError(413, "El archivo supera 5 MB", "archivo_invalido")
        ctype = (file.content_type or "").lower()
        name = file.filename.lower()
        if ctype == "application/pdf" or name.endswith(".pdf"):
            parts.append(_pdf_text(data).strip())
            input_type = "pdf"
        elif ctype in IMAGE_TYPES or name.endswith((".jpg", ".jpeg", ".png")):
            detail = "La lectura de fotos aún no está disponible; sube PDF o texto"
            raise ProblemError(422, detail, "archivo_invalido")
        elif ctype.startswith("text/") or name.endswith(".txt"):
            parts.append(data.decode("utf-8", errors="replace").strip())
        else:
            raise ProblemError(422, f"Tipo de archivo no soportado: {ctype}", "archivo_invalido")
    joined = "\n\n".join(p for p in parts if p)
    if not joined:
        raise ProblemError(422, "Envía `text` o un archivo con contenido legible")
    if len(joined) > MAX_TEXT:
        raise ProblemError(422, f"El texto supera {MAX_TEXT} caracteres", "dato_absurdo")
    return UploadedText(text=joined, input_type=input_type)
