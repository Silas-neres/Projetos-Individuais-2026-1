"""
Contratos Semânticos — define o que o LLM extrai e como validar.
Dois contratos distintos por tipo de documento:
  - BoletimConjunturaLLM  → PDFs com variações % de múltiplas empresas
  - DadosOperacionaisLLM  → Prévias individuais com valores absolutos
"""
from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime


# ── Contrato: Boletim de Conjuntura ───────────────────────────────────────────

class MetricaVariacoes(BaseModel):
    """Variações percentuais de uma métrica em 4 comparações de período."""
    variacao_vs_trimestre_anterior_pct: Optional[float] = Field(
        None,
        description=(
            "Variação % versus o trimestre imediatamente anterior. "
            "Ex: 3T25 vs 2T25. Retorne apenas o número (ex: -32 para -32%)."
        )
    )
    variacao_vs_mesmo_trimestre_ano_anterior_pct: Optional[float] = Field(
        None,
        description="Variação % versus o mesmo trimestre do ano anterior. Ex: 3T25 vs 3T24."
    )
    variacao_9m_ano_anterior_pct: Optional[float] = Field(
        None,
        description=(
            "Variação % acumulada 9 meses do ano anterior vs 9 meses do ano retrasado. "
            "Ex: coluna '9m24/23'."
        )
    )
    variacao_9m_ano_atual_pct: Optional[float] = Field(
        None,
        description=(
            "Variação % acumulada 9 meses do ano atual vs 9 meses do ano anterior. "
            "Ex: coluna '9m25/24'."
        )
    )
    valor_absoluto: Optional[float] = Field(
        None,
        description="Valor absoluto total (unidades, VGV etc). null se não estiver no documento."
    )


class EmpresaBoletim(BaseModel):
    empresa: str = Field(description="Nome da construtora/incorporadora")
    lancamentos: MetricaVariacoes = Field(description="Variações de lançamentos para esta empresa")
    vendas: MetricaVariacoes = Field(description="Variações de vendas para esta empresa")


class TotalBoletim(BaseModel):
    metrica: str = Field(description="Nome da métrica: 'lancamentos' ou 'vendas'")
    variacao_vs_trimestre_anterior_pct: Optional[float] = Field(
        None, description="Variação % total do setor vs trimestre anterior"
    )
    variacao_vs_mesmo_trimestre_ano_anterior_pct: Optional[float] = Field(
        None, description="Variação % total do setor vs mesmo trimestre ano anterior"
    )
    variacao_9m_ano_anterior_pct: Optional[float] = Field(
        None, description="Variação % 9m do ano anterior vs ano retrasado"
    )
    variacao_9m_ano_atual_pct: Optional[float] = Field(
        None, description="Variação % 9m do ano atual vs ano anterior"
    )
    valor_absoluto: Optional[float] = Field(None, description="Valor absoluto total do setor. null se ausente.")


class BoletimConjunturaLLM(BaseModel):
    """Schema passado ao Gemini para extração de Boletins de Conjuntura (múltiplas empresas, variações %)."""
    titulo: str = Field(description="Título do documento (ex: 'Conjuntura do Setor Habitacional')")
    periodo: str = Field(description="Período no formato TT/AA ou TTAA (ex: '3T25')")
    ano: int = Field(description="Ano de referência (ex: 2025)")
    trimestre: int = Field(description="Trimestre de referência: 1, 2, 3 ou 4")
    fonte: Optional[str] = Field(None, description="Fonte dos dados informada no documento")
    tipo_documento: str = Field(description="Tipo do documento. Sempre retorne: 'boletim_conjuntura'")
    totais: list[TotalBoletim] = Field(description="Totais consolidados do setor por métrica")
    empresas: list[EmpresaBoletim] = Field(description="Dados de variação por empresa")
    observacao: Optional[str] = Field(None, description="Comentário ou análise textual presente no documento")


# ── Contrato: Prévia Operacional (empresa individual) ─────────────────────────

class DadosOperacionaisLLM(BaseModel):
    """Schema passado ao Gemini para extração de prévias operacionais individuais."""

    empresa: str = Field(description="Nome da construtora ou incorporadora")
    ano: int = Field(description="Ano de referência do relatório (ex: 2025)")
    trimestre: int = Field(description="Trimestre de referência: 1, 2, 3 ou 4")

    lancamentos_unidades: Optional[int] = Field(
        None, description="Unidades lançadas no trimestre. Valor absoluto, não variação percentual."
    )
    lancamentos_vgv_mil: Optional[float] = Field(
        None, description="VGV de lançamentos em R$ mil. Se o documento usar R$ milhões, multiplique por 1000."
    )
    vendas_liquidas_unidades: Optional[int] = Field(
        None, description="Unidades de vendas líquidas (brutas menos distratos) no trimestre."
    )
    vendas_liquidas_vgv_mil: Optional[float] = Field(
        None, description="VGV de vendas líquidas em R$ mil. Se o documento usar R$ milhões, multiplique por 1000."
    )
    estoque_unidades: Optional[int] = Field(None, description="Unidades em estoque ao final do trimestre.")
    estoque_vgv_mil: Optional[float] = Field(
        None, description="VGV do estoque em R$ mil. Se o documento usar R$ milhões, multiplique por 1000."
    )
    entregas_unidades: Optional[int] = Field(None, description="Unidades entregues (habite-se ou chaves) no trimestre.")
    vso_percentual: Optional[float] = Field(
        None, description="VSO em %. Retorne o número puro (ex: 15.3 para 15,3%)."
    )
    unidades_em_obras: Optional[int] = Field(None, description="Unidades em construção ao final do trimestre.")


# ── Schemas de Resposta da API ─────────────────────────────────────────────────

class DadosOperacionaisResponse(BaseModel):
    id: int
    empresa: str
    ano: int
    trimestre: int
    lancamentos_unidades: Optional[int]
    lancamentos_vgv_mil: Optional[float]
    vendas_liquidas_unidades: Optional[int]
    vendas_liquidas_vgv_mil: Optional[float]
    estoque_unidades: Optional[int]
    estoque_vgv_mil: Optional[float]
    entregas_unidades: Optional[int]
    vso_percentual: Optional[float]
    unidades_em_obras: Optional[int]
    url_origem: str
    hash_pdf: str
    data_coleta: datetime
    nome_arquivo: Optional[str]
    created_at: datetime

    model_config = {"from_attributes": True}


class IngestRequest(BaseModel):
    url: str = Field(description="URL direta do PDF na Central de Resultados")
    empresa: str = Field(description="Nome da construtora")
