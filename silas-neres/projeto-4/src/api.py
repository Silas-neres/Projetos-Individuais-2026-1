"""
API REST — expõe os dados extraídos para alimentar o Boletim de Conjuntura.

Endpoint principal: GET /api/conjuntura?empresa=MRV&ano=2025&trimestre=3
  → Retorna dados unificados de AMBAS as fontes (prévias individuais e boletins),
    com o campo "fonte" indicando a origem de cada registro.

Endpoint específico: GET /api/boletim?ano=2025&trimestre=3
  → Retorna a visão consolidada de um boletim completo (todas as empresas juntas).
"""
from fastapi import FastAPI, HTTPException, Query, BackgroundTasks
from sqlalchemy import desc
from typing import Optional
from datetime import datetime

from src.database import init_db, get_db, DadosOperacionais, PDFCatalog
from src.database import BoletimConjuntura, BoletimTotal, BoletimEmpresa
from src.schemas import DadosOperacionaisResponse, IngestRequest
from src.pipeline import process_pdf, run_pipeline

app = FastAPI(
    title="Pipeline UDA — Setor Habitacional",
    description="API para consulta de dados operacionais extraídos de PDFs das construtoras brasileiras.",
    version="2.0.0",
)


@app.on_event("startup")
def startup():
    init_db()


# ── Helpers ───────────────────────────────────────────────────────────────────

def _periodo_labels(ano: int, trimestre: int) -> tuple[str, str, str, str]:
    """Gera os nomes dinâmicos das colunas de variação baseado no período."""
    tri_ant = trimestre - 1 if trimestre > 1 else 4
    ano_tri_ant = ano if trimestre > 1 else ano - 1
    aa = str(ano)[2:]
    aa_ant = str(ano - 1)[2:]
    aa_ant2 = str(ano - 2)[2:]
    return (
        f"variacao_vs_{tri_ant}t{str(ano_tri_ant)[2:]}_percentual",
        f"variacao_vs_{trimestre}t{aa_ant}_percentual",
        f"variacao_9m{aa_ant}_vs_9m{aa_ant2}_percentual",
        f"variacao_9m{aa}_vs_9m{aa_ant}_percentual",
    )


def _build_variacao_dict(row, labels: tuple) -> dict:
    l1, l2, l3, l4 = labels
    return {
        l1: float(row.variacao_tri_anterior_pct) if row.variacao_tri_anterior_pct is not None else None,
        l2: float(row.variacao_tri_ano_anterior_pct) if row.variacao_tri_ano_anterior_pct is not None else None,
        l3: float(row.variacao_9m_ano_anterior_pct) if row.variacao_9m_ano_anterior_pct is not None else None,
        l4: float(row.variacao_9m_ano_atual_pct) if row.variacao_9m_ano_atual_pct is not None else None,
        "valor_absoluto": float(row.valor_absoluto) if row.valor_absoluto is not None else None,
    }


def _serialize_boletim(boletim: BoletimConjuntura) -> dict:
    """Reconstrói o JSON do boletim com nomes de campo dinâmicos por período."""
    labels = _periodo_labels(boletim.ano, boletim.trimestre)

    # Totais
    totais = [
        {"metrica": t.metrica, **_build_variacao_dict(t, labels)}
        for t in boletim.totais
    ]

    # Empresas: agrupa lancamentos + vendas por empresa
    empresas_map: dict[str, dict] = {}
    for row in boletim.empresas_data:
        if row.empresa not in empresas_map:
            empresas_map[row.empresa] = {"empresa": row.empresa}
        empresas_map[row.empresa][row.metrica] = _build_variacao_dict(row, labels)

    return {
        "documento": {
            "titulo": boletim.titulo,
            "periodo": boletim.periodo,
            "ano": boletim.ano,
            "trimestre": boletim.trimestre,
            "fonte": boletim.fonte,
            "tipo_documento": boletim.tipo_documento,
            "hash_sha256": boletim.hash_pdf,
        },
        "totais": totais,
        "empresas": list(empresas_map.values()),
        "observacao": boletim.observacao,
    }


# ── Endpoints: Boletim de Conjuntura ─────────────────────────────────────────

