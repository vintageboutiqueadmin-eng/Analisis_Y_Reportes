"""
Dashboard view for the Lic. Juan Orozco (and anyone with viewer access).
"""

from __future__ import annotations

import datetime as dt
from zoneinfo import ZoneInfo

import streamlit as st

from . import sheets
from .dashboard_html import (
    CSS, render_dashboard_body, parse_time,
)


# Guatemala is UTC-6, no DST. Streamlit Cloud runs UTC, so we must localize.
GT_TZ = ZoneInfo("America/Guatemala")


SPANISH_WEEKDAYS = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"]
SPANISH_MONTHS = [
    "Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio",
    "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre",
]


def now_gt() -> dt.datetime:
    """Current datetime in Guatemala timezone."""
    return dt.datetime.now(GT_TZ)


def today_gt() -> dt.date:
    return now_gt().date()


def _format_spanish_date(d: dt.date) -> str:
    wd = SPANISH_WEEKDAYS[d.weekday()]
    mo = SPANISH_MONTHS[d.month - 1]
    return f"{wd} {d.day} de {mo}, {d.year}".upper()


def _now_minutes_for(date: dt.date) -> int | None:
    """Return current minutes-from-midnight if `date` is today (GT time), else None."""
    if date == today_gt():
        n = now_gt()
        return n.hour * 60 + n.minute
    return None


def _compute_stats(employees, records_by_emp, now_min):
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
                continue
            ss = parse_time(rec.get("shift_start"))
            se = parse_time(rec.get("shift_end"))
            ls = parse_time(rec.get("lunch_start"))
            le = parse_time(rec.get("lunch_end"))
            ot = rec.get("overtime_minutes") or 0
            if now_min is None:
                working += 1
            else:
                end_with_ot = (se or 0) + ot
                if ls is not None and le is not None and ls <= now_min < le:
                    lunch += 1
                elif ss is not None and end_with_ot and ss <= now_min < end_with_ot:
                    working += 1
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

    stores_out = []
    for store in stores:
        store_emps = [e for e in employees if e["store_id"] == store["id"]]
        rendered_emps = []
        for emp in store_emps:
            rec = records_by_emp.get(emp["id"])
            if not rec:
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


def render(current_user: dict) -> None:
    """Render the dashboard page in Streamlit."""

    # Hide default Streamlit chrome and zero out container padding.
    # IMPORTANT: don't hide the header — it contains the sidebar reopen button.
    # Instead, make it transparent so it doesn't compete visually with our topbar.
    st.markdown(
        """
        <style>
        #MainMenu, footer { visibility: hidden; }

        /* Header transparent (not hidden) so the sidebar collapsed-button stays clickable */
        header[data-testid="stHeader"] {
            background: transparent !important;
            height: auto !important;
        }
        /* Sidebar collapse button — ensure it sits above our black topbar */
        [data-testid="collapsedControl"],
        [data-testid="stSidebarCollapsedControl"],
        button[kind="header"] {
            visibility: visible !important;
            opacity: 1 !important;
            z-index: 9999 !important;
            background: rgba(255,255,255,0.95) !important;
            border-radius: 4px !important;
            box-shadow: 0 2px 8px rgba(0,0,0,0.18) !important;
        }

        .block-container {
            padding-top: 0 !important; padding-left: 0 !important;
            padding-right: 0 !important; padding-bottom: 0 !important;
            max-width: 100% !important;
        }
        section[data-testid="stSidebar"] { background: #FFF; border-right: 1px solid #D8DCE2; }
        </style>
        """,
        unsafe_allow_html=True,
    )

    # Sidebar
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
            value=st.session_state.get("dashboard_date", today_gt()),
            format="DD/MM/YYYY",
            label_visibility="collapsed",
        )
        st.session_state.dashboard_date = selected_date

        col_a, col_b = st.columns(2)
        if col_a.button("← Ayer", use_container_width=True):
            st.session_state.dashboard_date = selected_date - dt.timedelta(days=1)
            st.rerun()
        if col_b.button("Hoy", use_container_width=True):
            st.session_state.dashboard_date = today_gt()
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
        st.caption(f"Hora GT: {now_gt().strftime('%H:%M')}")

    # Main body
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

    # CRITICAL: inject CSS and body separately to avoid Streamlit markdown
    # parser misinterpreting the large HTML block. st.html renders raw HTML
    # without any markdown processing.
    st.html(CSS)
    body_html = render_dashboard_body(
        data, user_name=current_user["name"], user_role=role_label
    )
    st.html(body_html)
