from sqlalchemy import (
    create_engine, Column, Integer, String, Boolean,
    DateTime, ForeignKey, Numeric, Text, UniqueConstraint
)
from sqlalchemy.orm import declarative_base, sessionmaker, relationship
from datetime import datetime
from contextlib import contextmanager
from src.config import DATABASE_URL

engine = create_engine(DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine)
Base = declarative_base()


class PDFCatalog(Base):
    """Catálogo de PDFs coletados — garante idempotência via hash SHA-256."""
    __tablename__ = "pdf_catalog"

    id = Column(Integer, primary_key=True)
    url = Column(Text, nullable=False)
    hash_sha256 = Column(String(64), unique=True, nullable=False)
    empresa = Column(String(100))
    nome_arquivo = Column(Text)
    processado = Column(Boolean, default=False)
    erro = Column(Text, nullable=True)
    data_coleta = Column(DateTime, default=datetime.utcnow)
    data_processamento = Column(DateTime, nullable=True)

    dados_operacionais = relationship("DadosOperacionais", back_populates="pdf_catalog_rel")
    boletins = relationship("BoletimConjuntura", back_populates="pdf_catalog_rel")


# ── Tabelas: Prévia Operacional (empresa individual) ──────────────────────────

class DadosOperacionais(Base):
    """Dados operacionais extraídos de prévias individuais com linhagem completa."""
    __tablename__ = "dados_operacionais"

    id = Column(Integer, primary_key=True)
    empresa = Column(String(100), nullable=False)
    ano = Column(Integer, nullable=False)
    trimestre = Column(Integer, nullable=False)

    lancamentos_unidades = Column(Integer, nullable=True)
    lancamentos_vgv_mil = Column(Numeric(15, 2), nullable=True)
    vendas_liquidas_unidades = Column(Integer, nullable=True)
    vendas_liquidas_vgv_mil = Column(Numeric(15, 2), nullable=True)
    estoque_unidades = Column(Integer, nullable=True)
    estoque_vgv_mil = Column(Numeric(15, 2), nullable=True)
    entregas_unidades = Column(Integer, nullable=True)
    vso_percentual = Column(Numeric(5, 2), nullable=True)
    unidades_em_obras = Column(Integer, nullable=True)

    pdf_catalog_id = Column(Integer, ForeignKey("pdf_catalog.id"), nullable=True)
    url_origem = Column(Text, nullable=False)
    hash_pdf = Column(String(64), nullable=False)
    data_coleta = Column(DateTime, nullable=False)
    nome_arquivo = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    pdf_catalog_rel = relationship("PDFCatalog", back_populates="dados_operacionais")

    __table_args__ = (
        UniqueConstraint("empresa", "ano", "trimestre", name="uq_empresa_periodo"),
    )


# ── Tabelas: Boletim de Conjuntura (múltiplas empresas) ───────────────────────

class BoletimConjuntura(Base):
    """Metadados do boletim de conjuntura e linhagem do PDF."""
    __tablename__ = "boletim_conjuntura"

    id = Column(Integer, primary_key=True)
    titulo = Column(Text)
    periodo = Column(String(10))   # ex: "3T25"
    ano = Column(Integer, nullable=False)
    trimestre = Column(Integer, nullable=False)
    fonte = Column(Text)
    observacao = Column(Text)
    tipo_documento = Column(String(50), default="boletim_conjuntura")

    pdf_catalog_id = Column(Integer, ForeignKey("pdf_catalog.id"), nullable=True)
    url_origem = Column(Text, nullable=False)
    hash_pdf = Column(String(64), nullable=False)
    data_coleta = Column(DateTime, nullable=False)
    nome_arquivo = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)

    totais = relationship("BoletimTotal", back_populates="boletim", cascade="all, delete-orphan")
    empresas_data = relationship("BoletimEmpresa", back_populates="boletim", cascade="all, delete-orphan")
    pdf_catalog_rel = relationship("PDFCatalog", back_populates="boletins")

    __table_args__ = (
        UniqueConstraint("ano", "trimestre", "hash_pdf", name="uq_boletim_periodo_hash"),
    )


class BoletimTotal(Base):
    """Totais consolidados do setor para cada métrica do boletim."""
    __tablename__ = "boletim_total"

    id = Column(Integer, primary_key=True)
    boletim_id = Column(Integer, ForeignKey("boletim_conjuntura.id"), nullable=False)
    metrica = Column(String(50), nullable=False)   # 'lancamentos' ou 'vendas'

    variacao_tri_anterior_pct = Column(Numeric(8, 2))
    variacao_tri_ano_anterior_pct = Column(Numeric(8, 2))
    variacao_9m_ano_anterior_pct = Column(Numeric(8, 2))
    variacao_9m_ano_atual_pct = Column(Numeric(8, 2))
    valor_absoluto = Column(Numeric(15, 2))

    boletim = relationship("BoletimConjuntura", back_populates="totais")


class BoletimEmpresa(Base):
    """Variações por empresa e por métrica dentro de um boletim."""
    __tablename__ = "boletim_empresa"

    id = Column(Integer, primary_key=True)
    boletim_id = Column(Integer, ForeignKey("boletim_conjuntura.id"), nullable=False)
    empresa = Column(String(100), nullable=False)
    metrica = Column(String(50), nullable=False)   # 'lancamentos' ou 'vendas'

    variacao_tri_anterior_pct = Column(Numeric(8, 2))
    variacao_tri_ano_anterior_pct = Column(Numeric(8, 2))
    variacao_9m_ano_anterior_pct = Column(Numeric(8, 2))
    variacao_9m_ano_atual_pct = Column(Numeric(8, 2))
    valor_absoluto = Column(Numeric(15, 2))

    boletim = relationship("BoletimConjuntura", back_populates="empresas_data")


# ── Setup ──────────────────────────────────────────────────────────────────────

def init_db():
    Base.metadata.create_all(engine)


@contextmanager
def get_db():
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
