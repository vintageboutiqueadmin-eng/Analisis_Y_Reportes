"""
Persistencia del historial de cierres + bandeja de pendientes.

Pestañas usadas en Google Sheets:
  - cierres_historicos  → cada análisis completo
  - cierres_pendientes  → boletas huérfanas y depósitos sin boleta (bandeja)
"""

from __future__ import annotations

import datetime as dt
import json
import re
import unicodedata
import uuid
from zoneinfo import ZoneInfo

import streamlit as st

from . import sheets


GT_TZ = ZoneInfo("America/Guatemala")

# ---------------------------------------------------------------------------
# Tabs schemas
# ---------------------------------------------------------------------------

HISTORY_TAB = "cierres_historicos"
HISTORY_HEADERS = [
    "id", "report_date", "created_at", "created_by",
    "overall_status", "total_ventas",
    "num_pdfs", "num_neonet", "num_boletas",
    "summary", "json_data",
]

PENDING_TAB = "cierres_pendientes"
PENDING_HEADERS = [
    "id",                # autogen
    "type",              # "boleta_huerfana" | "deposito_sin_boleta"
    "amount",            # float
    "origin_report_id",  # id del cierre donde quedó pendiente
    "origin_date",       # report_date del cierre origen
    "created_at",
    "status",            # "open" | "resolved"
    "resolved_in_report_id",  # id del cierre que lo cuadró (si aplica)
    "resolved_at",
    "details_json",      # extras: slip_number, pos_ref, cashier, store, etc.
]


# ---------------------------------------------------------------------------
# Tab management
# ---------------------------------------------------------------------------

def _ensure_history_tab():
    ss = sheets.get_spreadsheet()
    titles = {ws.title for ws in ss.worksheets()}
    if HISTORY_TAB not in titles:
        ss.add_worksheet(title=HISTORY_TAB, rows=500, cols=len(HISTORY_HEADERS))
    ws = ss.worksheet(HISTORY_TAB)
    first_row = ws.row_values(1)
    if [h.strip().lower() for h in first_row] != [h.lower() for h in HISTORY_HEADERS]:
        ws.update("A1", [HISTORY_HEADERS])
    return ws


def _ensure_pending_tab():
    ss = sheets.get_spreadsheet()
    titles = {ws.title for ws in ss.worksheets()}
    if PENDING_TAB not in titles:
        ss.add_worksheet(title=PENDING_TAB, rows=500, cols=len(PENDING_HEADERS))
    ws = ss.worksheet(PENDING_TAB)
    first_row = ws.row_values(1)
    if [h.strip().lower() for h in first_row] != [h.lower() for h in PENDING_HEADERS]:
        ws.update("A1", [PENDING_HEADERS])
    return ws


# ===========================================================================
# HISTORY: list, save, update, delete
# ===========================================================================

def _safe_float(v) -> float:
    try:
        return float(v)
    except (ValueError, TypeError):
        return 0.0


def _safe_int(v) -> int:
    try:
        return int(float(v))
    except (ValueError, TypeError):
        return 0


@st.cache_data(ttl=30, show_spinner=False)
def list_history() -> list[dict]:
    """Return all rows from cierres_historicos as a list of dicts."""
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
        json_data = None
        try:
            raw = r.get("json_data")
            if raw:
                json_data = json.loads(raw)
        except Exception:
            json_data = None
        out.append({
            "id": str(r.get("id", "")),
            "report_date": str(r.get("report_date", "")),
            "created_at": str(r.get("created_at", "")),
            "created_by": str(r.get("created_by", "")),
            "overall_status": str(r.get("overall_status", "ok")),
            "total_ventas": _safe_float(r.get("total_ventas")),
            "num_pdfs": _safe_int(r.get("num_pdfs")),
            "num_neonet": _safe_int(r.get("num_neonet")),
            "num_boletas": _safe_int(r.get("num_boletas")),
            "summary": str(r.get("summary", "")),
            "json_data": json_data,
        })
    out.sort(key=lambda x: x["created_at"], reverse=True)
    return out


def save_report(report: dict, user_email: str, n_pdfs: int, n_neonet: int, n_boletas: int) -> str:
    """Persist a completed analysis. Returns the generated id."""
    ws = _ensure_history_tab()
    now = dt.datetime.now(GT_TZ)
    rid = f"{now.strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:6]}"

    report_date = report.get("report_date") or now.date().isoformat()
    total_ventas = (report.get("totals_from_pdfs") or {}).get("total_ventas", 0) or 0
    overall_status = report.get("overall_status", "ok")
    summary = (report.get("overall_summary", "") or "")[:500]
    json_str = json.dumps(report, ensure_ascii=False, separators=(",", ":"))

    row = [
        rid, report_date, now.isoformat(timespec="seconds"), user_email,
        overall_status, float(total_ventas),
        int(n_pdfs), int(n_neonet), int(n_boletas),
        summary, json_str,
    ]
    ws.append_row(row, value_input_option="USER_ENTERED")
    list_history.clear()
    return rid


def get_report_by_id(report_id: str) -> dict | None:
    for item in list_history():
        if item["id"] == report_id:
            return item
    return None


def update_report(report_id: str, updated_report: dict) -> bool:
    """
    Overwrite the json_data, summary, overall_status and total_ventas of an existing
    history row (used when a pending got resolved and the old report changed status).
    """
    ws = _ensure_history_tab()
    all_values = ws.get_all_values()
    headers = all_values[0] if all_values else HISTORY_HEADERS
    col_idx = {h: i for i, h in enumerate(headers)}

    for i, row in enumerate(all_values[1:], start=2):
        if row and row[0].strip() == report_id:
            new_status = updated_report.get("overall_status", row[col_idx.get("overall_status", 4)])
            new_total = (updated_report.get("totals_from_pdfs") or {}).get("total_ventas",
                          _safe_float(row[col_idx.get("total_ventas", 5)]))
            new_summary = (updated_report.get("overall_summary") or "")[:500]
            new_json = json.dumps(updated_report, ensure_ascii=False, separators=(",", ":"))

            ws.update_cell(i, col_idx["overall_status"] + 1, new_status)
            ws.update_cell(i, col_idx["total_ventas"] + 1, float(new_total))
            ws.update_cell(i, col_idx["summary"] + 1, new_summary)
            ws.update_cell(i, col_idx["json_data"] + 1, new_json)
            list_history.clear()
            return True
    return False


def delete_history_entry(report_id: str) -> bool:
    ws = _ensure_history_tab()
    all_values = ws.get_all_values()
    for i, row in enumerate(all_values[1:], start=2):
        if row and row[0].strip() == report_id:
            ws.delete_rows(i)
            list_history.clear()
            return True
    return False


# ===========================================================================
# CATALOG of processed document IDs (for duplicate detection)
# ===========================================================================

def build_processed_catalog() -> dict:
    """
    Walk through all history reports and extract every unique ID we've seen:
      - PDF: pos_ref
      - Bank slip: slip_number
      - NEONET/Credomatic ticket: processor + lote
    Returns: {
      "pos_refs": {pos_ref: report_id, ...},
      "bank_slips": {slip_number: report_id, ...},
      "tickets": {f"{processor}-{lote}": report_id, ...},
    }
    """
    pos_refs = {}
    bank_slips = {}
    tickets = {}

    for h in list_history():
        rid = h["id"]
        data = h.get("json_data") or {}

        # PDFs: from cashier_breakdown
        for c in (data.get("cashier_breakdown") or []):
            ref = (c.get("pos_ref") or "").strip()
            if ref and ref not in pos_refs:
                pos_refs[ref] = rid

        # Bank slips: from bank_reconciliation.matched + orphan_slips
        bank = data.get("bank_reconciliation") or {}
        for m in (bank.get("matched") or []):
            sn = (m.get("slip_number") or "").strip()
            if sn and sn not in bank_slips:
                bank_slips[sn] = rid
        for o in (bank.get("orphan_slips") or []):
            sn = (o.get("slip_number") or "").strip()
            if sn and sn not in bank_slips:
                bank_slips[sn] = rid

        # NEONET / Credomatic tickets: from card_reconciliation
        card = data.get("card_reconciliation") or {}
        for proc_key, proc_label in [("credomatic", "CREDOMATIC"), ("visanet_neonet", "NEONET")]:
            lote = (card.get(proc_key, {}).get("ticket_lote") or "").strip()
            if lote:
                key = f"{proc_label}-{lote}"
                if key not in tickets:
                    tickets[key] = rid

    return {
        "pos_refs": pos_refs,
        "bank_slips": bank_slips,
        "tickets": tickets,
    }


# ===========================================================================
# PENDING TRAY: boletas huérfanas + depósitos sin boleta
# ===========================================================================

@st.cache_data(ttl=30, show_spinner=False)
def list_pending(only_open: bool = True) -> list[dict]:
    """Return all rows from cierres_pendientes."""
    try:
        _ensure_pending_tab()
        ws = sheets.get_spreadsheet().worksheet(PENDING_TAB)
        rows = ws.get_all_records()
    except Exception:
        return []

    out = []
    for r in rows:
        if not r.get("id"):
            continue
        status = str(r.get("status", "open"))
        if only_open and status != "open":
            continue
        details = {}
        try:
            raw = r.get("details_json")
            if raw:
                details = json.loads(raw)
        except Exception:
            details = {}
        out.append({
            "id": str(r.get("id", "")),
            "type": str(r.get("type", "")),
            "amount": _safe_float(r.get("amount")),
            "origin_report_id": str(r.get("origin_report_id", "")),
            "origin_date": str(r.get("origin_date", "")),
            "created_at": str(r.get("created_at", "")),
            "status": status,
            "resolved_in_report_id": str(r.get("resolved_in_report_id", "")),
            "resolved_at": str(r.get("resolved_at", "")),
            "details": details,
        })
    out.sort(key=lambda x: x["created_at"], reverse=True)
    return out


