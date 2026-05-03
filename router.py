import logging
import httpx

from config import TELEGRAM_OWNER_CHAT_ID, BOT_SERVICE_URL
from sheets import (
    get_cita_by_id,
    get_cita_pendiente_por_chat_id,
    actualizar_estado,
)
from telegram_client import (
    send_message,
    detect_intent,
    msg_recordatorio_24h,
    msg_segundo_aviso,
    msg_respuesta_si,
    msg_recordatorio_2h,
    msg_respuesta_no,
    msg_cancelacion_dueno,
    msg_sin_contexto,
)
from scheduler import (
    programar_segundo_aviso,
    programar_recordatorio_2h,
    cancelar_jobs_cita,
)

logger = logging.getLogger(__name__)


# ── Mensajes entrantes de Telegram ──────────────────────────────────────────

def handle_incoming_message(chat_id: str, texto: str):
    """
    Punto de entrada para mensajes entrantes de Telegram.
    - SÍ/NO con cita pendiente → gestiona aquí.
    - Cualquier otro mensaje → reenvía al bot principal.
    """
    cita = get_cita_pendiente_por_chat_id(chat_id)

    if cita is None:
        forward_to_bot(chat_id, texto)
        return

    intent = detect_intent(texto)

    if intent == "si":
        _handle_si(chat_id, cita)
    elif intent == "no":
        _handle_no(chat_id, cita)
    else:
        send_message(chat_id, msg_sin_contexto(cita["Fecha"]))


def _handle_si(chat_id: str, cita: dict):
    cita_id = cita["ID_Cita"]
    actualizar_estado(cita_id, "confirmado", confirmado_24h="si")
    send_message(chat_id, msg_respuesta_si())

    dt = _parse_cita_datetime(cita)
    if dt:
        programar_recordatorio_2h(cita_id, dt)


def _handle_no(chat_id: str, cita: dict):
    cita_id = cita["ID_Cita"]
    nombre  = cita["Nombre"]
    fecha   = cita["Fecha"]
    hora    = cita["Hora"]

    actualizar_estado(cita_id, "cancelado", notas="Canceló por Telegram")
    cancelar_jobs_cita(cita_id)

    send_message(chat_id, msg_respuesta_no(nombre))
    if TELEGRAM_OWNER_CHAT_ID:
        send_message(TELEGRAM_OWNER_CHAT_ID, msg_cancelacion_dueno(nombre, fecha, hora))


# ── Jobs del scheduler ───────────────────────────────────────────────────────

def job_recordatorio_24h(cita_id: str):
    cita = get_cita_by_id(cita_id)
    if not cita or cita["Estado"] != "pendiente":
        return
    chat_id = cita.get("ChatID")
    if not chat_id:
        logger.warning("Sin ChatID para cita %s — no se puede enviar recordatorio", cita_id)
        return
    send_message(chat_id, msg_recordatorio_24h(cita["Nombre"], cita["Hora"]))
    dt = _parse_cita_datetime(cita)
    if dt:
        programar_segundo_aviso(cita_id, dt)


def job_segundo_aviso(cita_id: str):
    cita = get_cita_by_id(cita_id)
    if not cita or cita["Estado"] != "pendiente":
        return
    chat_id = cita.get("ChatID")
    if not chat_id:
        return
    send_message(chat_id, msg_segundo_aviso(cita["Nombre"], cita["Hora"]))


def job_recordatorio_2h(cita_id: str):
    cita = get_cita_by_id(cita_id)
    if not cita or cita["Estado"] not in ("pendiente", "confirmado"):
        return
    chat_id = cita.get("ChatID")
    if not chat_id:
        return
    send_message(chat_id, msg_recordatorio_2h(cita["Nombre"]))
    actualizar_estado(cita_id, cita["Estado"], recordatorio_2h="si")


# ── Reenvío al bot principal ─────────────────────────────────────────────────

def forward_to_bot(chat_id: str, texto: str):
    if not BOT_SERVICE_URL:
        return
    try:
        httpx.post(
            f"{BOT_SERVICE_URL}/internal/message",
            json={"chat_id": chat_id, "texto": texto},
            timeout=5,
        )
    except Exception as exc:
        logger.warning("No se pudo reenviar al bot: %s", exc)


# ── Utilidades ───────────────────────────────────────────────────────────────

def _parse_cita_datetime(cita: dict):
    from datetime import datetime, timezone
    try:
        return datetime.strptime(
            f"{cita['Fecha']} {cita['Hora']}", "%d/%m/%Y %H:%M"
        ).replace(tzinfo=timezone.utc)
    except Exception:
        return None
