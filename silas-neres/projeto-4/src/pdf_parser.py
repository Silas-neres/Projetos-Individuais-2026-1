"""
Extração de texto dos PDFs usando PyMuPDF (fitz).
Estratégia Full-Scan: envia texto completo ao LLM, aproveitando
a janela de contexto de 1M tokens do Gemini 2.0 Flash.
"""
import fitz  # PyMuPDF
import logging

logger = logging.getLogger(__name__)

MAX_CHARS = 800_000  # Limite seguro para não exceder o contexto do Gemini


def extract_text_from_bytes(pdf_bytes: bytes) -> str:
    """Extrai todo o texto de um PDF em memória (sem salvar em disco)."""
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    pages_text = []

    for page_num, page in enumerate(doc, start=1):
        text = page.get_text("text")
        if text.strip():
            pages_text.append(f"--- Página {page_num} ---\n{text}")

    full_text = "\n".join(pages_text)
    doc.close()

    if len(full_text) > MAX_CHARS:
        logger.warning(f"PDF truncado: {len(full_text)} chars -> {MAX_CHARS}")
        full_text = full_text[:MAX_CHARS]

    return full_text
