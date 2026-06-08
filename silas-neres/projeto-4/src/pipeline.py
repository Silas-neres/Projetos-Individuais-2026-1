"""
Orquestrador do pipeline: coleta → idempotência → parse → extração → persistência.
Roteamento automático por tipo de documento (boletim vs prévia operacional).
"""
import logging
from datetime import datetime

from src.database import (
    get_db, PDFCatalog, DadosOperacionais,
    BoletimConjuntura, BoletimTotal, BoletimEmpresa
)
from src.scraper import scrape_all_companies, download_pdf
from src.pdf_parser import extract_text_from_bytes, extract_pages_as_images, is_visual_pdf
from src.extractor import detect_document_type, extract_boletim, extract_previa, extract_previa_from_images

logger = logging.getLogger(__name__)


def process_pdf(url: str, empresa: str, nome_arquivo: str = "") -> dict:
    """
    Processa um único PDF end-to-end:
    1. Baixa e calcula hash SHA-256 (idempotência)
    2. Detecta tipo de documento pelo texto
    3. Extrai com o schema correto via Gemini
    4. Persiste com linhagem completa
    """
    logger.info(f"[{empresa}] Processando: {url}")

    try:
        pdf_bytes, hash_sha256 = download_pdf(url)
    except Exception as e:
        logger.error(f"[{empresa}] Falha no download: {e}")
        return {"status": "erro_download", "url": url, "erro": str(e)}

    with get_db() as db:
        # Idempotência
        existing = db.query(PDFCatalog).filter_by(hash_sha256=hash_sha256).first()
        if existing and existing.processado:
            logger.info(f"[{empresa}] Já processado (hash={hash_sha256[:8]}...). Pulando.")
            return {"status": "ja_processado", "hash": hash_sha256}

        if not existing:
            catalog_entry = PDFCatalog(
                url=url,
                hash_sha256=hash_sha256,
                empresa=empresa,
                nome_arquivo=nome_arquivo or url.split("/")[-1],
                data_coleta=datetime.utcnow(),
            )
            db.add(catalog_entry)
            db.flush()
        else:
            catalog_entry = existing

        # Extração de texto
        try:
            pdf_text = extract_text_from_bytes(pdf_bytes)
        except Exception as e:
            catalog_entry.erro = f"Erro parse PDF: {e}"
            logger.error(f"[{empresa}] Erro ao extrair texto: {e}")
            return {"status": "erro_parse", "url": url, "erro": str(e)}

        if not pdf_text.strip():
            catalog_entry.erro = "PDF sem texto extraível (imagem/escaneado)"
            return {"status": "pdf_sem_texto", "url": url}

        # Detecção e roteamento
        doc_type = detect_document_type(pdf_text)
        logger.info(f"[{empresa}] Tipo detectado: {doc_type}")

        try:
            if doc_type == "boletim_conjuntura":
                result = _process_boletim(db, pdf_text, url, hash_sha256, nome_arquivo, catalog_entry)
            elif is_visual_pdf(pdf_text):
                # PDF de slideshow — tabelas estão em imagens, usa Gemini Vision
                logger.info(f"[{empresa}] PDF visual detectado. Usando extração por imagem (Vision).")
                page_images = extract_pages_as_images(pdf_bytes)
                result = _process_previa_vision(db, page_images, empresa, url, hash_sha256, nome_arquivo, catalog_entry)
            else:
                result = _process_previa(db, pdf_text, empresa, url, hash_sha256, nome_arquivo, catalog_entry)
        except Exception as e:
            catalog_entry.erro = f"Erro LLM: {e}"
            logger.error(f"[{empresa}] Erro na extração: {e}")
            return {"status": "erro_llm", "url": url, "erro": str(e)}

        catalog_entry.processado = True
        catalog_entry.data_processamento = datetime.utcnow()
        catalog_entry.erro = None
        return result


