"""
Dashboard view for the Lic. Juan Orozco (and anyone with viewer access).
"""

from __future__ import annotations

import datetime as dt
from zoneinfo import ZoneInfo

import streamlit as st
from streamlit_autorefresh import st_autorefresh

from . import sheets
from .dashboard_html import (
    CSS, render_dashboard_body, parse_time,
)
from .dashboard_weekly import render_weekly_view


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


def _format_store_date(d: dt.date) -> str:
    """Fecha junto al nombre de la tienda, ej. 'Viernes 26 junio 2026'."""
    wd = SPANISH_WEEKDAYS[d.weekday()]
    mo = SPANISH_MONTHS[d.month - 1].lower()
    return f"{wd} {d.day} {mo} {d.year}"


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


def _parse_hhmm_to_minutes(s):
    """Convert 'HH:MM' to minutes since midnight, or None."""
    if not s:
        return None
    try:
        h, m = str(s).split(":")
        return int(h) * 60 + int(m)
    except Exception:
        return None


def _choose_active_segment(rec, now_min):
    """
    For a working employee with possibly 2 segments, decide which segment is
    "active" right now. Returns dict {store_id, shift_start, shift_end, is_seg2}.

    Logic:
      - If single shift (no split): always return segment 1.
      - If split:
          * If now is within segment 1 range → segment 1
          * If now is within segment 2 range → segment 2
          * If now < segment 1 start → segment 1 (the day hasn't started yet)
          * If now > segment 2 end → segment 2 (the day is over, show last segment)
          * If now is between segments → segment 1 (transition period)
      - now_min may be None (looking at a non-today date) — default to segment 1.
    """
    s1_store = rec.get("worked_store_id") or ""
    s1_start = rec.get("shift_start") or ""
    s1_end = rec.get("shift_end") or ""

    if not rec.get("shift_split"):
        return {
            "store_id": s1_store,
            "shift_start": s1_start,
            "shift_end": s1_end,
            "is_seg2": False,
        }

    s2_store = rec.get("segment2_store_id") or ""
    s2_start = rec.get("segment2_start") or ""
    s2_end = rec.get("segment2_end") or ""

    # If we have no "now" reference, return segment 1 by default
    if now_min is None:
        return {
            "store_id": s1_store,
            "shift_start": s1_start,
            "shift_end": s1_end,
            "is_seg2": False,
        }

    s1_start_min = _parse_hhmm_to_minutes(s1_start)
    s1_end_min = _parse_hhmm_to_minutes(s1_end)
    s2_start_min = _parse_hhmm_to_minutes(s2_start)
    s2_end_min = _parse_hhmm_to_minutes(s2_end)

    # If segment 2 is active or already over, use segment 2
    if s2_start_min is not None and now_min >= s2_start_min:
        return {
            "store_id": s2_store,
            "shift_start": s2_start,
            "shift_end": s2_end,
            "is_seg2": True,
        }

    # Otherwise segment 1
    return {
        "store_id": s1_store,
        "shift_start": s1_start,
        "shift_end": s1_end,
        "is_seg2": False,
    }


def _build_data(date: dt.date) -> dict:
    employees = sheets.get_employees()
    stores = sheets.get_stores()
    attendance = sheets.get_attendance_for_date(date.isoformat())
    records_by_emp = {r["employee_id"]: r for r in attendance}

    now_min = _now_minutes_for(date)
    stats = _compute_stats(employees, records_by_emp, now_min)

    # Build per-store buckets
    store_employees_map = {s["id"]: [] for s in stores}

    for emp in employees:
        rec = records_by_emp.get(emp["id"])

        if not rec:
            # No record → show at home store as "Sin asignación"
            target_store = emp["store_id"]
            if target_store in store_employees_map:
                store_employees_map[target_store].append({
                    "name": emp["name"],
                    "status": "day_off",
                    "notes": "Sin asignación para esta fecha",
                    "is_support": False,
                })
            continue

        status = rec.get("status", "working")

        # For non-working statuses, pin to home store
        if status != "working":
            target_store = emp["store_id"]
            if target_store in store_employees_map:
                store_employees_map[target_store].append({
                    "name": emp["name"],
                    "status": status,
                    "shift_start": rec.get("shift_start"),
                    "shift_end": rec.get("shift_end"),
                    "lunch_start": rec.get("lunch_start"),
                    "lunch_end": rec.get("lunch_end"),
                    "overtime_minutes": rec.get("overtime_minutes") or 0,
                    "is_late": rec.get("is_late", False),
                    "actual_start": rec.get("actual_start"),
                    "notes": rec.get("notes", ""),
                    "is_support": False,
                })
            continue

        # WORKING — figure out which segment is currently active
        active = _choose_active_segment(rec, now_min)
        target_store = active["store_id"] or emp["store_id"]
        if target_store not in store_employees_map:
            target_store = emp["store_id"]
            if target_store not in store_employees_map:
                continue

        # Support badge applies per active segment: if active segment's store
        # is not the employee's home store, show "Apoyo"
        is_support = (target_store != emp["store_id"])

        store_employees_map[target_store].append({
            "name": emp["name"],
            "status": "working",
            "shift_start": active["shift_start"],
            "shift_end": active["shift_end"],
            "lunch_start": rec.get("lunch_start"),
            "lunch_end": rec.get("lunch_end"),
            "overtime_minutes": rec.get("overtime_minutes") or 0,
            "is_late": rec.get("is_late", False),
            "actual_start": rec.get("actual_start"),
            "notes": rec.get("notes", ""),
            "is_support": is_support,
            "is_split_segment": active["is_seg2"],
        })

    stores_out = []
    for store in stores:
        emps_here = store_employees_map.get(store["id"], [])
        emps_here.sort(
            key=lambda e: (0 if e.get("status") == "working" else 1, e["name"])
        )
        stores_out.append({
            "title": store["name"],
            "marker": store.get("marker", ""),
            "employees": emps_here,
        })

    return {
        "date_display": _format_spanish_date(date),
        "date_label": _format_store_date(date),
        "now_minutes": now_min,
        "stats": stats,
        "stores": stores_out,
    }