def add_pending(pending_type: str, amount: float, origin_report_id: str,
                origin_date: str, details: dict) -> str:
    """Add a pending entry to the tray. Returns generated id."""
    ws = _ensure_pending_tab()
    now = dt.datetime.now(GT_TZ)
    pid = f"P-{now.strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:6]}"
    row = [
        pid, pending_type, float(amount), origin_report_id, origin_date,
        now.isoformat(timespec="seconds"), "open", "", "",
        json.dumps(details, ensure_ascii=False),
    ]
    ws.append_row(row, value_input_option="USER_ENTERED")
    list_pending.clear()
    return pid


# ===========================================================================
# NETTING DE DIFERENCIAS INTERNAS POR CAJERO-DÍA (varias cajas del mismo cajero)
# ===========================================================================
# Cuando Odoo abre VARIAS cajas para el MISMO cajero el MISMO día (p.ej. una caja
# se traba y se genera un cierre "(RESCATE DE POS/...)"), cada sesión reporta su
# propia diferencia interna (efectivo cobrado − depósito). Esas diferencias son el
# MISMO dinero físico repartido entre sesiones: el faltante de una sesión se
# compensa con el sobrante (depósito de más) de otra. La diferencia REAL del cajero
# ese día es el NETO de todas sus sesiones, no la suma de los faltantes positivos.
#
# Caso real (Sexta Ana Gabriela Alfaro, 29/05 — Odoo abrió 3 cajas):
#   POS/7570  ef 818  dep 800  → +18 (faltante)
#   POS/7573  ef  88  dep   0  → +88 (faltante)   (RESCATE de 7570)
#   POS/7574  ef   0  dep 106  → −106 (sobrante)
#   NETO = +18 +88 −106 = 0  →  la cajera NO debe reponer nada.
#
# La agrupación es por (cajero, tienda, FECHA del número POS). La fecha sale del
# pos_ref "POS/AAAA/MM/DD/NNNN" — NO del report_date — porque un mismo reporte puede
# contener cierres de varios días (p.ej. el cierre del 16/05 traía 15, 16 y 17). Así
# nunca se mezclan sesiones de días distintos.
# ===========================================================================

def _norm_cashier(name) -> str:
    """Normaliza nombre de cajero para agrupar: minúsculas, sin acentos, sin espacios extra."""
    s = str(name or "").strip().lower()
    s = unicodedata.normalize("NFKD", s)
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    return " ".join(s.split())


def _pos_date(pos_ref, fallback: str = "") -> str:
    """Extrae AAAA-MM-DD del número POS ('POS/2026/05/29/7570'). Usa fallback si no hay."""
    m = re.search(r"POS/(\d{4})/(\d{2})/(\d{2})/", str(pos_ref or ""))
    if m:
        return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
    return str(fallback or "")[:10]


def _rescate_parent(pos_ref) -> str:
    """Si el pos_ref es un cierre RESCATE, devuelve el pos_ref padre; si no, ''."""
    m = re.search(r"RESCATE DE\s+([^)]+)", str(pos_ref or ""), flags=re.IGNORECASE)
    return m.group(1).strip() if m else ""


def _group_cashier_day_sessions(breakdown: list, report_date_fallback: str = "") -> list:
    """
    Agrupa las entradas de cashier_breakdown por (cajero normalizado, tienda, fecha
    del POS). Devuelve una lista de grupos; cada grupo trae sus sesiones, el conteo,
    el NETO (Σ efectivo − Σ depósito) y los pos_refs.
    """
    groups: dict = {}
    order: list = []
    for c in (breakdown or []):
        key = (
            _norm_cashier(c.get("cashier")),
            str(c.get("store") or "").strip(),
            _pos_date(c.get("pos_ref"), report_date_fallback),
        )
        if key not in groups:
            groups[key] = {"cashier": c.get("cashier") or "",
                           "store": c.get("store") or "",
                           "date": key[2],
                           "sessions": []}
            order.append(key)
        ef = _safe_float(c.get("efectivo"))
        dep = _safe_float(c.get("deposito"))
        field_diff = _safe_float(c.get("diferencia_interna"))
        # 'signed' = diferencia firmada de la sesión. Usa efectivo−depósito cuando hay
        # montos; si la sesión no trae montos, cae al campo diferencia_interna.
        signed = round(ef - dep, 2) if (ef or dep) else round(field_diff, 2)
        groups[key]["sessions"].append({
            "pos_ref": c.get("pos_ref") or "",
            "efectivo": ef, "deposito": dep,
            "field_diff": field_diff, "signed": signed,
            "rescate_parent": _rescate_parent(c.get("pos_ref")),
            "notes": c.get("notes") or "",
        })

    out = []
    for key in order:
        g = groups[key]
        sess = g["sessions"]
        out.append({
            "cashier": g["cashier"], "store": g["store"], "date": g["date"],
            "sessions": sess, "n": len(sess),
            "net": round(sum(s["signed"] for s in sess), 2),
            "pos_refs": [s["pos_ref"] for s in sess],
        })
    return out


def _net_faltantes_for_breakdown(breakdown: list, tolerance: float = 1.0,
                                 report_date_fallback: str = "",
                                 single_use_computed: bool = False) -> list:
    """
    Faltantes REALES que deben existir como pendientes 'diferencia_interna_cierre'
    para un reporte, ya netados por cajero-día.

    - Cajero con 1 sesión ese día → comportamiento histórico (faltante por sesión).
      Si single_use_computed=True también calcula efectivo−depósito (como el backfill).
    - Cajero con VARIAS sesiones el mismo día → se neta Σ(efectivo−depósito). Solo si
      el NETO > tolerancia se genera UN faltante (por el neto), atribuido a la sesión
      con mayor faltante. Si el neto ≤ tolerancia (cuadra o queda sobrante), NINGUNO.
    """
    result = []
    for g in _group_cashier_day_sessions(breakdown, report_date_fallback):
        sess = g["sessions"]
        if g["n"] <= 1:
            s = sess[0]
            diff = s["field_diff"]
            if single_use_computed and diff <= 0 and s["efectivo"] > 0 and s["deposito"] > 0:
                if (s["efectivo"] - s["deposito"]) > 0.01:
                    diff = round(s["efectivo"] - s["deposito"], 2)
            if diff > 0:
                result.append({
                    "amount": round(diff, 2), "pos_ref": s["pos_ref"],
                    "cashier": g["cashier"], "store": g["store"],
                    "note": s["notes"], "multi": False,
                    "group_pos_refs": [s["pos_ref"]],
                })
            continue
        # Multi-sesión el mismo día → netar
        net = g["net"]
        if net <= tolerance:
            continue  # cuadra neto o queda sobrante → no es faltante a reponer
        rep = max(sess, key=lambda x: x["signed"])
        desc = ", ".join(
            f"{s['pos_ref']} ({'+' if s['signed'] >= 0 else ''}{s['signed']:.2f})"
            for s in sess
        )
        result.append({
            "amount": round(net, 2), "pos_ref": rep["pos_ref"],
            "cashier": g["cashier"], "store": g["store"],
            "note": (f"Faltante NETO de {g['n']} cierres del mismo cajero el "
                     f"{g['date']} (Odoo abrió varias cajas): {desc}. "
                     f"Neto a reponer Q {net:.2f}."),
            "multi": True, "group_pos_refs": list(g["pos_refs"]),
        })
    return result


def add_pending_from_report(report: dict, report_id: str) -> dict:
    """
    Given a completed analysis report, push missing_slips, orphan_slips, and
    internal cashier differences to the pending tray.
    Returns {added: N, missing: N, orphans: N, internal_diffs: N}.
    """
    bank = report.get("bank_reconciliation") or {}
    report_date = report.get("report_date") or ""
    added = 0
    internal_diffs_count = 0

    # missing_slips → deposito_sin_boleta
    for m in (bank.get("missing_slips") or []):
        amt = _safe_float(m.get("amount"))
        if amt <= 0:
            continue
        add_pending(
            pending_type="deposito_sin_boleta",
            amount=amt,
            origin_report_id=report_id,
            origin_date=report_date,
            details={
                "pos_ref": m.get("pos_ref", ""),
                "cashier": m.get("cashier", ""),
            },
        )
        added += 1

    # orphan_slips → boleta_huerfana
    for o in (bank.get("orphan_slips") or []):
        amt = _safe_float(o.get("amount"))
        if amt <= 0:
            continue
        add_pending(
            pending_type="boleta_huerfana",
            amount=amt,
            origin_report_id=report_id,
            origin_date=report_date,
            details={
                "slip_number": o.get("slip_number", ""),
                "date": o.get("date", ""),
            },
        )
        added += 1

    # cashier_breakdown → diferencia_interna_cierre, NETADO por cajero-día.
    # Varias cajas del mismo cajero el mismo día se compensan entre sí; solo el neto
    # (Σ efectivo − Σ depósito) es un faltante real. Ver _net_faltantes_for_breakdown.
    for f in _net_faltantes_for_breakdown(
        report.get("cashier_breakdown") or [],
        report_date_fallback=report_date,
    ):
        details = {
            "pos_ref": f["pos_ref"],
            "cashier": f["cashier"],
            "store": f["store"],
            "note": f["note"],
        }
        if f.get("multi"):
            details["grupo_pos_refs"] = f["group_pos_refs"]
        add_pending(
            pending_type="diferencia_interna_cierre",
            amount=f["amount"],
            origin_report_id=report_id,
            origin_date=report_date,
            details=details,
        )
        added += 1
        internal_diffs_count += 1

    return {
        "added": added,
        "missing": len(bank.get("missing_slips") or []),
        "orphans": len(bank.get("orphan_slips") or []),
        "internal_diffs": internal_diffs_count,
    }


