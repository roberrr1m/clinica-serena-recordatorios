import json
import logging
from datetime import datetime
from typing import Optional

import gspread
from google.oauth2.service_account import Credentials
from config import GOOGLE_SHEET_ID, GOOGLE_CREDENTIALS_JSON, GOOGLE_CREDENTIALS_FILE

logger = logging.getLogger(__name__)

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

CITAS_HEADERS = [
    "ID_Cita", "Nombre", "Telefono", "ChatID", "Fecha", "Hora",
    "Estado", "Confirmado_24h", "Recordatorio_2h", "Notas", "Timestamp",
]

CONTACTOS_HEADERS = ["Telefono", "ChatID", "Nombre", "Timestamp"]

_client: Optional[gspread.Client] = None


def get_client() -> gspread.Client:
    global _client
    if _client is None:
        if GOOGLE_CREDENTIALS_JSON:
            creds_info = json.loads(GOOGLE_CREDENTIALS_JSON)
            creds = Credentials.from_service_account_info(creds_info, scopes=SCOPES)
        else:
            creds = Credentials.from_service_account_file(
                GOOGLE_CREDENTIALS_FILE, scopes=SCOPES
            )
        _client = gspread.authorize(creds)
    return _client


def _get_or_create_sheet(name: str, headers: list) -> gspread.Worksheet:
    spreadsheet = get_client().open_by_key(GOOGLE_SHEET_ID)
    try:
        ws = spreadsheet.worksheet(name)
    except gspread.WorksheetNotFound:
        ws = spreadsheet.add_worksheet(name, rows=1000, cols=len(headers))
        ws.append_row(headers)
    return ws


def get_citas_sheet() -> gspread.Worksheet:
    return _get_or_create_sheet("Citas", CITAS_HEADERS)


def get_contactos_sheet() -> gspread.Worksheet:
    return _get_or_create_sheet("Contactos", CONTACTOS_HEADERS)


# ── Contactos: teléfono ↔ chat_id ───────────────────────────────────────────

def registrar_contacto(telefono: str, chat_id: int | str, nombre: str = ""):
    """Guarda o actualiza el vínculo teléfono → chat_id."""
    ws = get_contactos_sheet()
    phones = ws.col_values(1)
    phone_norm = _norm_phone(telefono)
    for i, p in enumerate(phones[1:], start=2):
        if _norm_phone(p) == phone_norm:
            ws.update_cell(i, 2, str(chat_id))
            return
    ws.append_row([telefono, str(chat_id), nombre,
                   datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")])


def get_chat_id_por_telefono(telefono: str) -> Optional[str]:
    ws = get_contactos_sheet()
    rows = ws.get_all_values()[1:]
    phone_norm = _norm_phone(telefono)
    for row in rows:
        if len(row) >= 2 and _norm_phone(row[0]) == phone_norm:
            return row[1]
    return None


def _norm_phone(phone: str) -> str:
    digits = "".join(c for c in phone if c.isdigit())
    return digits[-9:] if len(digits) >= 9 else digits


# ── Citas ────────────────────────────────────────────────────────────────────

def registrar_cita(cita: dict) -> int:
    ws = get_citas_sheet()
    row = [
        cita.get("cita_id", ""),
        cita.get("nombre", ""),
        cita.get("telefono", ""),
        cita.get("chat_id", ""),
        cita.get("fecha", ""),
        cita.get("hora", ""),
        "pendiente", "no", "no", "",
        datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
    ]
    ws.append_row(row)
    return len(ws.get_all_values())


def _find_row(ws: gspread.Worksheet, col: int, value: str) -> Optional[int]:
    values = ws.col_values(col)
    for i, v in enumerate(values):
        if v == value:
            return i + 1
    return None


def actualizar_estado(cita_id: str, estado: str,
                      confirmado_24h: Optional[str] = None,
                      recordatorio_2h: Optional[str] = None,
                      notas: Optional[str] = None,
                      chat_id: Optional[str] = None):
    ws = get_citas_sheet()
    row_num = _find_row(ws, 1, cita_id)
    if row_num is None:
        logger.warning("cita_id %s no encontrado", cita_id)
        return
    ws.update_cell(row_num, 7, estado)
    if confirmado_24h is not None:
        ws.update_cell(row_num, 8, confirmado_24h)
    if recordatorio_2h is not None:
        ws.update_cell(row_num, 9, recordatorio_2h)
    if notas is not None:
        ws.update_cell(row_num, 10, notas)
    if chat_id is not None:
        ws.update_cell(row_num, 4, chat_id)


def get_cita_by_id(cita_id: str) -> Optional[dict]:
    ws = get_citas_sheet()
    row_num = _find_row(ws, 1, cita_id)
    if row_num is None:
        return None
    return _row_to_dict(ws.row_values(row_num))


def get_cita_pendiente_por_chat_id(chat_id: str) -> Optional[dict]:
    ws = get_citas_sheet()
    rows = ws.get_all_values()[1:]
    for row in reversed(rows):
        if len(row) >= 7 and str(row[3]) == str(chat_id) and row[6] == "pendiente":
            return _row_to_dict(row)
    return None


def get_citas_hoy() -> list:
    ws = get_citas_sheet()
    today = datetime.now().strftime("%d/%m/%Y")
    return [_row_to_dict(r) for r in ws.get_all_values()[1:]
            if len(r) >= 5 and r[4] == today]


def _row_to_dict(row: list) -> dict:
    padded = row + [""] * (len(CITAS_HEADERS) - len(row))
    return dict(zip(CITAS_HEADERS, padded))
