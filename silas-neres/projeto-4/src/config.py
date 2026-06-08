import os
from dotenv import load_dotenv

load_dotenv()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://uda_user:uda_password@localhost:5432/uda_pipeline")
POLLING_INTERVAL_HOURS = int(os.getenv("POLLING_INTERVAL_HOURS", "24"))
GEMINI_MODEL = "gemini-flash-latest"

# Construtoras monitoradas — adicione ou remova conforme necessário
COMPANIES = [
    {
        "nome": "MRV",
        "url_ri": "https://ri.mrv.com.br/resultados/central-de-resultados",
        "keywords_pdf": ["prévia", "previa", "operacional", "resultado"],
        "base_url": "https://ri.mrv.com.br",
    },
    {
        "nome": "Direcional",
        "url_ri": "https://ri.direcional.com.br/pt/informacoes-aos-investidores/central-de-resultados",
        "keywords_pdf": ["prévia", "previa", "operacional", "resultado"],
        "base_url": "https://ri.direcional.com.br",
    },
    {
        "nome": "Cury",
        "url_ri": "https://ri.cury.com.br/pt/informacoes-aos-investidores/central-de-resultados",
        "keywords_pdf": ["prévia", "previa", "operacional", "resultado"],
        "base_url": "https://ri.cury.com.br",
    },
    {
        "nome": "Tenda",
        "url_ri": "https://ri.construtora-tenda.com.br/central-de-resultados/",
        "keywords_pdf": ["prévia", "previa", "operacional", "resultado"],
        "base_url": "https://ri.construtora-tenda.com.br",
    },
    {
        "nome": "Plano&Plano",
        "url_ri": "https://ri.planoplano.com.br/central-de-resultados",
        "keywords_pdf": ["prévia", "previa", "operacional", "resultado"],
        "base_url": "https://ri.planoplano.com.br",
    },
]
