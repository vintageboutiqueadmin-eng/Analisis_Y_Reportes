"""
Persistencia del historial de cierres + bandeja de pendientes.

Pestañas usadas en Google Sheets:
  - cierres_historicos  → cada análisis completo
  - cierres_pendientes  → boletas huérfanas y depósitos sin boleta (bandeja)
"""

from __future__ import annotations

import datetime as dt
import json
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

    # cashier_breakdown[i].diferencia_interna > 0 → diferencia_interna_cierre
    for c in (report.get("cashier_breakdown") or []):
        diff = _safe_float(c.get("diferencia_interna"))
        if diff <= 0:
            continue
        add_pending(
            pending_type="diferencia_interna_cierre",
            amount=diff,
            origin_report_id=report_id,
            origin_date=report_date,
            details={
                "pos_ref": c.get("pos_ref", ""),
                "cashier": c.get("cashier", ""),
                "store": c.get("store", ""),
                "note": c.get("notes", ""),
            },
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
    Scan ALL historical reports and ensure every cashier with diferencia_interna > 0
    has a corresponding pending row in cierres_pendientes. Skips ones that
    already exist (matched by origin_report_id + pos_ref + amount).

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
        report_date = h.get("report_date") or ""
        for c in (data.get("cashier_breakdown") or []):
            scanned += 1
            diff = _safe_float(c.get("diferencia_interna"))
            if diff <= 0:
                continue
            sig = (rid, c.get("pos_ref", ""), round(diff, 2))
            if sig in existing:
                continue
            add_pending(
                pending_type="diferencia_interna_cierre",
                amount=diff,
                origin_report_id=rid,
                origin_date=report_date,
                details={
                    "pos_ref": c.get("pos_ref", ""),
                    "cashier": c.get("cashier", ""),
                    "store": c.get("store", ""),
                    "note": c.get("notes", ""),
                },
            )
            existing.add(sig)
            added += 1

    return {"scanned": scanned, "added": added}


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