def mark_pending_resolved(pending_id: str, resolved_in_report_id: str) -> bool:
    """Mark a pending entry as resolved. Returns True if updated."""
    ws = _ensure_pending_tab()
    all_values = ws.get_all_values()
    if not all_values:
        return False
    headers = all_values[0]
    col_idx = {h: i for i, h in enumerate(headers)}

    for i, row in enumerate(all_values[1:], start=2):
        if row and row[0].strip() == pending_id:
            now_iso = dt.datetime.now(GT_TZ).isoformat(timespec="seconds")
            ws.update_cell(i, col_idx["status"] + 1, "resolved")
            ws.update_cell(i, col_idx["resolved_in_report_id"] + 1, resolved_in_report_id)
            ws.update_cell(i, col_idx["resolved_at"] + 1, now_iso)
            list_pending.clear()
            return True
    return False


def delete_pending(pending_id: str) -> bool:
    ws = _ensure_pending_tab()
    all_values = ws.get_all_values()
    for i, row in enumerate(all_values[1:], start=2):
        if row and row[0].strip() == pending_id:
            ws.delete_rows(i)
            list_pending.clear()
            return True
    return False


# ===========================================================================
# When a pending gets resolved, the OLD source report's status may improve
# ===========================================================================

def apply_resolutions_to_origin_reports(resolved_items: list[dict]) -> int:
    """
    For each resolved pending, check if its origin report can now be marked
    as 'ok' (because its remaining open pendings are gone).

    `resolved_items` is the list from report["resolved_pending"]:
        [{pending_id, original_report_id, ...}, ...]

    Returns count of origin reports updated.
    """
    if not resolved_items:
        return 0

    # Group by origin_report_id
    by_origin = {}
    for r in resolved_items:
        oid = r.get("original_report_id") or r.get("pending_id", "").split("-from-")[-1]
        if not oid:
            continue
        by_origin.setdefault(oid, []).append(r)

    updated_count = 0
    for origin_id, items in by_origin.items():
        origin = get_report_by_id(origin_id)
        if not origin or not origin.get("json_data"):
            continue

        report = origin["json_data"]
        bank = report.get("bank_reconciliation") or {}

        # Remove matched items from missing_slips and orphan_slips
        matched_pos_refs = set()
        matched_slip_numbers = set()
        matched_internal_diffs = set()  # pos_refs whose internal diff was resolved
        for r in items:
            ptype = r.get("pending_type", "")
            pending_id = r.get("pending_id", "")
            full = list_pending(only_open=False)
            pending_row = next((p for p in full if p["id"] == pending_id), None)
            if not pending_row:
                continue
            details = pending_row.get("details", {}) or {}
            if ptype == "deposito_sin_boleta":
                matched_pos_refs.add(details.get("pos_ref", ""))
            elif ptype == "boleta_huerfana":
                matched_slip_numbers.add(details.get("slip_number", ""))
            elif ptype == "diferencia_interna_cierre":
                matched_internal_diffs.add(details.get("pos_ref", ""))

        new_missing = [
            m for m in (bank.get("missing_slips") or [])
            if (m.get("pos_ref") or "") not in matched_pos_refs
        ]
        new_orphans = [
            o for o in (bank.get("orphan_slips") or [])
            if (o.get("slip_number") or "") not in matched_slip_numbers
        ]
        bank["missing_slips"] = new_missing
        bank["orphan_slips"] = new_orphans
        report["bank_reconciliation"] = bank

        # Zero-out diferencia_interna for the resolved cashier entries
        if matched_internal_diffs:
            for c in (report.get("cashier_breakdown") or []):
                if (c.get("pos_ref") or "") in matched_internal_diffs:
                    c["diferencia_interna"] = 0
                    note = c.get("notes", "")
                    add = "[Diferencia interna resuelta posteriormente]"
                    c["notes"] = f"{note} {add}".strip() if note else add

        # Append a finding noting the resolution
        findings = report.get("findings") or []
        bits = []
        if matched_pos_refs:
            bits.append(f"{len(matched_pos_refs)} depósito(s) sin boleta")
        if matched_slip_numbers:
            bits.append(f"{len(matched_slip_numbers)} boleta(s) huérfana(s)")
        if matched_internal_diffs:
            bits.append(f"{len(matched_internal_diffs)} diferencia(s) interna(s)")
        findings.append({
            "severity": "ok",
            "title": "Pendientes resueltos posteriormente",
            "detail": f"Algunos pendientes de este cierre fueron cuadrados después: "
                      f"{', '.join(bits) if bits else 'pendientes'}.",
        })
        report["findings"] = findings

        # Possibly improve overall_status if it was only "warning" because of these
        if report.get("overall_status") == "warning":
            still_has_issues = (
                new_missing or new_orphans or
                any(_safe_float(c.get("diferencia_interna")) > 0
                    for c in (report.get("cashier_breakdown") or []))
            )
            if not still_has_issues:
                has_other_warnings = any(
                    f.get("severity") in ("warn", "alert")
                    for f in findings
                    if f.get("title") != "Pendientes resueltos posteriormente"
                )
                if not has_other_warnings:
                    report["overall_status"] = "ok"

        if update_report(origin_id, report):
            updated_count += 1

    return updated_count


# ===========================================================================
# INLINE RESOLUTION from Pending tray (subir boleta/PDF para resolver)
# ===========================================================================

def find_pending_combinations(target_amount: float, pendings: list[dict],
                               tolerance: float = 1.0, max_size: int = 3) -> list[list[dict]]:
    """
    Find combinations of pending entries (size 1 to max_size) whose sum matches
    target_amount within tolerance.
    Returns list of combinations, each combination being a list of pending dicts.
    Sorted by combination size (smaller first), then by closeness to target.
    """
    from itertools import combinations

    results = []
    for size in range(1, max_size + 1):
        for combo in combinations(pendings, size):
            total = sum(p["amount"] for p in combo)
            if abs(total - target_amount) <= tolerance:
                results.append({
                    "combo": list(combo),
                    "total": total,
                    "size": size,
                    "delta": abs(total - target_amount),
                })

    # Sort: prefer smaller combinations, then exactness
    results.sort(key=lambda x: (x["size"], x["delta"]))
    return [r["combo"] for r in results]


def backfill_internal_diffs_from_history() -> dict:
    """
    Scan ALL historical reports and ensure every cashier with a real internal
    diff has a corresponding pending row in cierres_pendientes.

    Internal diffs are NETTED per cashier-day: when one cashier had several POS
    sessions the same day (Odoo opened several boxes / RESCATE close), the faltantes
    of some sessions cancel out against the sobrante of another. Only the NET is a
    real faltante. Single-session days keep the historic behaviour (field value, or
    computed efectivo − deposito for old reports). See _net_faltantes_for_breakdown.

    Skips ones that already exist (matched by origin_report_id + pos_ref + amount).

    Returns {scanned: N, added: M}.
    """
    scanned = 0
    added = 0

    # Build a set of "signatures" of existing pending diferencia_interna entries
    existing = set()
    for p in list_pending(only_open=False):
        if p["type"] != "diferencia_interna_cierre":
            continue
        details = p.get("details", {}) or {}
        sig = (
            p["origin_report_id"],
            details.get("pos_ref", ""),
            round(p["amount"], 2),
        )
        existing.add(sig)

    for h in list_history():
        rid = h["id"]
        data = h.get("json_data") or {}
        report_date = str(h.get("report_date") or "")
        scanned += len(data.get("cashier_breakdown") or [])
        for f in _net_faltantes_for_breakdown(
            data.get("cashier_breakdown") or [],
            report_date_fallback=report_date,
            single_use_computed=True,
        ):
            sig = (rid, f["pos_ref"], round(f["amount"], 2))
            if sig in existing:
                continue
            details = {
                "pos_ref": f["pos_ref"],
                "cashier": f["cashier"],
                "store": f["store"],
                "note": (f["note"] + " [detectado por backfill]").strip(),
            }
            if f.get("multi"):
                details["grupo_pos_refs"] = f["group_pos_refs"]
            add_pending(
                pending_type="diferencia_interna_cierre",
                amount=f["amount"],
                origin_report_id=rid,
                origin_date=report_date,
                details=details,
            )
            existing.add(sig)
            added += 1

    return {"scanned": scanned, "added": added}


