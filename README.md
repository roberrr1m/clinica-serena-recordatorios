# Recordatorios Anti No-Show — Telegram

Servidor FastAPI que automatiza recordatorios de citas por Telegram.
Detecta reservas de Calendly cada 5 minutos (polling) sin necesidad de webhooks (plan gratuito).

## Flujo completo

```
Paciente reserva en Calendly
  → poller detecta la cita en ≤5 min
  → registro en Google Sheets (estado: pendiente)
  → Telegram de confirmación inmediata al paciente

Día anterior a las 10:00h (hora local de la clínica)
  → Telegram recordatorio 24h ("¿Confirmas SÍ o NO?")
  → si no responde en 4h → segundo aviso automático
  → si reservó con menos de 24h de antelación → aviso inmediato

Paciente responde SÍ
  → estado: confirmado
  → Telegram de confirmación
  → recordatorio programado 2h antes de la cita

Paciente responde NO
  → estado: cancelado
  → Telegram con enlace para reagendar
  → aviso al dueño de la clínica
  → jobs cancelados

2h antes de la cita
  → Telegram recordatorio final con dirección y teléfono
```

## Configuración para un nuevo cliente

### 1. Personalizar config.py

Edita los datos de la clínica al inicio de `config.py`:

```python
NOMBRE_CLINICA    = "Nombre de la Clínica"
DIRECCION         = "Calle, Ciudad"
GOOGLE_MAPS_URL   = "https://maps.google.com/?q=..."
CALENDLY_URL      = "https://calendly.com/usuario/evento"
TELEFONO_CLINICA  = "+34 XXX XXX XXX"
HORA_RECORDATORIO = "10:00"        # hora local del recordatorio 24h
CLINICA_TIMEZONE  = "Europe/Madrid"
```

### 2. Google Sheets

1. Crea una hoja de cálculo nueva en Google Drive
2. Copia el **ID** de la URL: `https://docs.google.com/spreadsheets/d/ID/edit`
3. En [Google Cloud Console](https://console.cloud.google.com):
   - Crea un proyecto nuevo (o usa uno existente)
   - Habilita **Google Sheets API** y **Google Drive API**
   - Crea una **cuenta de servicio** → descarga el JSON de credenciales
4. Comparte la hoja con el email de la cuenta de servicio (editor)
5. Las hojas "Citas" y "Contactos" se crean automáticamente en el primer arranque

### 3. Bot de Telegram

1. Habla con [@BotFather](https://t.me/BotFather) → `/newbot` → copia el **token**
2. Para obtener tu `TELEGRAM_OWNER_CHAT_ID`: habla con [@userinfobot](https://t.me/userinfobot)
3. Añade la pregunta "Teléfono móvil" en tu evento de Calendly (Calendly → Edit event → Questions)

### 4. Calendly API

1. En [Calendly](https://calendly.com) → Integrations → API & Webhooks
2. Genera un **Personal Access Token**
3. Para obtener tu `CALENDLY_USER_URI`:
   ```
   curl https://api.calendly.com/users/me -H "Authorization: Bearer TU_TOKEN"
   ```
   Copia el campo `uri` de la respuesta.

### 5. Variables de entorno (.env)

```env
GOOGLE_SHEET_ID=
GOOGLE_CREDENTIALS_JSON=    # contenido completo del JSON de la cuenta de servicio
TELEGRAM_TOKEN=
TELEGRAM_OWNER_CHAT_ID=
CALENDLY_TOKEN=
CALENDLY_USER_URI=
SERVICE_URL=                # URL pública del servidor (para keepalive en Render)
CLINICA_TIMEZONE=Europe/Madrid
```

### 6. Deploy en Render

1. Sube el código a GitHub (repo privado)
2. En [render.com](https://render.com) → New Web Service → conecta el repo
3. Runtime: Docker (usa el Dockerfile incluido)
4. Añade todas las variables de entorno del paso anterior
5. Una vez desplegado, registra el webhook de Telegram:
   ```
   POST https://tu-servicio.onrender.com/setup/webhook
   {"url": "https://tu-servicio.onrender.com"}
   ```

## Vincular pacientes (teléfono ↔ Telegram)

Para que el paciente reciba mensajes, su teléfono de Calendly debe estar vinculado a su chat_id de Telegram. Hay dos formas:

**Automática**: el paciente escribe cualquier mensaje al bot → el servidor registra su chat_id → cuando reserva con ese teléfono, queda vinculado.

**Manual** (desde otro sistema o bot):
```
POST /register
{"telefono": "+34600000000", "chat_id": "123456789", "nombre": "Nombre"}
```

## Endpoints útiles

| Endpoint | Descripción |
|---|---|
| `GET /health` | Estado del servidor |
| `GET /citas/hoy` | Citas programadas para hoy |
| `POST /register` | Vincula teléfono ↔ chat_id manualmente |
| `POST /setup/webhook` | Registra webhook de Telegram |
| `POST /telegram/webhook` | Recibe mensajes del bot (configurado por Telegram) |
| `POST /internal/message` | Inyecta mensaje desde sistema externo |

## Ejemplo montado

El código incluye la configuración de **Clínica Serena** (Sevilla) como ejemplo de referencia.
Para un nuevo cliente: duplica la carpeta, edita `config.py` y las variables de entorno.
