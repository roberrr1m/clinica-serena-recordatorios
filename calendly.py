import hashlib
import hmac
import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import Request
from config import CALENDLY_WEBHOOK_SECRET

logger = logging.getLogger(__name__)


async def verify_signature(request: Request) -> bool:
    """Verifica la firma HMAC-SHA256 del webhook de Calendly."""
    if not CALENDLY_WEBHOOK_SECRET:
        logger.warning("CALENDLY_WEBHOOK_SECRET no configurado, saltando verificación")
        return True

    header = request.headers.get("Calendly-Webhook-Signature", "")
    body = await request.body()

    # Formato: t=timestamp,v1=signature
    parts = dict(p.split("=", 1) for p in header.split(",") if "=" in p)
    timestamp = parts.get("t", "")
    signature = parts.get("v1", "")

    message = f"{timestamp}.{body.decode()}"
    expected = hmac.new(
        CALENDLY_WEBHOOK_SECRET.encode(),
        message.encode(),
        hashlib.sha256,
    ).hexdigest()

    return hmac.compare_digest(expected, signature)


def _extract_phone(questions: list) -> str:
    """Busca el teléfono en las preguntas personalizadas de Calendly."""
    keywords = ("telefono", "teléfono", "phone", "móvil", "movil", "whatsapp")
    for q in questions:
        label = q.get("question", "").lower()
        if any(kw in label for kw in keywords):
            return q.get("answer", "").strip()
    return ""


def parse_invitee_created(payload: dict) -> Optional[dict]:
    """
    Extrae los datos relevantes del evento invitee.created.
    Devuelve None si faltan campos críticos.
    """
    try:
        p = payload.get("payload", {})
        scheduled = p.get("scheduled_event", {})

        uri = p.get("uri", "")
        cita_id = uri.split("/")[-1] if uri else ""

        nombre   = p.get("name", "Paciente")
        email    = p.get("email", "")
        telefono = _extract_phone(p.get("questions_and_answers", []))

        start_raw = scheduled.get("start_time", "")
        if not start_raw:
            logger.error("start_time ausente en payload")
            return None

        dt = datetime.fromisoformat(start_raw.replace("Z", "+00:00"))
        dt_local = dt.astimezone()    # convierte a zona local del servidor

        DIAS_ES = ["lunes", "martes", "miércoles", "jueves",
                   "viernes", "sábado", "domingo"]
        dia_semana = DIAS_ES[dt_local.weekday()]
        fecha = dt_local.strftime("%d/%m/%Y")
        hora  = dt_local.strftime("%H:%M")

        return {
            "cita_id":       cita_id,
            "nombre":        nombre,
            "email":         email,
            "telefono":      telefono,
            "fecha":         fecha,
            "hora":          hora,
            "dia_semana":    dia_semana,
            "datetime_utc":  dt,
            "reschedule_url": p.get("reschedule_url", ""),
            "cancel_url":    p.get("cancel_url", ""),
            "event_uri":     scheduled.get("uri", ""),
        }
    except Exception as exc:
        logger.error("Error parseando invitee.created: %s", exc)
        return None


def parse_invitee_canceled(payload: dict) -> Optional[dict]:
    try:
        p = payload.get("payload", {})
        scheduled = p.get("scheduled_event", {})

        uri = p.get("uri", "")
        cita_id = uri.split("/")[-1] if uri else ""

        nombre   = p.get("name", "Paciente")
        telefono = _extract_phone(p.get("questions_and_answers", []))

        start_raw = scheduled.get("start_time", "")
        dt = datetime.fromisoformat(start_raw.replace("Z", "+00:00"))
        dt_local = dt.astimezone()
        fecha = dt_local.strftime("%d/%m/%Y")
        hora  = dt_local.strftime("%H:%M")

        return {
            "cita_id":  cita_id,
            "nombre":   nombre,
            "telefono": telefono,
            "fecha":    fecha,
            "hora":     hora,
        }
    except Exception as exc:
        logger.error("Error parseando invitee.canceled: %s", exc)
        return None
