"""
Scheduler de polling — executa o pipeline automaticamente em intervalos definidos.
Roda em paralelo à API via thread separada.
"""
import logging
from apscheduler.schedulers.background import BackgroundScheduler
from src.config import POLLING_INTERVAL_HOURS
from src.pipeline import run_pipeline

logger = logging.getLogger(__name__)


def start_scheduler() -> BackgroundScheduler:
    scheduler = BackgroundScheduler()
    scheduler.add_job(
        run_pipeline,
        trigger="interval",
        hours=POLLING_INTERVAL_HOURS,
        id="pipeline_polling",
        replace_existing=True,
    )
    scheduler.start()
    logger.info(f"Scheduler iniciado: pipeline roda a cada {POLLING_INTERVAL_HOURS}h")
    return scheduler
