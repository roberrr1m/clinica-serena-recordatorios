import re
import httpx
import logging
from config import META_ACCESS_TOKEN, META_PHONE_NUMBER_ID

logger = logging.getLogger(__name__)

WA_API = f"https://graph.facebook.com/v19.0/{META_PHONE_NUMBER_ID}/messages"


def format_phone(phone: str) -> str:
    """Normaliza a formato E.164 sin '+': '34600000000'"""
    digits = re.sub(r"\D", "", phone)
    if digits.startswith("0034"):
        digits = digits[2:]
    if digits.startswith("34") and len(digits) == 11:
        return digits
    if len(digits) == 9:
        return "34" + digits
    return digits


def send_message(telefono: str, mensaje: str) -> bool:
    phone = format_phone(telefono)
    payload = {
        "messaging_product": "whatsapp",
        "to": phone,
        "type": "text",
        "text": {"body": mensaje, "preview_url": False},
    }
    headers = {
        "Authorization": f"Bearer {META_ACCESS_TOKEN}",
        "Content-Type": "application/json",
    }
    try:
        r = httpx.post(WA_API, json=payload, headers=headers, timeout=10)
        r.raise_for_status()
        logger.info("WhatsApp enviado a %s", phone)
        return True
    except Exception as exc:
        logger.error("Error WhatsApp a %s: %s", phone, exc)
        return False


# ── Detección de intención ──────────────────────────────────────────────────

SI_PATTERNS = re.compile(
    r"\b(s[íi]|yes|claro|confirmado|ok|perfecto|all[íi]\s+estar[eé]|ahi\s+estare|👍)\b",
    re.IGNORECASE,
)
NO_PATTERNS = re.compile(
    r"\b(no|cancelar|cancelo|no\s+puedo|imposible|otro\s+d[íi]a|otro\s+dia)\b",
    re.IGNORECASE,
)


def detect_intent(texto: str) -> str:
    """Devuelve 'si', 'no', o 'otro'."""
    t = texto.strip()
    if SI_PATTERNS.search(t):
        return "si"
    if NO_PATTERNS.search(t):
        return "no"
    return "otro"


# ── Mensajes ────────────────────────────────────────────────────────────────

def msg_confirmacion_reserva(nombre: str, dia_semana: str, fecha: str,
                              hora: str, reschedule_url: str) -> str:
    return (
        f"✅ ¡Cita confirmada en Clínica Serena!\n\n"
        f"📅 {dia_semana} {fecha} a las {hora}\n"
        f"📍 Sevilla – te enviaremos la dirección exacta el día antes.\n\n"
        f"Si necesitas cambiarla puedes hacerlo aquí:\n{reschedule_url}\n\n"
        f"¡Hasta pronto! 😊"
    )


def msg_recordatorio_24h(nombre: str, hora: str) -> str:
    return (
        f"Hola {nombre} 👋\n\n"
        f"Mañana a las {hora} tienes tu revisión gratuita en Clínica Serena.\n\n"
        f"📍 Calle Ejemplo 12, Sevilla\n"
        f"🚗 Parking disponible en la puerta\n\n"
        f"¿Confirmas que podrás venir?\n"
        f"Responde *SÍ* o *NO* y te lo confirmamos."
    )


def msg_segundo_aviso(nombre: str, hora: str) -> str:
    return (
        f"Hola {nombre}, no hemos recibido tu confirmación "
        f"para mañana a las {hora} en Clínica Serena.\n\n"
        f"¿Sigues pudiendo venir?\n"
        f"Responde *SÍ* o *NO* – solo un segundo 🙏"
    )


def msg_respuesta_si() -> str:
    from config import GOOGLE_MAPS_URL
    return (
        f"Perfecto, ¡te esperamos mañana! ✅\n\n"
        f"📍 Clínica Serena – Calle Ejemplo 12, Sevilla\n"
        f"🗺️ Cómo llegar: {GOOGLE_MAPS_URL}\n\n"
        f"Recuerda venir sin productos en el pelo si puedes.\n"
        f"¡Hasta mañana! 💪"
    )


def msg_recordatorio_2h(nombre: str) -> str:
    from config import TELEFONO_CLINICA
    return (
        f"¡Hola {nombre}! En 2 horas te esperamos 🏥\n\n"
        f"📍 Clínica Serena – Calle Ejemplo 12, Sevilla\n"
        f"📞 {TELEFONO_CLINICA} si tienes cualquier problema\n\n"
        f"¡Nos vemos pronto! 😊"
    )


def msg_respuesta_no(nombre: str) -> str:
    from config import CALENDLY_URL
    return (
        f"Sin problema {nombre}, entendemos que a veces surgen imprevistos 🙏\n\n"
        f"¿Quieres elegir otro día? Aquí tienes los huecos disponibles:\n"
        f"👉 {CALENDLY_URL}\n\n"
        f"¡Cuando quieras estamos aquí!"
    )


def msg_cancelacion_dueno(nombre: str, telefono: str,
                           fecha: str, hora: str) -> str:
    return (
        f"⚠️ Cancelación recibida\n\n"
        f"Paciente: {nombre}\n"
        f"Teléfono: {telefono}\n"
        f"Cita: {fecha} a las {hora}\n\n"
        f"Ha cancelado y se le ha enviado el enlace para reagendar."
    )


def msg_cancelacion_calendly(nombre: str, fecha: str) -> str:
    from config import CALENDLY_URL
    return (
        f"Hola {nombre}, hemos recibido tu cancelación de la cita del {fecha}.\n\n"
        f"Cuando quieras volver a agendarla:\n"
        f"👉 {CALENDLY_URL}\n\n"
        f"¡Aquí estaremos! 😊"
    )


def msg_sin_contexto(fecha: str) -> str:
    return (
        f"Perdona, solo necesito que respondas "
        f"*SÍ* o *NO* para confirmar tu cita del {fecha} 🙏"
    )
