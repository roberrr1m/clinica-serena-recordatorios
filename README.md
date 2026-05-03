# Recordatorios Anti No-Show — Clínica Serena

Servidor FastAPI que automatiza recordatorios de citas por WhatsApp.

## Flujo completo

```
Reserva en Calendly
  → webhook /calendly/webhook
  → registro en Google Sheets (estado: pendiente)
  → WhatsApp de confirmación inmediata
  → job programado: recordatorio a las 10:00h del día anterior

Día anterior a las 10:00h
  → WhatsApp recordatorio 24h ("¿Confirmas SÍ o NO?")
  → job programado: segundo aviso en 4h si no responde

Paciente responde SÍ
  → estado: confirmado
  → WhatsApp de confirmación
  → job programado: recordatorio 2h antes de la cita

Paciente responde NO
  → estado: cancelado
  → WhatsApp de reagendado al paciente
  → WhatsApp de aviso al dueño
  → jobs cancelados

2h antes de la cita
  → WhatsApp recordatorio final
```

## Configuración paso a paso

### 1. Google Sheets

1. Crea una hoja de cálculo nueva en Google Drive
2. Copia el ID de la URL: `https://docs.google.com/spreadsheets/d/**ID**/edit`
3. Ve a [Google Cloud Console](https://console.cloud.google.com)
4. Crea un proyecto → Habilita Google Sheets API y Google Drive API
5. Crea una cuenta de servicio → descarga el JSON de credenciales
6. Comparte la hoja con el email de la cuenta de servicio (editor)
7. Pon el ID en `GOOGLE_SHEET_ID` y el JSON completo en `GOOGLE_CREDENTIALS_JSON`

La hoja "Citas" se crea automáticamente con las columnas correctas en el primer arranque.

### 2. Meta WhatsApp Cloud API

1. Ve a [developers.facebook.com](https://developers.facebook.com) → crea una app
2. Añade el producto "WhatsApp"
3. Copia el **Access Token** → `META_ACCESS_TOKEN`
4. Copia el **Phone Number ID** → `META_PHONE_NUMBER_ID`
5. En Webhooks, configura:
   - URL: `https://[tu-dominio]/whatsapp/webhook`
   - Verify Token: el valor que pongas en `META_VERIFY_TOKEN`
   - Suscríbete a `messages`

### 3. Calendly Webhooks

1. En Calendly → Integrations → Webhooks → New Webhook
2. URL: `https://[tu-dominio]/calendly/webhook`
3. Eventos: `invitee.created` + `invitee.canceled`
4. Copia el **Signing Key** → `CALENDLY_WEBHOOK_SECRET`
5. **Importante**: añade una pregunta personalizada "Teléfono / WhatsApp" en tu tipo de evento para que el bot pueda enviar mensajes.

### 4. Deploy en Railway

```bash
# Instala Railway CLI
npm install -g @railway/cli
railway login
railway init
railway up
```

Variables de entorno: añádelas en Railway → Settings → Variables.

### 5. Deploy en Render

1. Conecta el repositorio en [render.com](https://render.com)
2. Tipo: Web Service
3. Build Command: `pip install -r requirements.txt`
4. Start Command: `uvicorn main:app --host 0.0.0.0 --port $PORT`
5. Añade las variables de entorno

## Test local

```bash
pip install -r requirements.txt
cp .env.example .env
# rellena el .env con tus credenciales
uvicorn main:app --reload --port 8002
```

Verifica que el servidor responde:
```bash
curl http://localhost:8002/health
```

Simula un webhook de Calendly:
```bash
curl -X POST http://localhost:8002/calendly/webhook \
  -H "Content-Type: application/json" \
  -d @test_payload.json
```

## Coordinación con el bot (Skill 2)

Este servidor y el bot comparten el mismo número de WhatsApp.
- Mensajes SÍ/NO con cita pendiente → los gestiona este servidor
- Cualquier otro mensaje → se reenvía al bot en `BOT_SERVICE_URL/internal/message`

Si no tienes el bot corriendo, deja `BOT_SERVICE_URL` en blanco o apuntando a localhost — el reenvío fallará silenciosamente sin afectar los recordatorios.

## Persistencia de jobs

Los jobs de APScheduler se guardan en `jobs.sqlite` — sobreviven reinicios del servidor. Si necesitas limpiar todos los jobs pendientes:

```python
python -c "import sqlite3; sqlite3.connect('jobs.sqlite').execute('DELETE FROM apscheduler_jobs'); print('Jobs borrados')"
```
