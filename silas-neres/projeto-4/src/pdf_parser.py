"""
Extração de PDFs usando PyMuPDF (fitz).

Estratégia principal  — Full-Scan de texto: suficiente para a maioria dos PDFs.
Estratégia de fallback — Imagens por página: acionada quando o PDF é de apresentação
(slides com tabelas gráficas) e o texto extraído é muito escasso para o LLM processar.
"""
import fitz  # PyMuPDF
import logging

logger = logging.getLogger(__name__)

MAX_CHARS = 800_000
MIN_CHARS_PARA_TEXTO = 300  # Abaixo disso, PDF provavelmente é slideshow visual
MAX_PAGINAS_IMAGEM = 15     # Limite de páginas para extração por imagem
DPI_IMAGEM = 150            # Resolução suficiente para leitura de tabelas


def extract_text_from_bytes(pdf_bytes: bytes) -> str:
    """Extrai texto completo do PDF. Retorna string vazia se PDF for visual/escaneado."""
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


def is_visual_pdf(text: str) -> bool:
    """
    Detecta PDFs de apresentação (slides) onde os dados operacionais estão em
    tabelas gráficas (imagens), não em texto selecionável.

    PDFs textuais com dados reais têm centenas de números >= 100 (unidades,
    VGV, etc.). Slides têm apenas números de página e referências soltas.
    Threshold calibrado comparando Tenda/text (266 números >= 100) vs
    MRV/slides (~8 números >= 100).
    """
    import re
    if len(text.strip()) < MIN_CHARS_PARA_TEXTO:
        return True
    try:
        nums_grandes = [
            n for n in re.findall(r'\b\d[\d.,]*\b', text)
            if float(n.replace('.', '').replace(',', '.')) >= 100
        ]
    except ValueError:
        nums_grandes = []
    return len(nums_grandes) < 15


def extract_pages_as_images(pdf_bytes: bytes) -> list[bytes]:
    """
    Converte cada página do PDF em PNG (bytes).
    Usado como fallback para PDFs de apresentação com tabelas visuais.
    Limitado a MAX_PAGINAS_IMAGEM para não sobrecarregar o contexto do Gemini.
    """
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    images = []

    total = min(len(doc), MAX_PAGINAS_IMAGEM)
    for i in range(total):
        page = doc[i]
        pixmap = page.get_pixmap(dpi=DPI_IMAGEM)
        images.append(pixmap.tobytes("png"))

    doc.close()
    logger.info(f"PDF convertido em {len(images)} imagens (fallback visual)")
    return images
