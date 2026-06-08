"""
Ponto de entrada da aplicação.
Sobe a API FastAPI + o scheduler de polling em background.
"""
import logging
import uvicorn
from src.database import init_db
from src.api import app
from scheduler import start_scheduler

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

if __name__ == "__main__":
    init_db()
    scheduler = start_scheduler()
    try:
        uvicorn.run(app, host="0.0.0.0", port=8000)
    finally:
        scheduler.shutdown()
