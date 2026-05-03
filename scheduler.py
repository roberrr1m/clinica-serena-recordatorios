import logging
from datetime import datetime, timedelta, timezone

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
from apscheduler.executors.pool import ThreadPoolExecutor

from config import HORA_RECORDATORIO

logger = logging.getLogger(__name__)

_scheduler: BackgroundScheduler | None = None


def get_scheduler() -> BackgroundScheduler:
    global _scheduler
    if _scheduler is None:
        jobstores  = {"default": SQLAlchemyJobStore(url="sqlite:///jobs.sqlite")}
        executors  = {"default": ThreadPoolExecutor(10)}
        _scheduler = BackgroundScheduler(jobstores=jobstores, executors=executors)
        _scheduler.start()
        logger.info("Scheduler iniciado")
    return _scheduler


# ── helpers internos ────────────────────────────────────────────────────────

def _hora_recordatorio_24h(cita_dt: datetime) -> datetime:
    """10:00h del día anterior a la cita."""
    h, m = map(int, HORA_RECORDATORIO.split(":"))
    dia_anterior = (cita_dt - timedelta(days=1)).date()
    return datetime(dia_anterior.year, dia_anterior.month, dia_anterior.day,
                    h, m, tzinfo=cita_dt.tzinfo)


def _run_job(fn, *args):
    try:
        fn(*args)
    except Exception as exc:
        logger.error("Error en job %s: %s", fn.__name__, exc)


# ── jobs públicos ────────────────────────────────────────────────────────────

def programar_recordatorio_24h(cita_id: str, cita_dt: datetime):
    from router import job_recordatorio_24h
    scheduler = get_scheduler()
    run_at = _hora_recordatorio_24h(cita_dt)
    if run_at < datetime.now(tz=cita_dt.tzinfo):
        logger.warning("Recordatorio 24h ya pasado para cita %s — disparando ahora", cita_id)
        run_at = datetime.now(tz=cita_dt.tzinfo) + timedelta(seconds=5)
    scheduler.add_job(
        _run_job, "date", run_date=run_at,
        args=[job_recordatorio_24h, cita_id],
        id=f"rec24h_{cita_id}", replace_existing=True,
    )
    logger.info("Job rec24h_%s programado para %s", cita_id, run_at)


def programar_segundo_aviso(cita_id: str, cita_dt: datetime):
    from router import job_segundo_aviso
    scheduler = get_scheduler()
    run_at = datetime.now(tz=cita_dt.tzinfo) + timedelta(hours=4)
    scheduler.add_job(
        _run_job, "date", run_date=run_at,
        args=[job_segundo_aviso, cita_id],
        id=f"rec24h_aviso2_{cita_id}", replace_existing=True,
    )
    logger.info("Job segundo_aviso_%s programado para %s", cita_id, run_at)


def programar_recordatorio_2h(cita_id: str, cita_dt: datetime):
    from router import job_recordatorio_2h
    scheduler = get_scheduler()
    run_at = cita_dt - timedelta(hours=2)
    if run_at < datetime.now(tz=cita_dt.tzinfo):
        logger.warning("Recordatorio 2h ya pasado para cita %s — omitiendo", cita_id)
        return
    scheduler.add_job(
        _run_job, "date", run_date=run_at,
        args=[job_recordatorio_2h, cita_id],
        id=f"rec2h_{cita_id}", replace_existing=True,
    )
    logger.info("Job rec2h_%s programado para %s", cita_id, run_at)


def cancelar_jobs_cita(cita_id: str):
    scheduler = get_scheduler()
    for job_id in [f"rec24h_{cita_id}", f"rec24h_aviso2_{cita_id}", f"rec2h_{cita_id}"]:
        try:
            scheduler.remove_job(job_id)
            logger.info("Job %s cancelado", job_id)
        except Exception:
            pass