def repair_multisession_internal_diffs(user_email: str, tolerance: float = 1.0) -> dict:
    """
    Repara reportes donde un MISMO cajero tuvo VARIOS cierres el MISMO día (Odoo
    abrió varias cajas / cierre RESCATE) y el sistema dejó faltantes por sesión sin
    netar contra el sobrante (depósito de más) de otra sesión.

    Para cada grupo (cajero, tienda, fecha del POS) con ≥2 sesiones:
      - Calcula el NETO (Σ efectivo − Σ depósito).
      - Cierra los pendientes 'diferencia_interna_cierre' ABIERTOS de ese grupo que no
        correspondan al neto (faltantes por sesión espurios).
      - Si el neto > tolerancia, deja UN solo pendiente por el neto; si el neto ≤
        tolerancia (cuadra o queda sobrante), no deja ninguno.
      - En el reporte pone en 0 las diferencias por sesión del grupo (y el neto en la
        sesión con mayor faltante, si aplica) y agrega un finding de auditoría.

    Es idempotente: corrida dos veces no vuelve a tocar nada. Devuelve un resumen.
    """
    resolver = f"netting-multisesion-{user_email}"
    open_pendings = list_pending(only_open=True)
    scanned_reports = 0
    groups_fixed = 0
    pendings_closed = 0
    residuals_created = 0
    details_out = []

    for h in list_history():
        rid = h["id"]
        report_date = str(h.get("report_date") or "")
        # Copia desacoplada del caché antes de mutar
        data = json.loads(json.dumps(h.get("json_data") or {}))
        breakdown = data.get("cashier_breakdown") or []
        scanned_reports += 1
        report_changed = False

        for g in _group_cashier_day_sessions(breakdown, report_date_fallback=report_date):
            if g["n"] < 2:
                continue
            net = g["net"]
            pos_set = set(g["pos_refs"])

            grp_pendings = [
                p for p in open_pendings
                if p["type"] == "diferencia_interna_cierre"
                and p.get("origin_report_id") == rid
                and ((p.get("details", {}) or {}).get("pos_ref", "") in pos_set)
            ]

            should_amt = round(net, 2) if net > tolerance else 0.0
            current_sum = round(sum(_safe_float(p["amount"]) for p in grp_pendings), 2)

            # ¿Ya está correcto? (ninguno si neto≤tol, o uno solo == neto)
            already_ok = (
                (should_amt == 0.0 and not grp_pendings)
                or (should_amt > 0 and len(grp_pendings) == 1
                    and abs(current_sum - should_amt) <= 0.01)
            )
            if already_ok:
                continue

            # ---- Reparar este grupo ----
            for p in grp_pendings:
                if mark_pending_resolved(p["id"], resolver):
                    pendings_closed += 1
            closed_ids = {p["id"] for p in grp_pendings}
            open_pendings = [p for p in open_pendings if p["id"] not in closed_ids]

            rep_sess = max(g["sessions"], key=lambda x: x["signed"])
            rep_pos = rep_sess["pos_ref"] if should_amt > 0 else ""

            if should_amt > 0:
                add_pending(
                    pending_type="diferencia_interna_cierre",
                    amount=should_amt,
                    origin_report_id=rid,
                    origin_date=report_date,
                    details={
                        "pos_ref": rep_pos,
                        "cashier": g["cashier"],
                        "store": g["store"],
                        "note": (f"Faltante NETO de {g['n']} cierres del mismo cajero "
                                 f"el {g['date']}. Neto a reponer Q {should_amt:.2f}."),
                        "grupo_pos_refs": list(g["pos_refs"]),
                    },
                )
                residuals_created += 1

            # Ajustar el breakdown del reporte
            for c in breakdown:
                if (c.get("pos_ref") or "") in pos_set:
                    c["diferencia_interna"] = should_amt if (
                        should_amt > 0 and (c.get("pos_ref") or "") == rep_pos) else 0
                    prev = c.get("notes", "")
                    tag = "[Netado por multi-sesión del cajero el mismo día]"
                    if tag not in prev:
                        c["notes"] = (prev + " " + tag).strip() if prev else tag

            desc = ", ".join(
                f"{s['pos_ref']} ({'+' if s['signed'] >= 0 else ''}{s['signed']:.2f})"
                for s in g["sessions"]
            )
            rescate_links = [
                f"{s['pos_ref']} es RESCATE de {s['rescate_parent']}"
                for s in g["sessions"] if s.get("rescate_parent")
            ]
            if should_amt > 0:
                txt = (f"{g['cashier']} ({g['store']}) tuvo {g['n']} cierres el "
                       f"{g['date']} ({desc}). Netados, queda un faltante real de "
                       f"Q {should_amt:.2f}; se cerraron los faltantes por sesión. ")
            else:
                txt = (f"{g['cashier']} ({g['store']}) tuvo {g['n']} cierres el "
                       f"{g['date']} ({desc}). El neto cuadra (Q {net:.2f}): los "
                       f"faltantes de unas sesiones se compensan con el sobrante de "
                       f"otra. No hay nada que reponer; se cerraron los faltantes "
                       f"por sesión. ")
            if rescate_links:
                txt += " ".join(rescate_links) + ". "
            txt += f"Conciliado por {user_email}."
            findings = data.get("findings") or []
            findings.append({
                "severity": "ok",
                "title": "Cierres multi-sesión netados",
                "detail": txt,
            })
            data["findings"] = findings
            _reposicion_maybe_upgrade_status(data)

            report_changed = True
            groups_fixed += 1
            details_out.append({
                "report_id": rid,
                "cashier": g["cashier"],
                "store": g["store"],
                "date": g["date"],
                "pos_refs": list(g["pos_refs"]),
                "net": net,
                "closed": len(grp_pendings),
                "residual": should_amt,
            })

        if report_changed:
            update_report(rid, data)

    list_pending.clear()
    list_history.clear()
    return {
        "scanned_reports": scanned_reports,
        "groups_fixed": groups_fixed,
        "pendings_closed": pendings_closed,
        "residuals_created": residuals_created,
        "details": details_out,
    }


def repair_suspicious_matches_in_history(tolerance: float = 1.0) -> dict:
    """
    Scan all historical reports' bank_reconciliation.matched entries and detect:
      A) Matches where |pos_amount - slip_amount| > tolerance (impossible under
         the matching rules — indicates Claude hallucinated the pair)
      B) The same slip_number used for multiple matched entries (violates
         "one slip = one use" rule)

    For each suspicious match:
      - Move the POS deposit to missing_slips
      - Add a pending entry of type deposito_sin_boleta
      - Mark the report's overall_status as warning if it was ok
      - Tag a finding noting the auto-repair

    ALSO detects fake orphan_slips: if an orphan_slip's amount matches the
    amount of a moved (hallucinated) match, that orphan is very likely fake
    (Claude invented it to "balance" the books). It gets removed from both
    the report and the pending tray.

    Returns dict with stats.
    """
    reports_repaired = 0
    matches_moved = 0
    fake_orphans_removed = 0
    suspicious_slips_seen = []  # informational

    for h in list_history():
        rid = h["id"]
        data = h.get("json_data") or {}
        bank = data.get("bank_reconciliation") or {}
        matched = list(bank.get("matched") or [])
        missing = list(bank.get("missing_slips") or [])
        orphans = list(bank.get("orphan_slips") or [])
        if not matched:
            continue

        # Build cashier lookup from cashier_breakdown for enriching missing_slips
        cbd = {
            (c.get("pos_ref") or ""): c
            for c in (data.get("cashier_breakdown") or [])
        }

        # Detect duplicate slip usage
        slip_count = {}
        for m in matched:
            sn = (m.get("slip_number") or "").strip()
            if sn:
                slip_count[sn] = slip_count.get(sn, 0) + 1

        new_matched = []
        local_moves = []
        seen_slips = set()
        for m in matched:
            pos_amt = _safe_float(m.get("pos_amount"))
            slip_amt = _safe_float(m.get("slip_amount"))
            sn = (m.get("slip_number") or "").strip()

            is_high_diff = abs(pos_amt - slip_amt) > tolerance
            is_duplicate = slip_count.get(sn, 0) > 1 and sn in seen_slips
            seen_slips.add(sn)

            if is_high_diff or is_duplicate:
                reason = (
                    "diferencia de monto > tolerancia"
                    if is_high_diff else "boleta repetida en matched"
                )
                pos_ref = m.get("pos_ref", "")
                cashier = (cbd.get(pos_ref, {}) or {}).get("cashier", "")
                local_moves.append({
                    "pos_ref": pos_ref,
                    "amount": pos_amt,
                    "cashier": cashier,
                    "reason": reason,
                    "suspicious_slip": sn,
                })
                suspicious_slips_seen.append({
                    "slip_number": sn,
                    "report_id": rid,
                    "reason": reason,
                })
            else:
                new_matched.append(m)

        if not local_moves:
            continue

        # NEW: detect FAKE orphan_slips. If an orphan_slip's amount matches a
        # moved (hallucinated) match's pos_amount, it's almost certainly fake.
        # Claude often invents an orphan to "balance" a wrong match.
        moved_amounts = [round(m["amount"], 2) for m in local_moves]
        new_orphans = []
        removed_orphans = []  # list of (slip_number, amount) tuples
        for o in orphans:
            o_amt = round(_safe_float(o.get("amount")), 2)
            o_sn = (o.get("slip_number") or "").strip()
            if o_amt in moved_amounts:
                removed_orphans.append((o_sn, o_amt))
                moved_amounts.remove(o_amt)  # consume one occurrence
            else:
                new_orphans.append(o)

        # Apply repairs to the report
        bank["matched"] = new_matched
        bank["missing_slips"] = missing + [
            {"pos_ref": x["pos_ref"], "amount": x["amount"], "cashier": x["cashier"]}
            for x in local_moves
        ]
        bank["orphan_slips"] = new_orphans
        data["bank_reconciliation"] = bank

        # Append finding
        findings = data.get("findings") or []
        finding_text = (
            f"Se detectaron {len(local_moves)} match(es) sospechoso(s) y "
            f"se reclasificaron como depósitos sin boleta. "
            f"Razones: {', '.join(sorted({x['reason'] for x in local_moves}))}. "
            f"Boletas usadas erróneamente: "
            f"{', '.join(sorted({x['suspicious_slip'] for x in local_moves}))}."
        )
        if removed_orphans:
            finding_text += (
                f" Se removieron también {len(removed_orphans)} boleta(s) "
                f"huérfana(s) probablemente ficticia(s) "
                f"(montos coincidían con matches inválidos): "
                f"{', '.join(sn for sn, _ in removed_orphans)}."
            )
        findings.append({
            "severity": "warn",
            "title": "Conciliación bancaria reparada automáticamente",
            "detail": finding_text,
        })
        data["findings"] = findings

        # Demote overall_status if previously ok
        if data.get("overall_status") == "ok":
            data["overall_status"] = "warning"

        # Save
        if update_report(rid, data):
            reports_repaired += 1

            # Delete pending entries for the removed fake orphan_slips
            # Snapshot the pending list first to avoid mid-iteration cache invalidation
            pending_snapshot = list(list_pending(only_open=True))
            for sn, _amt in removed_orphans:
                if not sn:
                    continue
                for p in pending_snapshot:
                    if p["type"] != "boleta_huerfana":
                        continue
                    if (p.get("details", {}) or {}).get("slip_number") == sn:
                        if delete_pending(p["id"]):
                            fake_orphans_removed += 1

            # Push new missing to pending tray (skip if already exists by signature)
            existing_pending_sigs = set()
            for p in list_pending(only_open=False):
                if p["type"] != "deposito_sin_boleta":
                    continue
                d = p.get("details", {}) or {}
                existing_pending_sigs.add(
                    (p["origin_report_id"], d.get("pos_ref", ""), round(p["amount"], 2))
                )
            for mv in local_moves:
                sig = (rid, mv["pos_ref"], round(mv["amount"], 2))
                if sig in existing_pending_sigs:
                    continue
                add_pending(
                    pending_type="deposito_sin_boleta",
                    amount=mv["amount"],
                    origin_report_id=rid,
                    origin_date=h.get("report_date", ""),
                    details={
                        "pos_ref": mv["pos_ref"],
                        "cashier": mv["cashier"],
                        "note": f"Movido a pendientes por reparación automática ({mv['reason']})",
                    },
                )
                matches_moved += 1

    return {
        "reports_repaired": reports_repaired,
        "matches_moved": matches_moved,
        "fake_orphans_removed": fake_orphans_removed,
        "suspicious_slips": suspicious_slips_seen,
    }


