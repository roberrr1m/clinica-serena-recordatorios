import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import PlainTextResponse

from calendly import verify_signature, parse_invitee_created, parse_invitee_canceled
from config import TELEGRAM_OWNER_CHAT_ID, TELEGRAM_TOKEN
from scheduler import get_scheduler
from sheets import (
    registrar_cita, actualizar_estado, get_citas_hoy,
    get_chat_id_por_telefono, registrar_contacto,
)
from telegram_client import (
    send_message,
    msg_confirmacion_reserva,
    msg_cancelacion_calendly,
    msg_cancelacion_dueno,
)
from router import handle_incoming_message
import scheduler as sched_module
import httpx

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    get_scheduler()
    yield


app = FastAPI(title="Recordatorios Clínica Serena — Telegram", lifespan=lifespan)


# ── Healthcheck ──────────────────────────────────────────────────────────────

@app.get("/health")
def health():
    return {"status": "ok"}


# ── Citas del día ────────────────────────────────────────────────────────────

@app.get("/citas/hoy")
def citas_hoy():
    return {"citas": get_citas_hoy()}


# ── Webhook de Calendly ──────────────────────────────────────────────────────

@app.post("/calendly/webhook")
async def calendly_webhook(request: Request):
    if not await verify_signature(request):
        raise HTTPException(status_code=401, detail="Firma inválida")

    payload = await request.json()
    event_type = payload.get("event", "")
    logger.info("Evento Calendly: %s", event_type)

    if event_type == "invitee.created":
        cita = parse_invitee_created(payload)
        if not cita:
            raise HTTPException(status_code=422, detail="Payload inválido")

        # Busca el chat_id si el paciente ya habló con el bot antes
        chat_id = ""
        if cita.get("telefono"):
            chat_id = get_chat_id_por_telefono(cita["telefono"]) or ""
        cita["chat_id"] = chat_id

        registrar_cita(cita)

        if chat_id:
            send_message(
                chat_id,
                msg_confirmacion_reserva(
                    cita["nombre"], cita["dia_semana"],
                    cita["fecha"], cita["hora"],
                    cita["reschedule_url"],
                ),
            )
        else:
            logger.warning(
                "Cita %s sin chat_id — el paciente necesita escribir al bot primero",
                cita["cita_id"],
            )
            if TELEGRAM_OWNER_CHAT_ID:
                send_message(
                    TELEGRAM_OWNER_CHAT_ID,
                    f"📋 Nueva cita de *{cita['nombre']}* el {cita['fecha']} a las {cita['hora']}.\n"
                    f"⚠️ Sin Telegram vinculado — no se pueden enviar recordatorios automáticos.",
                )

        sched_module.programar_recordatorio_24h(cita["cita_id"], cita["datetime_utc"])

    elif event_type == "invitee.canceled":
        cita = parse_invitee_canceled(payload)
        if not cita:
            raise HTTPException(status_code=422, detail="Payload inválido")

        chat_id = get_chat_id_por_telefono(cita.get("telefono", "")) or ""
        actualizar_estado(cita["cita_id"], "cancelado", notas="Canceló desde Calendly")
        sched_module.cancelar_jobs_cita(cita["cita_id"])

        if chat_id:
            send_message(chat_id, msg_cancelacion_calendly(cita["nombre"], cita["fecha"]))
        if TELEGRAM_OWNER_CHAT_ID:
            send_message(
                TELEGRAM_OWNER_CHAT_ID,
                msg_cancelacion_dueno(cita["nombre"], cita["fecha"], cita["hora"]),
            )

    return {"ok": True}


# ── Webhook de Telegram (mensajes entrantes) ─────────────────────────────────

@app.post("/telegram/webhook")
async def telegram_webhook(request: Request):
    payload = await request.json()
    try:
        msg = payload.get("message") or payload.get("edited_message")
        if not msg:
            return {"ok": True}

        chat_id  = str(msg["chat"]["id"])
        texto    = msg.get("text", "")
        nombre   = msg.get("from", {}).get("first_name", "")

        # Guarda el contacto si comparte su número de teléfono
        contact = msg.get("contact")
        if contact and contact.get("phone_number"):
            registrar_contacto(contact["phone_number"], chat_id,
                               contact.get("first_name", nombre))

        if texto:
            logger.info("Telegram de %s (%s): %s", nombre, chat_id, texto[:60])
            handle_incoming_message(chat_id, texto)

    except (KeyError, TypeError) as exc:
        logger.warning("Payload Telegram inesperado: %s", exc)

    return {"ok": True}


# ── Registro manual de contacto (para vincular teléfono ↔ chat_id) ───────────

@app.post("/register")
async def register_contact(request: Request):
    """
    El bot principal (Skill 2) llama a este endpoint cuando un paciente
    proporciona su número de teléfono en la conversación.
    Body: { "telefono": "...", "chat_id": "...", "nombre": "..." }
    """
    body = await request.json()
    telefono = body.get("telefono", "").strip()
    chat_id  = str(body.get("chat_id", "")).strip()
    nombre   = body.get("nombre", "")
    if telefono and chat_id:
        registrar_contacto(telefono, chat_id, nombre)
        # Si hay citas pendientes sin chat_id para este teléfono, las actualiza
        _vincular_citas_pendientes(telefono, chat_id)
    return {"ok": True}


def _vincular_citas_pendientes(telefono: str, chat_id: str):
    """Asigna el chat_id a citas pendientes que tenían ese teléfono sin chat_id."""
    from sheets import get_citas_sheet, _norm_phone, CITAS_HEADERS
    ws = get_citas_sheet()
    rows = ws.get_all_values()
    for i, row in enumerate(rows[1:], start=2):
        if len(row) < 7:
            continue
        phone_match = _norm_phone(row[2]) == _norm_phone(telefono)
        no_chat_id  = not row[3]
        is_pending  = row[6] == "pendiente"
        if phone_match and no_chat_id and is_pending:
            ws.update_cell(i, 4, chat_id)
            logger.info("Chat_id %s vinculado a cita %s", chat_id, row[0])


# ── Endpoint interno (coordinación con bot Skill 2) ──────────────────────────

@app.post("/internal/message")
async def internal_message(request: Request):
    body = await request.json()
    chat_id = str(body.get("chat_id", ""))
    texto   = body.get("texto", "")
    if chat_id and texto:
        handle_incoming_message(chat_id, texto)
    return {"ok": True}


# ── Registrar webhook de Telegram ────────────────────────────────────────────

@app.post("/setup/webhook")
async def setup_webhook(request: Request):
    """
    Registra la URL del webhook en Telegram.
    Body: { "url": "https://tu-dominio.com" }
    """
    body = await request.json()
    base_url = body.get("url", "").rstrip("/")
    webhook_url = f"{base_url}/telegram/webhook"
    r = httpx.post(
        f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/setWebhook",
        json={"url": webhook_url},
    )
    return r.json()