@app.get("/api/boletim")
def get_boletim(
    ano: Optional[int] = Query(None, description="Ano (ex: 2025)"),
    trimestre: Optional[int] = Query(None, description="Trimestre: 1, 2, 3 ou 4"),
    empresa: Optional[str] = Query(None, description="Filtrar por empresa específica"),
):
    """
    Retorna boletins de conjuntura com variações % por empresa.
    Exemplo: GET /api/boletim?ano=2025&trimestre=3
    """
    with get_db() as db:
        query = db.query(BoletimConjuntura)
        if ano:
            query = query.filter(BoletimConjuntura.ano == ano)
        if trimestre:
            query = query.filter(BoletimConjuntura.trimestre == trimestre)

        boletins = query.order_by(desc(BoletimConjuntura.ano), desc(BoletimConjuntura.trimestre)).all()

        if not boletins:
            raise HTTPException(status_code=404, detail="Nenhum boletim encontrado para os filtros informados.")

        result = []
        for b in boletins:
            serialized = _serialize_boletim(b)
            # Filtro por empresa (pós-serialização)
            if empresa:
                serialized["empresas"] = [
                    e for e in serialized["empresas"]
                    if empresa.lower() in e["empresa"].lower()
                ]
            result.append(serialized)

        return result


# ── Endpoint Principal: Conjuntura Unificada ──────────────────────────────────

@app.get("/api/conjuntura")
def get_conjuntura(
    empresa: Optional[str] = Query(None, description="Nome da construtora (ex: MRV)"),
    ano: Optional[int] = Query(None, description="Ano (ex: 2025)"),
    trimestre: Optional[int] = Query(None, description="Trimestre: 1, 2, 3 ou 4"),
):
    """
    Endpoint principal — retorna dados de AMBAS as fontes de dados:
    - Prévias operacionais individuais (valores absolutos: unidades, VGV, estoque…)
    - Boletins de conjuntura (variações % por empresa)

    O campo 'fonte' em cada registro indica a origem do dado.
    Exemplo: GET /api/conjuntura?empresa=MRV&ano=2025&trimestre=3
    """
    with get_db() as db:
        result = []

        # ── Fonte 1: Prévias operacionais individuais (valores absolutos) ──
        q = db.query(DadosOperacionais)
        if empresa:
            q = q.filter(DadosOperacionais.empresa.ilike(f"%{empresa}%"))
        if ano:
            q = q.filter(DadosOperacionais.ano == ano)
        if trimestre:
            q = q.filter(DadosOperacionais.trimestre == trimestre)

        for d in q.order_by(desc(DadosOperacionais.ano), desc(DadosOperacionais.trimestre)).all():
            result.append({
                "fonte": "previa_operacional",
                "empresa": d.empresa,
                "ano": d.ano,
                "trimestre": d.trimestre,
                "url_origem": d.url_origem,
                "hash_pdf": d.hash_pdf,
                "data_coleta": d.data_coleta.isoformat() if d.data_coleta else None,
                "nome_arquivo": d.nome_arquivo,
                "dados": {
                    "lancamentos_unidades": d.lancamentos_unidades,
                    "lancamentos_vgv_mil": float(d.lancamentos_vgv_mil) if d.lancamentos_vgv_mil else None,
                    "vendas_liquidas_unidades": d.vendas_liquidas_unidades,
                    "vendas_liquidas_vgv_mil": float(d.vendas_liquidas_vgv_mil) if d.vendas_liquidas_vgv_mil else None,
                    "estoque_unidades": d.estoque_unidades,
                    "estoque_vgv_mil": float(d.estoque_vgv_mil) if d.estoque_vgv_mil else None,
                    "entregas_unidades": d.entregas_unidades,
                    "vso_percentual": float(d.vso_percentual) if d.vso_percentual else None,
                    "unidades_em_obras": d.unidades_em_obras,
                },
            })

        # ── Fonte 2: Boletins de conjuntura (variações % por empresa) ──
        qb = db.query(BoletimEmpresa).join(
            BoletimConjuntura, BoletimEmpresa.boletim_id == BoletimConjuntura.id
        )
        if empresa:
            qb = qb.filter(BoletimEmpresa.empresa.ilike(f"%{empresa}%"))
        if ano:
            qb = qb.filter(BoletimConjuntura.ano == ano)
        if trimestre:
            qb = qb.filter(BoletimConjuntura.trimestre == trimestre)

        # Agrupa por (empresa, boletim) para montar lancamentos + vendas juntos
        empresas_boletim: dict = {}
        for row in qb.all():
            b = row.boletim
            key = (row.empresa, b.ano, b.trimestre, b.id)
            if key not in empresas_boletim:
                labels = _periodo_labels(b.ano, b.trimestre)
                empresas_boletim[key] = {
                    "fonte": "boletim_conjuntura",
                    "empresa": row.empresa,
                    "ano": b.ano,
                    "trimestre": b.trimestre,
                    "periodo": b.periodo,
                    "url_origem": b.url_origem,
                    "hash_pdf": b.hash_pdf,
                    "data_coleta": b.data_coleta.isoformat() if b.data_coleta else None,
                    "nome_arquivo": b.nome_arquivo,
                    "dados": {},
                    "_labels": labels,
                }
            labels = empresas_boletim[key]["_labels"]
            empresas_boletim[key]["dados"][row.metrica] = _build_variacao_dict(row, labels)

        for entry in empresas_boletim.values():
            entry.pop("_labels", None)
            result.append(entry)

        if not result:
            raise HTTPException(
                status_code=404,
                detail="Nenhum dado encontrado. Ingira PDFs via POST /api/ingest."
            )

        return result