def autoresolve_cross_pending_pairs(
    user_email: str, tolerance: float = 1.0
) -> dict:
    """
    Scan the open pending tray and find pairs of (boleta_huerfana, deposito_sin_boleta)
    where amounts match within tolerance. For each pair, resolve BOTH pendings as
    a mutual auto-match, and update BOTH origin reports with a finding noting the
    retroactive reconciliation.

    Returns dict with stats.
    """
    open_pendings = list_pending(only_open=True)

    orphans = [p for p in open_pendings if p["type"] == "boleta_huerfana"]
    missing = [p for p in open_pendings if p["type"] == "deposito_sin_boleta"]

    if not orphans or not missing:
        return {
            "pairs_resolved": 0,
            "reports_updated": 0,
            "pair_details": [],
        }

    used_orphan_ids = set()
    used_missing_ids = set()
    pair_details = []

    # Greedy match: for each missing, find the best-matching orphan by amount.
    # Sort by exact match first (smaller diff wins).
    for miss in missing:
        miss_amt = float(miss.get("amount") or 0)
        best_orphan = None
        best_diff = tolerance + 0.001
        for orph in orphans:
            if orph["id"] in used_orphan_ids:
                continue
            orph_amt = float(orph.get("amount") or 0)
            diff = abs(miss_amt - orph_amt)
            if diff <= tolerance and diff < best_diff:
                best_orphan = orph
                best_diff = diff

        if best_orphan is None:
            continue

        # Build a resolver_label that lets us identify these as cross-pending
        resolver_label = f"cross-pending-pair-{user_email}"

        # Mark both as resolved
        ok1 = mark_pending_resolved(miss["id"], resolver_label)
        ok2 = mark_pending_resolved(best_orphan["id"], resolver_label)
        if not (ok1 and ok2):
            continue

        used_orphan_ids.add(best_orphan["id"])
        used_missing_ids.add(miss["id"])

        # Update both origin reports with a finding
        miss_details = miss.get("details", {}) or {}
        orph_details = best_orphan.get("details", {}) or {}

        miss_pos_ref = miss_details.get("pos_ref", "")
        orph_slip = orph_details.get("slip_number", "")

        miss_origin = miss.get("origin_report_id")
        orph_origin = best_orphan.get("origin_report_id")

        # Update the missing's origin (remove from missing_slips, add to matched)
        miss_report = get_report_by_id(miss_origin) if miss_origin else None
        if miss_report and miss_report.get("json_data"):
            data = miss_report["json_data"]
            bank = data.get("bank_reconciliation") or {}
            bank["missing_slips"] = [
                m for m in (bank.get("missing_slips") or [])
                if (m.get("pos_ref") or "") != miss_pos_ref
            ]
            new_matched = list(bank.get("matched") or [])
            new_matched.append({
                "pos_ref": miss_pos_ref,
                "pos_amount": miss_amt,
                "slip_number": orph_slip,
                "slip_amount": float(best_orphan.get("amount") or 0),
                "cashier": miss_details.get("cashier", ""),
                "rescued_retroactively": True,
            })
            bank["matched"] = new_matched
            data["bank_reconciliation"] = bank

            findings = data.get("findings") or []
            findings.append({
                "severity": "info",
                "title": "Match cuadrado retrospectivamente",
                "detail": (
                    f"El depósito {miss_pos_ref} de {miss_details.get('cashier','?')} "
                    f"(Q {miss_amt:.2f}) fue cuadrado retroactivamente con la boleta "
                    f"J No. {orph_slip} del reporte origen {orph_origin}. "
                    f"Reconciliación automatizada por {user_email}."
                ),
            })
            data["findings"] = findings

            # If this was the only issue, possibly upgrade status
            if data.get("overall_status") == "warning":
                bank_now = data.get("bank_reconciliation") or {}
                cashier_diffs = sum(
                    1 for c in (data.get("cashier_breakdown") or [])
                    if _safe_float(c.get("diferencia_interna")) > 0
                )
                if (not bank_now.get("missing_slips")
                    and not bank_now.get("orphan_slips")
                    and cashier_diffs == 0):
                    data["overall_status"] = "ok"

            update_report(miss_origin, data)

        # Update the orphan's origin (remove from orphan_slips, add to matched)
        # Skip if same report as miss (would double-update)
        if orph_origin and orph_origin != miss_origin:
            orph_report = get_report_by_id(orph_origin)
            if orph_report and orph_report.get("json_data"):
                data = orph_report["json_data"]
                bank = data.get("bank_reconciliation") or {}
                bank["orphan_slips"] = [
                    o for o in (bank.get("orphan_slips") or [])
                    if (o.get("slip_number") or "") != orph_slip
                ]
                new_matched = list(bank.get("matched") or [])
                new_matched.append({
                    "pos_ref": miss_pos_ref,
                    "pos_amount": miss_amt,
                    "slip_number": orph_slip,
                    "slip_amount": float(best_orphan.get("amount") or 0),
                    "cashier": miss_details.get("cashier", ""),
                    "rescued_retroactively": True,
                })
                bank["matched"] = new_matched
                data["bank_reconciliation"] = bank

                findings = data.get("findings") or []
                findings.append({
                    "severity": "info",
                    "title": "Match cuadrado retrospectivamente",
                    "detail": (
                        f"La boleta J No. {orph_slip} (Q {best_orphan['amount']:.2f}) "
                        f"fue cuadrada retroactivamente con el depósito {miss_pos_ref} "
                        f"de {miss_details.get('cashier','?')} del reporte origen {miss_origin}. "
                        f"Reconciliación automatizada por {user_email}."
                    ),
                })
                data["findings"] = findings

                if data.get("overall_status") == "warning":
                    bank_now = data.get("bank_reconciliation") or {}
                    cashier_diffs = sum(
                        1 for c in (data.get("cashier_breakdown") or [])
                        if _safe_float(c.get("diferencia_interna")) > 0
                    )
                    if (not bank_now.get("missing_slips")
                        and not bank_now.get("orphan_slips")
                        and cashier_diffs == 0):
                        data["overall_status"] = "ok"

                update_report(orph_origin, data)

        pair_details.append({
            "missing_pos_ref": miss_pos_ref,
            "missing_amount": miss_amt,
            "missing_cashier": miss_details.get("cashier", ""),
            "missing_origin": miss_origin,
            "orphan_slip": orph_slip,
            "orphan_amount": float(best_orphan.get("amount") or 0),
            "orphan_origin": orph_origin,
        })

    return {
        "pairs_resolved": len(pair_details),
        "reports_updated": len(set(
            [d["missing_origin"] for d in pair_details] +
            [d["orphan_origin"] for d in pair_details]
        )),
        "pair_details": pair_details,
    }


