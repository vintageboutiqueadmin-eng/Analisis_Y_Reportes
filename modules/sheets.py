"""
Google Sheets integration.

Uses a service account configured in Streamlit secrets under [gcp_service_account].
The spreadsheet ID and tab names live under [sheets] in secrets.

Expected tabs:
  - employees: id | name | store_id | active
  - stores:    id | name | marker
  - attendance: date | employee_id | status | shift_start | shift_end |
                lunch_start | lunch_end | overtime_minutes | is_late |
                actual_start | notes | updated_by | updated_at
"""

from __future__ import annotations

import datetime as dt
from typing import Any
from zoneinfo import ZoneInfo

import streamlit as st


GT_TZ = ZoneInfo("America/Guatemala")


# ---------------------------------------------------------------------------
# Client
# ---------------------------------------------------------------------------

@st.cache_resource
def get_client():
    """Authenticated gspread client (service account)."""
    import gspread
    from google.oauth2.service_account import Credentials

    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive.readonly",
    ]
    info = dict(st.secrets["gcp_service_account"])
    creds = Credentials.from_service_account_info(info, scopes=scopes)
    return gspread.authorize(creds)


def get_spreadsheet():
    sheet_id = st.secrets["sheets"]["spreadsheet_id"]
    return get_client().open_by_key(sheet_id)


def _tab_name(default: str, key: str | None = None) -> str:
    if key:
        try:
            return st.secrets["sheets"].get(key, default)
        except Exception:
            return default
    return default


# ---------------------------------------------------------------------------
# Readers (cached)
# ---------------------------------------------------------------------------

@st.cache_data(ttl=30, show_spinner=False)
def get_employees() -> list[dict]:
    ws = get_spreadsheet().worksheet(_tab_name("employees", "tab_employees"))
    rows = ws.get_all_records()
    out = []
    for r in rows:
        active = str(r.get("active", "")).strip().lower()
        if active in ("false", "0", "no", "inactivo"):
            continue
        out.append({
            "id": str(r.get("id", "")).strip(),
            "name": str(r.get("name", "")).strip(),
            "store_id": str(r.get("store_id", "")).strip(),
        })
    return out


@st.cache_data(ttl=300, show_spinner=False)
def get_stores() -> list[dict]:
    ws = get_spreadsheet().worksheet(_tab_name("stores", "tab_stores"))
    rows = ws.get_all_records()
    return [
        {
            "id": str(r.get("id", "")).strip(),
            "name": str(r.get("name", "")).strip(),
            "marker": str(r.get("marker", "")).strip(),
        }
        for r in rows
        if r.get("id")
    ]


@st.cache_data(ttl=15, show_spinner=False)
def get_attendance_for_date(date_iso: str) -> list[dict]:
    ws = get_spreadsheet().worksheet(_tab_name("attendance", "tab_attendance"))
    rows = ws.get_all_records()
    out = []
    for r in rows:
        if str(r.get("date", "")).strip() != date_iso:
            continue
        out.append({
            "date": date_iso,
            "employee_id": str(r.get("employee_id", "")).strip(),
            "status": str(r.get("status", "working")).strip() or "working",
            "shift_start": str(r.get("shift_start", "")).strip() or None,
            "shift_end": str(r.get("shift_end", "")).strip() or None,
            "lunch_start": str(r.get("lunch_start", "")).strip() or None,
            "lunch_end": str(r.get("lunch_end", "")).strip() or None,
            "overtime_minutes": _to_int(r.get("overtime_minutes")),
            "is_late": _to_bool(r.get("is_late")),
            "actual_start": str(r.get("actual_start", "")).strip() or None,
            "notes": str(r.get("notes", "")).strip(),
            "worked_store_id": str(r.get("worked_store_id", "")).strip() or None,
        })
    return out


def _to_int(v: Any) -> int:
    try:
        return int(float(str(v).strip()))
    except (ValueError, TypeError):
        return 0


def _to_bool(v: Any) -> bool:
    if v is True:
        return True
    s = str(v).strip().lower()
    return s in ("true", "1", "yes", "sí", "si", "tarde")


# ---------------------------------------------------------------------------
# Writers
# ---------------------------------------------------------------------------

ATTENDANCE_HEADERS = [
    "date", "employee_id", "status", "shift_start", "shift_end",
    "lunch_start", "lunch_end", "overtime_minutes", "is_late",
    "actual_start", "notes", "updated_by", "updated_at",
    "worked_store_id",
]