def _process_boletim(db, pdf_text, url, hash_sha256, nome_arquivo, catalog_entry) -> dict:
    dados = extract_boletim(pdf_text)

    # Upsert por (ano, trimestre, hash_pdf)
    existing = db.query(BoletimConjuntura).filter_by(
        ano=dados.ano, trimestre=dados.trimestre, hash_pdf=hash_sha256
    ).first()

    if existing:
        # Recria totais e empresas
        for t in existing.totais:
            db.delete(t)
        for e in existing.empresas_data:
            db.delete(e)
        boletim = existing
        boletim.titulo = dados.titulo
        boletim.periodo = dados.periodo
        boletim.fonte = dados.fonte
        boletim.observacao = dados.observacao
    else:
        boletim = BoletimConjuntura(
            titulo=dados.titulo,
            periodo=dados.periodo,
            ano=dados.ano,
            trimestre=dados.trimestre,
            fonte=dados.fonte,
            observacao=dados.observacao,
            tipo_documento=dados.tipo_documento,
            pdf_catalog_id=catalog_entry.id,
            url_origem=url,
            hash_pdf=hash_sha256,
            data_coleta=datetime.utcnow(),
            nome_arquivo=nome_arquivo,
        )
        db.add(boletim)
        db.flush()

    # Persiste totais
    for total in dados.totais:
        db.add(BoletimTotal(
            boletim_id=boletim.id,
            metrica=total.metrica,
            variacao_tri_anterior_pct=total.variacao_vs_trimestre_anterior_pct,
            variacao_tri_ano_anterior_pct=total.variacao_vs_mesmo_trimestre_ano_anterior_pct,
            variacao_9m_ano_anterior_pct=total.variacao_9m_ano_anterior_pct,
            variacao_9m_ano_atual_pct=total.variacao_9m_ano_atual_pct,
            valor_absoluto=total.valor_absoluto,
        ))

    # Persiste dados por empresa (uma linha por empresa por métrica)
    for emp in dados.empresas:
        for metrica, variacao in [("lancamentos", emp.lancamentos), ("vendas", emp.vendas)]:
            db.add(BoletimEmpresa(
                boletim_id=boletim.id,
                empresa=emp.empresa,
                metrica=metrica,
                variacao_tri_anterior_pct=variacao.variacao_vs_trimestre_anterior_pct,
                variacao_tri_ano_anterior_pct=variacao.variacao_vs_mesmo_trimestre_ano_anterior_pct,
                variacao_9m_ano_anterior_pct=variacao.variacao_9m_ano_anterior_pct,
                variacao_9m_ano_atual_pct=variacao.variacao_9m_ano_atual_pct,
                valor_absoluto=variacao.valor_absoluto,
            ))

    return {
        "status": "sucesso",
        "tipo": "boletim_conjuntura",
        "periodo": dados.periodo,
        "ano": dados.ano,
        "trimestre": dados.trimestre,
        "empresas": [e.empresa for e in dados.empresas],
        "hash": hash_sha256,
    }


def _process_previa_vision(db, page_images, empresa, url, hash_sha256, nome_arquivo, catalog_entry) -> dict:
    """Extração via Gemini Vision para PDFs de apresentação (slides com tabelas visuais)."""
    dados = extract_previa_from_images(page_images, empresa)

    existing = db.query(DadosOperacionais).filter_by(
        empresa=dados.empresa, ano=dados.ano, trimestre=dados.trimestre
    ).first()

    if existing:
        _update_dado(existing, dados, url, hash_sha256, nome_arquivo, catalog_entry.id)
    else:
        db.add(DadosOperacionais(
            empresa=dados.empresa, ano=dados.ano, trimestre=dados.trimestre,
            lancamentos_unidades=dados.lancamentos_unidades,
            lancamentos_vgv_mil=dados.lancamentos_vgv_mil,
            vendas_liquidas_unidades=dados.vendas_liquidas_unidades,
            vendas_liquidas_vgv_mil=dados.vendas_liquidas_vgv_mil,
            estoque_unidades=dados.estoque_unidades,
            estoque_vgv_mil=dados.estoque_vgv_mil,
            entregas_unidades=dados.entregas_unidades,
            vso_percentual=dados.vso_percentual,
            unidades_em_obras=dados.unidades_em_obras,
            url_origem=url, hash_pdf=hash_sha256,
            data_coleta=datetime.utcnow(),
            nome_arquivo=nome_arquivo,
            pdf_catalog_id=catalog_entry.id,
        ))

    return {
        "status": "sucesso",
        "tipo": "previa_operacional",
        "metodo_extracao": "vision",
        "empresa": dados.empresa,
        "ano": dados.ano,
        "trimestre": dados.trimestre,
        "hash": hash_sha256,
    }