# ===========================================================================
# REPOSICIÓN: boleta huérfana  ↔  diferencia interna de cierre
# ---------------------------------------------------------------------------
# Caso común: un cajero queda corto en el cierre (efectivo cobrado > depósito,
# `diferencia_interna` > 0 → debe reponer) y al día siguiente deposita ese
# faltante por separado. Ese depósito genera una boleta de banco que no calza
# con ningún depósito de venta del POS → se marca huérfana. La boleta y el
# faltante son el MISMO dinero y deben saldarse entre sí.
#
# Una boleta de banco NO trae cajero; el único dato compartido es el MONTO. Por
# eso, para no cruzar dinero por error, el emparejado automático exige que el
# monto sea inequívoco (exactamente UNA huérfana y UNA diferencia interna de ese
# monto). Los montos con varios candidatos quedan para confirmación humana
# (link_reposicion / linker en la bandeja).
# ===========================================================================

def _parse_date_loose(s) -> dt.date | None:
    """Parse a date string in any of the formats used across the app."""
    if not s:
        return None
    s = str(s).strip()
    for c in (s, s[:10]):
        for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%Y/%m/%d", "%d/%m/%y"):
            try:
                return dt.datetime.strptime(c, fmt).date()
            except Exception:
                pass
    return None


def _reposicion_date_ok(slip_date_str: str, close_date_str: str) -> bool:
    """
    A reposición deposit cannot predate the close it repays. Returns True unless
    we can PROVE the slip is earlier than the close (lenient on unparseable dates).
    """
    sd = _parse_date_loose(slip_date_str)
    cd = _parse_date_loose(close_date_str)
    if sd is None or cd is None:
        return True
    return sd >= cd


def _reposicion_maybe_upgrade_status(data: dict) -> None:
    """Upgrade a report from 'warning' to 'ok' if no real issues remain."""
    if data.get("overall_status") != "warning":
        return
    bank = data.get("bank_reconciliation") or {}
    cashier_diffs = sum(
        1 for c in (data.get("cashier_breakdown") or [])
        if _safe_float(c.get("diferencia_interna")) > 0
    )
    other_warn = any(
        f.get("severity") in ("warn", "alert")
        for f in (data.get("findings") or [])
    )
    if (not bank.get("missing_slips") and not bank.get("orphan_slips")
            and cashier_diffs == 0 and not other_warn):
        data["overall_status"] = "ok"


def _apply_reposicion_link(orph: dict, diff: dict, user_email: str) -> dict | None:
    """
    Resolve one (boleta_huerfana ↔ diferencia_interna_cierre) pair as a reposición
    and update the origin report(s): zero the diferencia_interna on the difference's
    cierre, drop the orphan slip from the slip's cierre, and add a clear finding.
    Handles the case where both pendings share the same origin report (one save).
    Returns a detail dict, or None on failure.
    """
    resolver_label = f"reposicion-{user_email}"
    if not mark_pending_resolved(orph["id"], resolver_label):
        return None
    if not mark_pending_resolved(diff["id"], resolver_label):
        return None

    o_d = orph.get("details", {}) or {}
    d_d = diff.get("details", {}) or {}
    slip = o_d.get("slip_number", "")
    cashier = d_d.get("cashier", "?")
    diff_pos = d_d.get("pos_ref", "?")
    amt = _safe_float(diff.get("amount")) or _safe_float(orph.get("amount"))

    orph_origin = orph.get("origin_report_id")
    diff_origin = diff.get("origin_report_id")

    # Collect the mutations each origin report needs, then save each report ONCE
    # (the difference and the slip frequently come from the SAME upload).
    targets: dict[str, list[tuple[str, str]]] = {}
    if diff_origin:
        targets.setdefault(diff_origin, []).append(("diff", diff_pos))
    if orph_origin:
        targets.setdefault(orph_origin, []).append(("orph", slip))

    origins = set()
    for oid, muts in targets.items():
        rep = get_report_by_id(oid)
        if not rep or not rep.get("json_data"):
            continue
        data = rep["json_data"]
        for kind, key in muts:
            if kind == "diff":
                for c in (data.get("cashier_breakdown") or []):
                    if (c.get("pos_ref") or "") == key:
                        c["diferencia_interna"] = 0
                        prev = c.get("notes", "")
                        add = (
                            f"[Diferencia repuesta vía depósito bancario — "
                            f"boleta J No. {slip} (Q {amt:.2f})]"
                        )
                        c["notes"] = (prev + " " + add).strip() if prev else add
            else:  # orph
                bank = data.get("bank_reconciliation") or {}
                bank["orphan_slips"] = [
                    o for o in (bank.get("orphan_slips") or [])
                    if (o.get("slip_number") or "") != key
                ]
                data["bank_reconciliation"] = bank

        findings = data.get("findings") or []
        findings.append({
            "severity": "ok",
            "title": "Reposición conciliada",
            "detail": (
                f"El faltante de cierre de {cashier} ({diff_pos}, Q {amt:.2f}) fue "
                f"repuesto mediante el depósito bancario de la boleta J No. {slip}. "
                f"Ambos quedan saldados. Conciliado por {user_email}."
            ),
        })
        data["findings"] = findings
        _reposicion_maybe_upgrade_status(data)
        if update_report(oid, data):
            origins.add(oid)

    return {
        "orphan_id": orph["id"],
        "diff_id": diff["id"],
        "slip": slip,
        "cashier": cashier,
        "diff_pos": diff_pos,
        "amount": amt,
        "origins": origins,
    }


def autoresolve_reposicion_pairs(user_email: str, tolerance: float = 1.0) -> dict:
    """
    Scan the open pending tray and auto-link unambiguous reposiciones:
    a boleta_huerfana and a diferencia_interna_cierre of the SAME amount.

    SAFETY: a bank slip has no cashier, so amount is the only join key. An amount
    is linked automatically ONLY when it is unique on both sides (exactly one open
    orphan slip AND one open internal difference of that exact amount) and the slip
    date is not earlier than the close. Amounts with several candidates on either
    side are returned in `ambiguous` for manual confirmation in the tray and are
    left untouched.

    Returns: {pairs_resolved, reports_updated, pair_details, ambiguous}
    """
    open_pendings = list_pending(only_open=True)
    orphans = [p for p in open_pendings if p["type"] == "boleta_huerfana"]
    diffs = [p for p in open_pendings if p["type"] == "diferencia_interna_cierre"]

    if not orphans or not diffs:
        return {"pairs_resolved": 0, "reports_updated": 0,
                "pair_details": [], "ambiguous": []}

    from collections import defaultdict

    def _k(amt):
        return round(_safe_float(amt), 2)

    orph_by_amt: dict[float, list[dict]] = defaultdict(list)
    for o in orphans:
        orph_by_amt[_k(o["amount"])].append(o)
    diff_by_amt: dict[float, list[dict]] = defaultdict(list)
    for dpd in diffs:
        diff_by_amt[_k(dpd["amount"])].append(dpd)

    pair_details = []
    ambiguous = []
    updated_origins = set()

    for amt, o_list in orph_by_amt.items():
        if amt <= 0:
            continue
        d_list = diff_by_amt.get(amt, [])
        if not d_list:
            continue
        if len(o_list) == 1 and len(d_list) == 1:
            orph, diff = o_list[0], d_list[0]
            slip_date = (orph.get("details") or {}).get("date", "")
            if not _reposicion_date_ok(slip_date, diff.get("origin_date", "")):
                ambiguous.append({
                    "amount": amt, "orphan_count": 1, "diff_count": 1,
                    "reason": "fecha de boleta anterior al cierre",
                })
                continue
            detail = _apply_reposicion_link(orph, diff, user_email)
            if detail:
                pair_details.append(detail)
                updated_origins.update(detail["origins"])
        else:
            ambiguous.append({
                "amount": amt,
                "orphan_count": len(o_list),
                "diff_count": len(d_list),
                "reason": "varios candidatos del mismo monto",
            })

    return {
        "pairs_resolved": len(pair_details),
        "reports_updated": len(updated_origins),
        "pair_details": pair_details,
        "ambiguous": ambiguous,
    }