def upsert_attendance(record: dict, updated_by: str) -> None:
    """Insert or update a single attendance row keyed by (date, employee_id)."""
    ws = get_spreadsheet().worksheet(_tab_name("attendance", "tab_attendance"))
    all_values = ws.get_all_values()

    # Make sure headers are correct
    if not all_values:
        ws.append_row(ATTENDANCE_HEADERS)
        all_values = [ATTENDANCE_HEADERS]

    headers = all_values[0]
    # Verify header alignment (or write them if mismatched)
    if [h.strip().lower() for h in headers] != [h.lower() for h in ATTENDANCE_HEADERS]:
        # Write canonical headers in row 1
        ws.update("A1", [ATTENDANCE_HEADERS])
        headers = ATTENDANCE_HEADERS
        all_values[0] = ATTENDANCE_HEADERS

    date_iso = record["date"]
    emp_id = str(record["employee_id"])

    # Find existing row
    target_row = None
    for i, row in enumerate(all_values[1:], start=2):  # 1-indexed including header
        if len(row) < 2:
            continue
        if row[0].strip() == date_iso and row[1].strip() == emp_id:
            target_row = i
            break

    now_iso = dt.datetime.now(GT_TZ).isoformat(timespec="seconds")
    row_values = [
        date_iso,
        emp_id,
        record.get("status", "working"),
        record.get("shift_start") or "",
        record.get("shift_end") or "",
        record.get("lunch_start") or "",
        record.get("lunch_end") or "",
        str(record.get("overtime_minutes") or 0),
        "true" if record.get("is_late") else "false",
        record.get("actual_start") or "",
        record.get("notes") or "",
        updated_by,
        now_iso,
        record.get("worked_store_id") or "",
    ]

    if target_row:
        ws.update(f"A{target_row}", [row_values])
    else:
        ws.append_row(row_values)

    # Invalidate cache for this date
    get_attendance_for_date.clear()


def delete_attendance(date_iso: str, employee_id: str) -> None:
    ws = get_spreadsheet().worksheet(_tab_name("attendance", "tab_attendance"))
    all_values = ws.get_all_values()
    for i, row in enumerate(all_values[1:], start=2):
        if len(row) >= 2 and row[0].strip() == date_iso and row[1].strip() == str(employee_id):
            ws.delete_rows(i)
            break
    get_attendance_for_date.clear()


# ---------------------------------------------------------------------------
# Employee admin (used by admin module)
# ---------------------------------------------------------------------------

def add_employee(name: str, store_id: str) -> None:
    ws = get_spreadsheet().worksheet(_tab_name("employees", "tab_employees"))
    rows = ws.get_all_records()
    next_id = 1
    for r in rows:
        try:
            next_id = max(next_id, int(r.get("id") or 0) + 1)
        except Exception:
            pass
    ws.append_row([str(next_id), name, store_id, "true"])
    get_employees.clear()


def set_employee_active(employee_id: str, active: bool) -> None:
    ws = get_spreadsheet().worksheet(_tab_name("employees", "tab_employees"))
    all_values = ws.get_all_values()
    for i, row in enumerate(all_values[1:], start=2):
        if row and row[0].strip() == str(employee_id):
            ws.update_cell(i, 4, "true" if active else "false")
            break
    get_employees.clear()


# ---------------------------------------------------------------------------
# Bootstrap helpers (admin)
# ---------------------------------------------------------------------------

def ensure_workbook_structure() -> dict:
    """
    Make sure the three tabs exist with the right headers.
    Safe to call repeatedly.
    """
    ss = get_spreadsheet()
    titles = {ws.title for ws in ss.worksheets()}
    created = []

    def ensure(tab: str, headers: list[str]) -> None:
        if tab not in titles:
            ss.add_worksheet(title=tab, rows=200, cols=max(10, len(headers)))
            created.append(tab)
        ws = ss.worksheet(tab)
        first_row = ws.row_values(1)
        if [h.strip().lower() for h in first_row] != [h.lower() for h in headers]:
            ws.update("A1", [headers])

    ensure(_tab_name("stores", "tab_stores"), ["id", "name", "marker"])
    ensure(_tab_name("employees", "tab_employees"), ["id", "name", "store_id", "active"])
    ensure(_tab_name("attendance", "tab_attendance"), ATTENDANCE_HEADERS)

    return {"created": created}


def seed_default_data() -> None:
    """Populate stores and the demo roster (idempotent — only adds missing rows)."""
    ss = get_spreadsheet()

    # Stores
    sws = ss.worksheet(_tab_name("stores", "tab_stores"))
    existing_store_ids = {str(r.get("id", "")).strip() for r in sws.get_all_records()}
    default_stores = [
        ("7ma_ave", "7ma Avenida", "Sede 01"),
        ("6ta_ave", "6ta Avenida", "Sede 02"),
    ]
    for sid, name, marker in default_stores:
        if sid not in existing_store_ids:
            sws.append_row([sid, name, marker])

    # Employees
    ews = ss.worksheet(_tab_name("employees", "tab_employees"))
    existing_emp_names = {str(r.get("name", "")).strip().lower() for r in ews.get_all_records()}
    next_id = 1
    for r in ews.get_all_records():
        try:
            next_id = max(next_id, int(r.get("id") or 0) + 1)
        except Exception:
            pass
    default_employees = [
        ("Jonathan", "7ma_ave"),
        ("Daisy", "7ma_ave"),
        ("Alejandra Mota", "6ta_ave"),
        ("Sonia", "6ta_ave"),
        ("Ismael", "6ta_ave"),
        ("Isabel", "6ta_ave"),
    ]
    for name, store_id in default_employees:
        if name.lower() not in existing_emp_names:
            ews.append_row([str(next_id), name, store_id, "true"])
            next_id += 1

    get_stores.clear()
    get_employees.clear()