# ── Endpoints comuns ──────────────────────────────────────────────────────────

@app.get("/api/empresas")
def list_empresas():
    """Lista todas as empresas com dados no banco (prévias e boletins)."""
    with get_db() as db:
        prev = {r[0] for r in db.query(DadosOperacionais.empresa).distinct().all()}
        bol = {r[0] for r in db.query(BoletimEmpresa.empresa).distinct().all()}
        return {"empresas": sorted(prev | bol)}


@app.get("/api/linhagem")
def get_linhagem(
    empresa: Optional[str] = Query(None),
    ano: Optional[int] = Query(None),
    trimestre: Optional[int] = Query(None),
):
    """Rastreabilidade completa: qual PDF originou cada registro."""
    with get_db() as db:
        result = []

        # Prévias
        q = db.query(DadosOperacionais)
        if empresa:
            q = q.filter(DadosOperacionais.empresa.ilike(f"%{empresa}%"))
        if ano:
            q = q.filter(DadosOperacionais.ano == ano)
        if trimestre:
            q = q.filter(DadosOperacionais.trimestre == trimestre)
        for d in q.all():
            result.append({
                "tipo": "previa_operacional",
                "empresa": d.empresa,
                "ano": d.ano,
                "trimestre": d.trimestre,
                "url_origem": d.url_origem,
                "hash_pdf": d.hash_pdf,
                "nome_arquivo": d.nome_arquivo,
                "data_coleta": d.data_coleta.isoformat() if d.data_coleta else None,
            })

        # Boletins
        qb = db.query(BoletimConjuntura)
        if ano:
            qb = qb.filter(BoletimConjuntura.ano == ano)
        if trimestre:
            qb = qb.filter(BoletimConjuntura.trimestre == trimestre)
        for b in qb.all():
            result.append({
                "tipo": "boletim_conjuntura",
                "periodo": b.periodo,
                "ano": b.ano,
                "trimestre": b.trimestre,
                "url_origem": b.url_origem,
                "hash_pdf": b.hash_pdf,
                "nome_arquivo": b.nome_arquivo,
                "data_coleta": b.data_coleta.isoformat() if b.data_coleta else None,
            })

        return result


@app.get("/api/catalogo")
def get_catalogo(empresa: Optional[str] = Query(None)):
    with get_db() as db:
        query = db.query(PDFCatalog)
        if empresa:
            query = query.filter(PDFCatalog.empresa.ilike(f"%{empresa}%"))
        entries = query.order_by(desc(PDFCatalog.data_coleta)).all()
        return [
            {
                "id": e.id,
                "empresa": e.empresa,
                "nome_arquivo": e.nome_arquivo,
                "url": e.url,
                "hash_sha256": e.hash_sha256,
                "processado": e.processado,
                "erro": e.erro,
                "data_coleta": e.data_coleta.isoformat() if e.data_coleta else None,
                "data_processamento": e.data_processamento.isoformat() if e.data_processamento else None,
            }
            for e in entries
        ]


@app.post("/api/ingest")
def ingest_pdf(payload: IngestRequest, background_tasks: BackgroundTasks):
    """Ingestão manual de PDF via URL."""
    background_tasks.add_task(
        process_pdf,
        url=payload.url,
        empresa=payload.empresa,
        nome_arquivo=payload.url.split("/")[-1],
    )
    return {"status": "enfileirado", "url": payload.url, "empresa": payload.empresa}


@app.post("/api/pipeline/run")
def trigger_pipeline(background_tasks: BackgroundTasks):
    """Dispara o pipeline completo manualmente."""
    background_tasks.add_task(run_pipeline)
    return {"status": "pipeline iniciado", "timestamp": datetime.utcnow().isoformat()}


@app.get("/api/health")
def health():
    return {"status": "ok", "timestamp": datetime.utcnow().isoformat()}
