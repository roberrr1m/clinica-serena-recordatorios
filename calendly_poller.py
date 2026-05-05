"""
Polling de Calendly cada 5 minutos — alternativa a webhooks (plan gratuito).
Detecta reservas nuevas y cancelaciones comparando con Google Sheets.
"""
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional

import httpx
import pytz

from config import CALENDLY_TOKEN, CALENDLY_USER_URI, CLINICA_TIMEZONE, TELEGRAM_OWNER_CHAT_ID
from sheets import registrar_cita, actualizar_estado, get_citas_sheet, get_chat_id_por_telefono
from telegram_client import send_message, msg_confirmacion_reserva, msg_cancelacion_calendly, msg_cancelacion_dueno
import scheduler as sched_module

logger = logging.getLogger(__name__)

CALENDLY_API = "https://api.calendly.com"
DIAS_ES = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]


def _headers():
    return {"Authorization": f"Bearer {CALENDLY_TOKEN}", "Content-Type": "application/json"}


def _get_known_ids() -> set:
    """IDs de citas ya registradas en Google Sheets."""
    ws = get_citas_sheet()
    col = ws.col_values(1)[1:]   # columna ID_Cita, sin header
    return set(col)


def _extract_phone(questions: list) -> str:
    keywords = ("telefono", "teléfono", "phone", "móvil", "movil", "whatsapp")
    for q in questions:
        if any(kw in q.get("question", "").lower() for kw in keywords):
            return q.get("answer", "").strip()
    return ""


def poll_calendly():
    """Consulta eventos activos de las próximas 4 semanas y procesa los nuevos."""
    if not CALENDLY_TOKEN or not CALENDLY_USER_URI:
        logger.warning("CALENDLY_TOKEN o CALENDLY_USER_URI no configurados")
        return

    now = datetime.now(timezone.utc)
    min_time = (now - timedelta(hours=1)).isoformat()
    max_time = (now + timedelta(weeks=4)).isoformat()

    try:
        r = httpx.get(
            f"{CALENDLY_API}/scheduled_events",
            headers=_headers(),
            params={
                "user": CALENDLY_USER_URI,
                "status": "active",
                "min_start_time": min_time,
                "max_start_time": max_time,
                "count": 100,
            },
            timeout=15,
        )
        r.raise_for_status()
        events = r.json().get("collection", [])
    except Exception as exc:
        logger.error("Error consultando Calendly: %s", exc)
        return

    known_ids = _get_known_ids()

    for event in events:
        event_uri = event.get("uri", "")
        cita_id = event_uri.split("/")[-1]

        if cita_id in known_ids:
            continue   # ya procesada

        _process_new_event(cita_id, event_uri, event)


def _process_new_event(cita_id: str, event_uri: str, event: dict):
    """Obtiene invitados y registra la cita nueva."""
    try:
        r = httpx.get(
            f"{CALENDLY_API}/scheduled_events/{cita_id}/invitees",
            headers=_headers(),
            params={"count": 1},
            timeout=10,
        )
        r.raise_for_status()
        invitees = r.json().get("collection", [])
    except Exception as exc:
        logger.error("Error obteniendo invitados de %s: %s", cita_id, exc)
        return

    if not invitees:
        return

    invitee = invitees[0]
    nombre   = invitee.get("name", "Paciente")
    email    = invitee.get("email", "")
    telefono = _extract_phone(invitee.get("questions_and_answers", []))
    reschedule_url = invitee.get("reschedule_url", "")

    start_raw = event.get("start_time", "")
    if not start_raw:
        return

    tz_clinica = pytz.timezone(CLINICA_TIMEZONE)
    dt = datetime.fromisoformat(start_raw.replace("Z", "+00:00")).astimezone(tz_clinica)
    dia_semana = DIAS_ES[dt.weekday()]
    fecha = dt.strftime("%d/%m/%Y")
    hora  = dt.strftime("%H:%M")

    # Busca chat_id si el paciente ya habló con el bot
    chat_id = get_chat_id_por_telefono(telefono) if telefono else ""

    cita = {
        "cita_id": cita_id,
        "nombre":  nombre,
        "email":   email,
        "telefono": telefono,
        "chat_id":  chat_id,
        "fecha":    fecha,
        "hora":     hora,
        "dia_semana": dia_semana,
        "datetime_utc": dt.astimezone(timezone.utc),
        "reschedule_url": reschedule_url,
    }

    registrar_cita(cita)
    logger.info("Nueva cita registrada: %s — %s %s", nombre, fecha, hora)

    if chat_id:
        send_message(chat_id, msg_confirmacion_reserva(
            nombre, dia_semana, fecha, hora, reschedule_url
        ))
    elif TELEGRAM_OWNER_CHAT_ID:
        send_message(
            TELEGRAM_OWNER_CHAT_ID,
            f"📋 Nueva cita: *{nombre}* el {fecha} a las {hora}\n"
            f"⚠️ Sin Telegram vinculado — recordatorios no disponibles.",
        )

    from datetime import timezone as tz
    sched_module.programar_recordatorio_24h(cita_id, dt.astimezone(tz.utc))


def poll_cancelaciones():
    """Detecta citas que estaban pendientes y ahora están canceladas en Calendly."""
    if not CALENDLY_TOKEN:
        return

    ws = get_citas_sheet()
    rows = ws.get_all_values()[1:]

    for row in rows:
        if len(row) < 7 or row[6] not in ("pendiente", "confirmado"):
            continue

        cita_id = row[0]
        if not cita_id:
            continue

        try:
            r = httpx.get(
                f"{CALENDLY_API}/scheduled_events/{cita_id}",
                headers=_headers(),
                timeout=10,
            )
            if r.status_code == 404:
                continue
            r.raise_for_status()
            event = r.json().get("resource", {})

            if event.get("status") == "canceled":
                actualizar_estado(cita_id, "cancelado", notas="Canceló desde Calendly")
                sched_module.cancelar_jobs_cita(cita_id)

                nombre   = row[1]
                chat_id  = row[3]
                fecha    = row[4]
                hora     = row[5]

                if chat_id:
                    send_message(chat_id, msg_cancelacion_calendly(nombre, fecha))
                if TELEGRAM_OWNER_CHAT_ID:
                    send_message(TELEGRAM_OWNER_CHAT_ID,
                                 msg_cancelacion_dueno(nombre, fecha, hora))
                logger.info("Cita %s marcada como cancelada", cita_id)

        except Exception as exc:
            logger.warning("Error comprobando cancelación de %s: %s", cita_id, exc)