def render(current_user: dict) -> None:
    """Render the dashboard page in Streamlit."""

    # Auto-refresh every 60 seconds. Forces a re-run that will read fresh data
    # from Google Sheets (the cache TTL is 15s so it always gets the latest).
    refresh_count = st_autorefresh(interval=60_000, key="vb_dashboard_autorefresh")

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

        /* === SIDEBAR TOGGLE BUTTONS — gold w/ white arrows in BOTH states === */
        /* Broad coverage: catches the toggle regardless of Streamlit version */

        header[data-testid="stHeader"] button,
        [data-testid="collapsedControl"],
        [data-testid="stSidebarCollapsedControl"],
        [data-testid="stSidebarCollapseButton"],
        button[kind="header"],
        button[kind="headerNoPadding"],
        button[aria-label*="idebar" i],
        button[aria-label*="enu" i]:not(#MainMenu),
        section[data-testid="stSidebar"] button[kind="header"],
        section[data-testid="stSidebar"] [data-testid="stSidebarCollapseButton"] {
            background: #C9982A !important;
            color: #FFFFFF !important;
            border: none !important;
            border-radius: 4px !important;
            box-shadow: 0 2px 10px rgba(0,0,0,0.35) !important;
            visibility: visible !important;
            opacity: 1 !important;
            z-index: 9999 !important;
            padding: 6px 8px !important;
            transition: all 0.15s ease !important;
        }

        header[data-testid="stHeader"] button svg,
        [data-testid="collapsedControl"] svg,
        [data-testid="stSidebarCollapsedControl"] svg,
        [data-testid="stSidebarCollapseButton"] svg,
        button[kind="header"] svg,
        button[kind="headerNoPadding"] svg,
        button[aria-label*="idebar" i] svg,
        section[data-testid="stSidebar"] button[kind="header"] svg,
        section[data-testid="stSidebar"] [data-testid="stSidebarCollapseButton"] svg {
            color: #FFFFFF !important;
            fill: #FFFFFF !important;
            stroke: #FFFFFF !important;
            stroke-width: 2.5 !important;
            width: 18px !important;
            height: 18px !important;
            opacity: 1 !important;
        }

        header[data-testid="stHeader"] button:hover,
        [data-testid="collapsedControl"]:hover,
        [data-testid="stSidebarCollapsedControl"]:hover,
        button[kind="header"]:hover,
        button[kind="headerNoPadding"]:hover {
            background: #A37D1F !important;
            transform: scale(1.08);
        }

        /* But don't style the hamburger menu (#MainMenu is already hidden) */
        #MainMenu, #MainMenu * { background: transparent !important; box-shadow: none !important; }

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
        st.markdown("**Vista**")
        view_mode = st.radio(
            "Vista",
            ["Diario", "Semanal", "Resumen horas"],
            index={
                "Diario": 0, "Semanal": 1, "Resumen horas": 2,
            }.get(st.session_state.get("dashboard_view", "Diario"), 0),
            label_visibility="collapsed",
        )
        st.session_state.dashboard_view = view_mode

        st.markdown("---")
        st.markdown("**Fecha**")
        if view_mode == "Diario":
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
        else:
            st.caption("📅 Mostrando la semana actual (Lunes a Domingo)")

        st.markdown("---")
        if st.button("↻ Actualizar datos", use_container_width=True):
            sheets.get_attendance_for_date.clear()
            sheets.get_employees.clear()
            sheets.get_stores.clear()
            st.rerun()

        st.markdown("---")
        st.caption(f"Sesión: **{current_user['name']}**")
        st.caption(current_user["email"])
        st.markdown("---")
        st.markdown(
            "<div style='font-size:10px;letter-spacing:1.5px;text-transform:uppercase;"
            "color:#1B7340;font-weight:600;margin-bottom:4px;'>"
            "<span style='display:inline-block;width:6px;height:6px;border-radius:50%;"
            "background:#1B7340;margin-right:6px;animation:pulse 2s infinite;'></span>"
            "Auto-refresco activo</div>"
            "<style>@keyframes pulse { 0%,100% { opacity:1; } 50% { opacity:0.3; } }</style>",
            unsafe_allow_html=True,
        )
        st.caption(f"⏱ Cada 1 minuto · Hora GT: **{now_gt().strftime('%H:%M:%S')}**")
        if refresh_count > 0:
            st.caption(f"↻ Actualizaciones automáticas: {refresh_count}")

    # ====== Route by view mode ======
    current_view = st.session_state.get("dashboard_view", "Diario")

    if current_view == "Semanal":
        can_edit = current_user["role"] in ("admin", "manager")
        try:
            render_weekly_view(current_user, can_edit=can_edit)
        except Exception as e:
            st.error(
                "No se pudo cargar la vista semanal.\n\n"
                f"Detalle: `{e}`"
            )
        return

    if current_view == "Resumen horas":
        from .dashboard_hours import render_hours_summary
        try:
            render_hours_summary(current_user)
        except Exception as e:
            st.error(
                "No se pudo cargar el resumen de horas.\n\n"
                f"Detalle: `{e}`"
            )
        return

    # Daily view (default)
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
