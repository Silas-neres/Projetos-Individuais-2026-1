"""
Scraper dos portais de RI (Relações com Investidores) das construtoras.
Varre a página de Central de Resultados, coleta todos os links de PDF
e filtra pelos que parecem ser prévias operacionais ou relatórios de resultado.
"""
import hashlib
import logging
import re
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

from src.config import COMPANIES

logger = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
}


def _normalize_text(text: str) -> str:
    return text.lower().replace("á", "a").replace("é", "e").replace("ê", "e").replace("í", "i").replace("ó", "o").replace("ú", "u").replace("ã", "a").replace("ç", "c")


def _is_relevant_pdf(url: str, link_text: str, keywords: list[str]) -> bool:
    combined = _normalize_text(f"{url} {link_text}")
    return (
        ".pdf" in combined
        and any(_normalize_text(kw) in combined for kw in keywords)
    )


def fetch_pdf_links(company: dict) -> list[dict]:
    """Retorna lista de {'url': ..., 'empresa': ..., 'nome_arquivo': ...} para uma empresa."""
    try:
        resp = requests.get(company["url_ri"], headers=HEADERS, timeout=20)
        resp.raise_for_status()
    except Exception as e:
        logger.warning(f"[{company['nome']}] Falha ao acessar RI: {e}")
        return []

    soup = BeautifulSoup(resp.text, "lxml")
    found = []

    for tag in soup.find_all("a", href=True):
        href = tag["href"].strip()
        text = tag.get_text(strip=True)

        # Resolve URL relativa
        if not href.startswith("http"):
            href = urljoin(company["base_url"], href)

        if _is_relevant_pdf(href, text, company["keywords_pdf"]):
            nome = href.split("/")[-1].split("?")[0] or text
            found.append({
                "url": href,
                "empresa": company["nome"],
                "nome_arquivo": nome,
            })

    logger.info(f"[{company['nome']}] {len(found)} PDFs relevantes encontrados")
    return found


def scrape_all_companies() -> list[dict]:
    """Varre todas as empresas configuradas e retorna todos os PDFs encontrados."""
    all_pdfs = []
    for company in COMPANIES:
        pdfs = fetch_pdf_links(company)
        all_pdfs.extend(pdfs)
    return all_pdfs


def compute_hash(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def download_pdf(url: str) -> tuple[bytes, str]:
    """Baixa o PDF e retorna (conteúdo, hash_sha256)."""
    resp = requests.get(url, headers=HEADERS, timeout=60, stream=True)
    resp.raise_for_status()
    content = resp.content
    return content, compute_hash(content)