def _process_previa(db, pdf_text, empresa, url, hash_sha256, nome_arquivo, catalog_entry) -> dict:
    dados = extract_previa(pdf_text, empresa)

    existing = db.query(DadosOperacionais).filter_by(
        empresa=dados.empresa, ano=dados.ano, trimestre=dados.trimestre
    ).first()

    if existing:
        _update_dado(existing, dados, url, hash_sha256, nome_arquivo, catalog_entry.id)
    else:
        db.add(DadosOperacionais(
            empresa=dados.empresa,
            ano=dados.ano,
            trimestre=dados.trimestre,
            lancamentos_unidades=dados.lancamentos_unidades,
            lancamentos_vgv_mil=dados.lancamentos_vgv_mil,
            vendas_liquidas_unidades=dados.vendas_liquidas_unidades,
            vendas_liquidas_vgv_mil=dados.vendas_liquidas_vgv_mil,
            estoque_unidades=dados.estoque_unidades,
            estoque_vgv_mil=dados.estoque_vgv_mil,
            entregas_unidades=dados.entregas_unidades,
            vso_percentual=dados.vso_percentual,
            unidades_em_obras=dados.unidades_em_obras,
            url_origem=url,
            hash_pdf=hash_sha256,
            data_coleta=datetime.utcnow(),
            nome_arquivo=nome_arquivo,
            pdf_catalog_id=catalog_entry.id,
        ))

    return {
        "status": "sucesso",
        "tipo": "previa_operacional",
        "empresa": dados.empresa,
        "ano": dados.ano,
        "trimestre": dados.trimestre,
        "hash": hash_sha256,
    }


def _update_dado(dado, llm, url, hash_sha256, nome_arquivo, catalog_id):
    dado.lancamentos_unidades = llm.lancamentos_unidades
    dado.lancamentos_vgv_mil = llm.lancamentos_vgv_mil
    dado.vendas_liquidas_unidades = llm.vendas_liquidas_unidades
    dado.vendas_liquidas_vgv_mil = llm.vendas_liquidas_vgv_mil
    dado.estoque_unidades = llm.estoque_unidades
    dado.estoque_vgv_mil = llm.estoque_vgv_mil
    dado.entregas_unidades = llm.entregas_unidades
    dado.vso_percentual = llm.vso_percentual
    dado.unidades_em_obras = llm.unidades_em_obras
    dado.url_origem = url
    dado.hash_pdf = hash_sha256
    dado.data_coleta = datetime.utcnow()
    dado.nome_arquivo = nome_arquivo
    dado.pdf_catalog_id = catalog_id


def run_pipeline() -> list[dict]:
    logger.info("=== Iniciando pipeline UDA ===")
    from src.scraper import scrape_all_companies
    pdf_list = scrape_all_companies()
    logger.info(f"Total de PDFs encontrados: {len(pdf_list)}")

    results = []
    for pdf_info in pdf_list:
        result = process_pdf(
            url=pdf_info["url"],
            empresa=pdf_info["empresa"],
            nome_arquivo=pdf_info.get("nome_arquivo", ""),
        )
        results.append(result)

    sucessos = sum(1 for r in results if r["status"] == "sucesso")
    pulados = sum(1 for r in results if r["status"] == "ja_processado")
    erros = sum(1 for r in results if "erro" in r["status"])
    logger.info(f"=== Concluído: {sucessos} novos | {pulados} pulados | {erros} erros ===")
    return results
