"""
Persistencia del historial de cierres de caja conciliados.

Guarda el JSON completo del análisis en una pestaña del mismo Google Sheet
(`cierres_historicos`). El PDF físico no se guarda — se reconstruye on-demand
desde el JSON cuando el Lic quiera descargarlo de vuelta.

Esquema de la pestaña `cierres_historicos`:
  - id              (string, autogenerado: YYYYMMDD-HHMMSS-uuid4 corto)
  - report_date     (YYYY-MM-DD, fecha del cierre conciliado)
  - created_at      (ISO timestamp Guatemala, cuándo se procesó)
  - created_by      (email del usuario que lo procesó)
  - overall_status  (ok / warning / error)
  - total_ventas    (número, snapshot del total)
  - num_pdfs        (entero)
  - num_neonet      (entero)
  - num_boletas     (entero)
  - summary         (string corto, el overall_summary)
  - json_data       (string JSON completo del análisis)
"""

from __future__ import annotations

import datetime as dt
import json
import uuid
from zoneinfo import ZoneInfo

import streamlit as st

from . import sheets


GT_TZ = ZoneInfo("America/Guatemala")

HISTORY_TAB = "cierres_historicos"
HISTORY_HEADERS = [
    "id", "report_date", "created_at", "created_by",
    "overall_status", "total_ventas",
    "num_pdfs", "num_neonet", "num_boletas",
    "summary", "json_data",
]


# ---------------------------------------------------------------------------
# Tab management
# ---------------------------------------------------------------------------

def _ensure_history_tab():
    """Make sure the cierres_historicos tab exists with proper headers."""
    ss = sheets.get_spreadsheet()
    titles = {ws.title for ws in ss.worksheets()}
    if HISTORY_TAB not in titles:
        ss.add_worksheet(title=HISTORY_TAB, rows=500, cols=len(HISTORY_HEADERS))
    ws = ss.worksheet(HISTORY_TAB)
    first_row = ws.row_values(1)
    if [h.strip().lower() for h in first_row] != [h.lower() for h in HISTORY_HEADERS]:
        ws.update("A1", [HISTORY_HEADERS])
    return ws


def save_report(report: dict, user_email: str, n_pdfs: int, n_neonet: int, n_boletas: int) -> str:
    """
    Persist a completed analysis report. Returns the generated id.
    """
    ws = _ensure_history_tab()

    now = dt.datetime.now(GT_TZ)
    rid = f"{now.strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:6]}"

    report_date = report.get("report_date") or now.date().isoformat()
    total_ventas = (report.get("totals_from_pdfs") or {}).get("total_ventas", 0) or 0
    overall_status = report.get("overall_status", "ok")
    summary = (report.get("overall_summary", "") or "")[:500]

    # Compact JSON to save space in the cell
    json_str = json.dumps(report, ensure_ascii=False, separators=(",", ":"))

    row = [
        rid,
        report_date,
        now.isoformat(timespec="seconds"),
        user_email,
        overall_status,
        float(total_ventas),
        int(n_pdfs),
        int(n_neonet),
        int(n_boletas),
        summary,
        json_str,
    ]
    ws.append_row(row, value_input_option="USER_ENTERED")

    # Invalidate cache so next read sees the new row
    list_history.clear()
    return rid


# ---------------------------------------------------------------------------
# Read history
# ---------------------------------------------------------------------------

@st.cache_data(ttl=60, show_spinner=False)
def list_history() -> list[dict]:
    """Return all rows from the history tab as a list of dicts."""
    try:
        _ensure_history_tab()
        ws = sheets.get_spreadsheet().worksheet(HISTORY_TAB)
        rows = ws.get_all_records()
    except Exception:
        return []

    out = []
    for r in rows:
        if not r.get("id"):
            continue
        # Parse JSON if present
        json_data = None
        try:
            raw = r.get("json_data")
            if raw:
                json_data = json.loads(raw)
        except Exception:
            json_data = None
        try:
            tv = float(r.get("total_ventas") or 0)
        except (ValueError, TypeError):
            tv = 0.0
        out.append({
            "id": str(r.get("id", "")),
            "report_date": str(r.get("report_date", "")),
            "created_at": str(r.get("created_at", "")),
            "created_by": str(r.get("created_by", "")),
            "overall_status": str(r.get("overall_status", "ok")),
            "total_ventas": tv,
            "num_pdfs": int(r.get("num_pdfs") or 0),
            "num_neonet": int(r.get("num_neonet") or 0),
            "num_boletas": int(r.get("num_boletas") or 0),
            "summary": str(r.get("summary", "")),
            "json_data": json_data,
        })
    # Newest first
    out.sort(key=lambda x: x["created_at"], reverse=True)
    return out


def get_report_by_id(report_id: str) -> dict | None:
    """Fetch a single history row by id."""
    for item in list_history():
        if item["id"] == report_id:
            return item
    return None


def delete_history_entry(report_id: str) -> bool:
    """Delete a history row by id. Returns True if deleted."""
    ws = _ensure_history_tab()
    all_values = ws.get_all_values()
    for i, row in enumerate(all_values[1:], start=2):
        if row and row[0].strip() == report_id:
            ws.delete_rows(i)
            list_history.clear()
            return True
    return False
