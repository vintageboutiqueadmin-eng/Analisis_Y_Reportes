"""
Dashboard view for the Lic. Juan Orozco (and anyone with viewer access).
Builds a `data` dict from Google Sheets and renders the executive HTML.
"""

from __future__ import annotations

import datetime as dt
import locale

import streamlit as st

from . import sheets
from .dashboard_html import render_dashboard, parse_time


SPANISH_WEEKDAYS = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"]
SPANISH_MONTHS = [
    "Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio",
    "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre",
]


def _format_spanish_date(d: dt.date) -> str:
    wd = SPANISH_WEEKDAYS[d.weekday()]
    mo = SPANISH_MONTHS[d.month - 1]
    return f"{wd} {d.day} de {mo}, {d.year}".upper()


def _now_minutes_for(date: dt.date) -> int | None:
    """Return current minutes-from-midnight if `date` is today, else None."""
    today = dt.date.today()
    if date == today:
        n = dt.datetime.now()
        return n.hour * 60 + n.minute
    return None


def _compute_stats(employees: list[dict], records_by_emp: dict, now_min: int | None) -> dict:
    total = len(employees)
    working = 0
    lunch = 0
    off = 0
    other_absent = 0
    for emp in employees:
        rec = records_by_emp.get(emp["id"])
        status = rec.get("status", "working") if rec else None
        if not rec or status == "working":
            if not rec:
                # No record yet → counted as not assigned, treat as 'other'
                continue
            ss = parse_time(rec.get("shift_start"))
            se = parse_time(rec.get("shift_end"))
            ls = parse_time(rec.get("lunch_start"))
            le = parse_time(rec.get("lunch_end"))
            ot = rec.get("overtime_minutes") or 0
            # Determine current state
            if now_min is None:
                # Past or future date — count as scheduled working
                working += 1
            else:
                end_with_ot = (se or 0) + ot
                if ls is not None and le is not None and ls <= now_min < le:
                    lunch += 1
                elif ss is not None and end_with_ot and ss <= now_min < end_with_ot:
                    working += 1
                # else: not yet on shift / already left → don't count as working
        elif status == "day_off":
            off += 1
        else:
            other_absent += 1

    return {
        "total": total,
        "working": working,
        "lunch": lunch,
        "off": off,
        "other_absent": other_absent,
    }


def _build_data(date: dt.date) -> dict:
    employees = sheets.get_employees()
    stores = sheets.get_stores()
    attendance = sheets.get_attendance_for_date(date.isoformat())
    records_by_emp = {r["employee_id"]: r for r in attendance}

    now_min = _now_minutes_for(date)
    stats = _compute_stats(employees, records_by_emp, now_min)

    # Group employees by store, then sort with workers first then absences
    stores_out = []
    for store in stores:
        store_emps = [e for e in employees if e["store_id"] == store["id"]]
        rendered_emps = []
        for emp in store_emps:
            rec = records_by_emp.get(emp["id"])
            if not rec:
                # No record for this date → treat as unscheduled (day_off)
                rendered_emps.append({
                    "name": emp["name"],
                    "status": "day_off",
                    "notes": "Sin asignación para esta fecha",
                })
                continue
            rendered_emps.append({
                "name": emp["name"],
                "status": rec.get("status", "working"),
                "shift_start": rec.get("shift_start"),
                "shift_end": rec.get("shift_end"),
                "lunch_start": rec.get("lunch_start"),
                "lunch_end": rec.get("lunch_end"),
                "overtime_minutes": rec.get("overtime_minutes") or 0,
                "is_late": rec.get("is_late", False),
                "actual_start": rec.get("actual_start"),
                "notes": rec.get("notes", ""),
            })

        # Working employees first, then absences
        rendered_emps.sort(
            key=lambda e: (0 if e.get("status") == "working" else 1, e["name"])
        )

        stores_out.append({
            "title": store["name"],
            "marker": store.get("marker", ""),
            "employees": rendered_emps,
        })

    return {
        "date_display": _format_spanish_date(date),
        "now_minutes": now_min,
        "stats": stats,
        "stores": stores_out,
    }


# ---------------------------------------------------------------------------
# Streamlit entry point
# ---------------------------------------------------------------------------

def render(current_user: dict) -> None:
    """Render the dashboard page in Streamlit."""
    # Hide default Streamlit chrome
    st.markdown(
        """
        <style>
        #MainMenu, header, footer { visibility: hidden; }
        .block-container { padding-top: 0 !important; padding-left: 0 !important;
                           padding-right: 0 !important; padding-bottom: 0 !important;
                           max-width: 100% !important; }
        section[data-testid="stSidebar"] { background: #FFF; border-right: 1px solid #D8DCE2; }
        </style>
        """,
        unsafe_allow_html=True,
    )

    # Sidebar — date picker + nav
    with st.sidebar:
        st.markdown(
            "<div style='padding:18px 4px 8px;font-family:Geist,sans-serif;'>"
            "<div style='font-size:10px;letter-spacing:2.5px;text-transform:uppercase;"
            "color:#6C7280;font-weight:600;margin-bottom:6px;'>"
            "<span style='color:#C9982A;'>●</span> Vintage Boutique</div>"
            "<div style='font-size:16px;font-weight:600;letter-spacing:-0.2px;'>"
            "Panel de Asistencia</div></div>",
            unsafe_allow_html=True,
        )

        st.markdown("---")
        st.markdown("**Fecha**")
        selected_date = st.date_input(
            "Fecha a consultar",
            value=st.session_state.get("dashboard_date", dt.date.today()),
            format="DD/MM/YYYY",
            label_visibility="collapsed",
        )
        st.session_state.dashboard_date = selected_date

        col_a, col_b = st.columns(2)
        if col_a.button("← Ayer", use_container_width=True):
            st.session_state.dashboard_date = selected_date - dt.timedelta(days=1)
            st.rerun()
        if col_b.button("Hoy", use_container_width=True):
            st.session_state.dashboard_date = dt.date.today()
            st.rerun()
        if st.button("Mañana →", use_container_width=True):
            st.session_state.dashboard_date = selected_date + dt.timedelta(days=1)
            st.rerun()

        st.markdown("---")
        if st.button("↻ Actualizar datos", use_container_width=True):
            sheets.get_attendance_for_date.clear()
            sheets.get_employees.clear()
            sheets.get_stores.clear()
            st.rerun()

        st.markdown("---")
        st.caption(f"Sesión: **{current_user['name']}**")
        st.caption(current_user["email"])

    # Main body — render the HTML dashboard
    try:
        data = _build_data(st.session_state.dashboard_date)
    except Exception as e:
        st.error(
            "No se pudieron cargar los datos desde Google Sheets.\n\n"
            f"Detalle: `{e}`\n\n"
            "Verifica la configuración en `secrets.toml` "
            "y que la cuenta de servicio tenga acceso al sheet."
        )
        return

    role_label = {"admin": "Administración", "manager": "Gerencia de Tiendas",
                  "viewer": "Gerencia"}.get(current_user["role"], "Usuario")

    html = render_dashboard(data, user_name=current_user["name"], user_role=role_label)
    st.markdown(html, unsafe_allow_html=True)