def find_reposicion_candidates(pending: dict, tolerance: float = 1.0) -> list[dict]:
    """
    Given an open boleta_huerfana OR diferencia_interna_cierre, return the open
    pendings of the OPPOSITE type whose amount matches (within tolerance) and whose
    dates are consistent with a reposición. Powers the inline linker in the tray.
    """
    ptype = pending.get("type")
    if ptype == "boleta_huerfana":
        opp = "diferencia_interna_cierre"
    elif ptype == "diferencia_interna_cierre":
        opp = "boleta_huerfana"
    else:
        return []

    amt = _safe_float(pending.get("amount"))
    out = []
    for c in list_pending(only_open=True):
        if c["type"] != opp or c["id"] == pending.get("id"):
            continue
        if abs(_safe_float(c.get("amount")) - amt) > tolerance:
            continue
        if ptype == "boleta_huerfana":
            slip_date = (pending.get("details") or {}).get("date", "")
            close_date = c.get("origin_date", "")
        else:
            slip_date = (c.get("details") or {}).get("date", "")
            close_date = pending.get("origin_date", "")
        if not _reposicion_date_ok(slip_date, close_date):
            continue
        out.append(c)
    return out


def link_reposicion(orphan_id: str, diff_id: str, user_email: str) -> dict:
    """
    Explicitly link one orphan slip to one internal difference as a reposición
    (used by the inline linker for the ambiguous / manual case).
    Returns: {linked, reports_updated, slip, cashier, amount}
    """
    full = list_pending(only_open=True)
    orph = next((p for p in full
                 if p["id"] == orphan_id and p["type"] == "boleta_huerfana"), None)
    diff = next((p for p in full
                 if p["id"] == diff_id and p["type"] == "diferencia_interna_cierre"), None)
    if not orph or not diff:
        return {"linked": 0, "reports_updated": 0}
    detail = _apply_reposicion_link(orph, diff, user_email)
    if not detail:
        return {"linked": 0, "reports_updated": 0}
    return {
        "linked": 1,
        "reports_updated": len(detail["origins"]),
        "slip": detail["slip"],
        "cashier": detail["cashier"],
        "amount": detail["amount"],
    }


def repair_multi_deposit_bug_in_history(tolerance: float = 1.0) -> dict:
    """
    Detect and repair the "multi-deposit bug" in historical reports.

    The bug: when a single POS closing has MULTIPLE partial deposits (e.g. Q 1,824
    + Q 900 = Q 2,724), the old prompt summed them and treated as ONE deposit of
    Q 2,724. Then it failed to match against any single boleta and marked the
    sum as `missing_slip` (or used wrong matching). Meanwhile, the individual
    boletas that DO exist (Q 1,824 + Q 900 separately) ended up as `orphan_slips`.

    This function:
      1. Scans all historical reports
      2. For each `missing_slip` in a report, looks for COMBINATIONS of `orphan_slips`
         (same report or in pending tray) that sum to the missing amount
      3. If a combination of 2-3 orphans sums to the missing amount within
         tolerance, it splits the missing into the individual deposits and
         matches each with its orphan
      4. Updates the report bank_reconciliation accordingly + adds a finding
      5. Resolves the affected pendings

    Returns dict with stats.
    """
    from itertools import combinations

    history = list_history()
    if not history:
        return {"reports_fixed": 0, "splits_made": 0, "pendings_resolved": 0, "details": []}

    open_pendings = list_pending(only_open=True)
    open_orphan_pendings = [p for p in open_pendings if p["type"] == "boleta_huerfana"]
    open_missing_pendings = [p for p in open_pendings if p["type"] == "deposito_sin_boleta"]

    reports_fixed = 0
    splits_made = 0
    pendings_resolved_count = 0
    details = []

    for h in history:
        rid = h["id"]
        data = h.get("json_data") or {}
        bank = data.get("bank_reconciliation") or {}
        missing_slips = list(bank.get("missing_slips") or [])
        orphan_slips = list(bank.get("orphan_slips") or [])

        if not missing_slips:
            continue

        # Build pool of available orphans: orphans in THIS report + open orphan pendings
        # We'll track them so we don't double-use
        local_orphans = [
            {"src": "local", "ref": (o.get("slip_number") or "").strip(),
             "amount": float(o.get("amount") or 0), "obj": o}
            for o in orphan_slips
        ]
        pending_orphans = [
            {"src": "pending", "ref": (p.get("details", {}).get("slip_number") or "").strip(),
             "amount": float(p.get("amount") or 0), "obj": p}
            for p in open_orphan_pendings
        ]
        available_orphans = local_orphans + pending_orphans

        new_missing_slips = []
        used_orphan_ids = set()  # track by (src, ref) tuples
        local_changes = []
        new_matched = list(bank.get("matched") or [])

        for miss in missing_slips:
            miss_amt = float(miss.get("amount") or 0)
            miss_pos = (miss.get("pos_ref") or "").strip()
            miss_cashier = miss.get("cashier", "")

            if miss_amt <= 0:
                new_missing_slips.append(miss)
                continue

            # Try to find a combination of 2-3 orphans that sum to miss_amt
            usable = [
                o for o in available_orphans
                if (o["src"], o["ref"]) not in used_orphan_ids and o["amount"] > 0
            ]

            found_combo = None
            # Try combinations of size 2, then 3 (size 1 is the regular matching case)
            for combo_size in (2, 3):
                if len(usable) < combo_size:
                    continue
                for combo in combinations(usable, combo_size):
                    total = sum(o["amount"] for o in combo)
                    if abs(total - miss_amt) <= tolerance:
                        found_combo = combo
                        break
                if found_combo:
                    break

            if not found_combo:
                new_missing_slips.append(miss)
                continue

            # Found a combination! Split the missing into individual deposits matched
            # with each orphan
            for o in found_combo:
                new_matched.append({
                    "pos_ref": miss_pos,
                    "pos_amount": o["amount"],
                    "slip_number": o["ref"],
                    "slip_amount": o["amount"],
                    "cashier": miss_cashier,
                    "rescued_by_multidep_repair": True,
                    "note": f"Depósito parcial recuperado (parte de Q {miss_amt:.2f})",
                })
                used_orphan_ids.add((o["src"], o["ref"]))
                splits_made += 1

                # If the orphan came from a pending, mark it resolved
                if o["src"] == "pending":
                    pid = o["obj"]["id"]
                    if mark_pending_resolved(pid, f"multidep-repair-auto"):
                        pendings_resolved_count += 1

            local_changes.append({
                "report_id": rid,
                "missing_pos_ref": miss_pos,
                "missing_amount": miss_amt,
                "cashier": miss_cashier,
                "split_into": [
                    {"slip": o["ref"], "amount": o["amount"], "src": o["src"]}
                    for o in found_combo
                ],
            })
            details.append(local_changes[-1])

        if not local_changes:
            continue

        # Update report
        # Remove orphans we used (only local ones; pending ones are handled by mark_pending_resolved)
        used_local_refs = {
            ref for src, ref in used_orphan_ids if src == "local"
        }
        new_orphan_slips = [
            o for o in orphan_slips
            if (o.get("slip_number") or "").strip() not in used_local_refs
        ]

        bank["missing_slips"] = new_missing_slips
        bank["orphan_slips"] = new_orphan_slips
        bank["matched"] = new_matched
        data["bank_reconciliation"] = bank

        # Add finding
        findings = data.get("findings") or []
        for change in local_changes:
            split_desc = " + ".join(
                f"J {s['slip']} Q {s['amount']:.2f}"
                + (" [de bandeja de pendientes]" if s["src"] == "pending" else "")
                for s in change["split_into"]
            )
            findings.append({
                "severity": "info",
                "title": "Reparación de bug multi-depósito",
                "detail": (
                    f"El depósito {change['missing_pos_ref']} de {change['cashier']} "
                    f"(Q {change['missing_amount']:.2f}) fue particionado correctamente "
                    f"en {len(change['split_into'])} depósitos parciales que cuadran exacto: "
                    f"{split_desc}. Esto corrige un bug anterior donde múltiples depósitos "
                    f"parciales en un mismo cierre se sumaban y trataban como uno solo."
                ),
            })
        data["findings"] = findings

        # Upgrade overall_status if all issues are resolved now
        if data.get("overall_status") in ("warning", "issues"):
            still_has_issues = (
                bank.get("missing_slips")
                or bank.get("orphan_slips")
                or any(_safe_float(c.get("diferencia_interna")) > 0
                       for c in (data.get("cashier_breakdown") or []))
            )
            if not still_has_issues:
                data["overall_status"] = "ok"

        if update_report(rid, data):
            reports_fixed += 1

    return {
        "reports_fixed": reports_fixed,
        "splits_made": splits_made,
        "pendings_resolved": pendings_resolved_count,
        "details": details,
    }


def resolve_pending_manually(pending_id: str, user_email: str, note: str) -> dict:
    """
    Mark a single pending as resolved without an attached document
    (e.g. cashier reposed the missing cash in person).
    Updates origin report to reflect resolution.

    Returns {"resolved": 1 or 0, "origin_reports_updated": N}
    """
    full = list_pending(only_open=False)
    pending = next((p for p in full if p["id"] == pending_id), None)
    if not pending:
        return {"resolved": 0, "origin_reports_updated": 0}

    resolver_label = f"manual-{user_email}"
    if not mark_pending_resolved(pending_id, resolver_label):
        return {"resolved": 0, "origin_reports_updated": 0}

    resolved_items = [{
        "pending_id": pending_id,
        "pending_type": pending["type"],
        "original_report_id": pending["origin_report_id"],
        "amount": pending["amount"],
        "matched_with": "Resolución manual",
        "note": note,
    }]
    origin_count = apply_resolutions_to_origin_reports(resolved_items)
    return {"resolved": 1, "origin_reports_updated": origin_count}


