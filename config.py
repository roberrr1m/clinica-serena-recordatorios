import os
from dotenv import load_dotenv

load_dotenv()

NOMBRE_CLINICA   = "Clínica Serena"
DIRECCION        = "Calle Ejemplo 12, Sevilla"
GOOGLE_MAPS_URL  = "https://maps.google.com/?q=Clinica+Serena+Sevilla"
CALENDLY_URL     = "https://calendly.com/roberto-xylenai/30min"
TELEFONO_CLINICA = "+34 954 000 000"
HORA_RECORDATORIO = "10:00"   # hora del recordatorio 24h antes

# Telegram
TELEGRAM_TOKEN          = os.getenv("TELEGRAM_TOKEN", "")
TELEGRAM_OWNER_CHAT_ID  = os.getenv("TELEGRAM_OWNER_CHAT_ID", "")   # chat_id del dueño

# Google Sheets
GOOGLE_SHEET_ID          = os.getenv("GOOGLE_SHEET_ID", "")
GOOGLE_CREDENTIALS_JSON  = os.getenv("GOOGLE_CREDENTIALS_JSON", "")
GOOGLE_CREDENTIALS_FILE  = os.getenv("GOOGLE_CREDENTIALS_FILE", "credentials.json")

# Calendly
CALENDLY_WEBHOOK_SECRET = os.getenv("CALENDLY_WEBHOOK_SECRET", "")

# Coordinación con el bot principal (Skill 2)
BOT_SERVICE_URL = os.getenv("BOT_SERVICE_URL", "")
PORT            = int(os.getenv("PORT", "8002"))