def resolve_pending_with_compensation(
    pending_id: str,
    compensation_amount: float,
    user_email: str,
    note: str,
) -> dict:
    """
    Resolve a pending with a manual compensation adjustment (no document).

    The compensation_amount represents the net cash impact:
      + positive  = money entered / surplus accepted
      - negative  = money exited / loss accepted

    The pending is ALWAYS marked resolved (the Lic.'s decision is authoritative),
    and the origin report is updated with a finding capturing the adjustment for
    audit trail purposes.

    Args:
        pending_id: the pending ID to resolve
        compensation_amount: signed amount of the adjustment (in GTQ)
        user_email: who is applying the adjustment (for traceability)
        note: justification text (required by UI, not enforced here)

    Returns: {"resolved": 0 or 1, "origin_reports_updated": N, "compensation": amount}
    """
    full = list_pending(only_open=False)
    pending = next((p for p in full if p["id"] == pending_id), None)
    if not pending:
        return {"resolved": 0, "origin_reports_updated": 0, "compensation": 0}

    # Store compensation data inside details_json before marking resolved
    # so we have permanent record
    ws = _ensure_pending_tab()
    all_values = ws.get_all_values()
    if not all_values:
        return {"resolved": 0, "origin_reports_updated": 0, "compensation": 0}
    headers = all_values[0]
    col_idx = {h: i for i, h in enumerate(headers)}

    for i, row in enumerate(all_values[1:], start=2):
        if not row or row[0].strip() != pending_id:
            continue
        # Update details_json to include compensation data
        try:
            current_details = json.loads(row[col_idx["details_json"]] or "{}")
        except Exception:
            current_details = {}
        current_details["compensation_amount"] = float(compensation_amount)
        current_details["compensation_by"] = user_email
        current_details["compensation_note"] = note
        current_details["compensation_at"] = dt.datetime.now(GT_TZ).isoformat(timespec="seconds")
        ws.update_cell(
            i, col_idx["details_json"] + 1,
            json.dumps(current_details, ensure_ascii=False),
        )
        break

    # Mark resolved with a special label so we know it was a compensation
    resolver_label = f"compensation-{user_email}"
    if not mark_pending_resolved(pending_id, resolver_label):
        return {"resolved": 0, "origin_reports_updated": 0, "compensation": 0}

    # Update origin report with an audit-trail finding
    origin = get_report_by_id(pending["origin_report_id"])
    origin_updated = 0
    if origin and origin.get("json_data"):
        report = origin["json_data"]
        bank = report.get("bank_reconciliation") or {}

        # Type-specific cleanup so the pendant disappears from the historical view
        ptype = pending["type"]
        details = pending.get("details", {}) or {}
        if ptype == "deposito_sin_boleta":
            pos_ref = details.get("pos_ref", "")
            bank["missing_slips"] = [
                m for m in (bank.get("missing_slips") or [])
                if (m.get("pos_ref") or "") != pos_ref
            ]
        elif ptype == "boleta_huerfana":
            sn = details.get("slip_number", "")
            bank["orphan_slips"] = [
                o for o in (bank.get("orphan_slips") or [])
                if (o.get("slip_number") or "") != sn
            ]
        elif ptype == "diferencia_interna_cierre":
            pos_ref = details.get("pos_ref", "")
            for c in (report.get("cashier_breakdown") or []):
                if (c.get("pos_ref") or "") == pos_ref:
                    c["diferencia_interna"] = 0
                    prev_note = c.get("notes", "")
                    add_note = f"[Resuelto con compensación manual de Q {compensation_amount:.2f}]"
                    c["notes"] = (prev_note + " " + add_note).strip()

        report["bank_reconciliation"] = bank

        # Add audit finding
        findings = report.get("findings") or []
        sign_label = "ingreso" if compensation_amount > 0 else ("pérdida aceptada" if compensation_amount < 0 else "neutralizado")
        findings.append({
            "severity": "warn",
            "title": "Ajuste manual aplicado por compensación",
            "detail": (
                f"El Lic. ({user_email}) aplicó una compensación manual de "
                f"Q {compensation_amount:.2f} ({sign_label}) sobre el pendiente "
                f"de {ptype} (monto original Q {pending['amount']:.2f}). "
                f"Justificación: {note}"
            ),
        })
        report["findings"] = findings

        # Possibly upgrade overall_status if no other issues remain
        if report.get("overall_status") == "warning":
            still_has_issues = (
                bank.get("missing_slips")
                or bank.get("orphan_slips")
                or any(_safe_float(c.get("diferencia_interna")) > 0
                       for c in (report.get("cashier_breakdown") or []))
            )
            # Note: we DON'T auto-upgrade to "ok" when there's a manual adjustment,
            # because the finding is still a warning. The Lic./Pablo can see the
            # cierre is closed-but-with-manual-adjustment.

        if update_report(pending["origin_report_id"], report):
            origin_updated = 1

    return {
        "resolved": 1,
        "origin_reports_updated": origin_updated,
        "compensation": compensation_amount,
    }


def list_compensations_in_period(start_iso: str, end_iso: str) -> list[dict]:
    """
    Return all manual compensations applied in the given date range.
    Reads from resolved pendings whose details contain compensation_at within range.
    Used for monthly P&L reporting in Centro Ejecutivo > Resumen.
    """
    out = []
    for p in list_pending(only_open=False):
        if p.get("status") != "resolved":
            continue
        details = p.get("details", {}) or {}
        if "compensation_amount" not in details:
            continue
        comp_at = details.get("compensation_at", "")
        if not comp_at:
            continue
        comp_date = comp_at[:10]  # YYYY-MM-DD prefix
        if start_iso <= comp_date <= end_iso:
            out.append({
                "pending_id": p["id"],
                "pending_type": p["type"],
                "origin_report_id": p["origin_report_id"],
                "origin_date": p["origin_date"],
                "original_amount": p["amount"],
                "compensation_amount": float(details.get("compensation_amount", 0)),
                "compensation_by": details.get("compensation_by", ""),
                "compensation_note": details.get("compensation_note", ""),
                "compensation_at": comp_at,
                "details": details,
            })
    out.sort(key=lambda x: x["compensation_at"], reverse=True)
    return out


def resolve_pending_inline(pending_ids: list[str], resolver_report_id: str,
                            slip_or_pdf_id: str, amount: float,
                            note: str = "") -> dict:
    """
    Mark a list of pendings as resolved by an inline upload action.
    Updates origin reports to reflect resolution.

    Args:
        pending_ids: list of pending IDs being resolved (1 or more if combined)
        resolver_report_id: synthetic ID for this inline resolution event
        slip_or_pdf_id: the slip number (J No.) or POS ref of the new doc
        amount: amount of the uploaded doc
        note: optional human note

    Returns: {"resolved": N, "origin_reports_updated": M}
    """
    resolved_items = []
    for pid in pending_ids:
        # Look up pending details before marking resolved
        full = list_pending(only_open=False)
        pending = next((p for p in full if p["id"] == pid), None)
        if not pending:
            continue
        if mark_pending_resolved(pid, resolver_report_id):
            resolved_items.append({
                "pending_id": pid,
                "pending_type": pending["type"],
                "original_report_id": pending["origin_report_id"],
                "amount": pending["amount"],
                "matched_with": slip_or_pdf_id,
                "note": note,
            })

    origin_count = apply_resolutions_to_origin_reports(resolved_items)

    return {
        "resolved": len(resolved_items),
        "origin_reports_updated": origin_count,
    }


def create_partial_remainder_pending(original_pending: dict, remainder_amount: float,
                                       note: str = "") -> str:
    """
    When a pending gets PARTIALLY resolved (e.g. pending was Q1,697 and the new
    boleta is only Q1,500), we mark the original as resolved and create a new
    pending for the remainder (Q197).
    """
    details = dict(original_pending.get("details", {}))
    details["note"] = (
        f"Resto pendiente tras pago parcial. Pendiente original: "
        f"Q{original_pending['amount']:.2f}. {note}"
    ).strip()
    return add_pending(
        pending_type=original_pending["type"],
        amount=remainder_amount,
        origin_report_id=original_pending["origin_report_id"],
        origin_date=original_pending["origin_date"],
        details=details,
    )


def slip_number_exists_in_history(slip_number: str) -> tuple[bool, str]:
    """
    Check if a J No. is already registered somewhere. Returns (exists, report_id_or_pending_id).
    """
    sn = (slip_number or "").strip()
    if not sn:
        return False, ""

    # Check in cierres_historicos via catalog
    try:
        catalog = build_processed_catalog()
        if sn in catalog.get("bank_slips", {}):
            return True, catalog["bank_slips"][sn]
    except Exception:
        pass

    # Check inline-resolved slips: stored as resolver_report_id in pending rows
    try:
        all_p = list_pending(only_open=False)
        for p in all_p:
            d = p.get("details", {}) or {}
            if d.get("slip_number") == sn:
                return True, p["id"]
    except Exception:
        pass

    return False, ""


def pos_ref_exists_in_history(pos_ref: str) -> tuple[bool, str]:
    """Check if a POS ref is already registered."""
    pr = (pos_ref or "").strip()
    if not pr:
        return False, ""
    try:
        catalog = build_processed_catalog()
        if pr in catalog.get("pos_refs", {}):
            return True, catalog["pos_refs"][pr]
    except Exception:
        pass
    return False, ""
