"""
Weekly dashboard view (Monday-Sunday) — companion to the daily dashboard.

Renders a grid:
  - rows = active employees (alphabetical)
  - cols = 7 days of current week (L M M J V S D) + Total
  - each cell shows: icon + short store + tooltip with full hours
  - click any cell → popover with editable mini-form for that specific day
  - row totals: days worked, day_off count, absences count
  - column totals: per-store coverage per day
"""

from __future__ import annotations

import datetime as dt
from zoneinfo import ZoneInfo

import streamlit as st

from . import sheets
from .dashboard_html import color_for_name


GT_TZ = ZoneInfo("America/Guatemala")


STATUS_ICONS = {
    "working": "✅",
    "day_off": "💤",
    "permission": "📋",
    "vacation": "🏖️",
    "sick": "🤒",
}

STATUS_LABELS = {
    "working": "Trabajando",
    "day_off": "Día libre",
    "permission": "Permiso",
    "vacation": "Vacaciones",
    "sick": "Enfermo",
}

STATUS_OPTIONS = list(STATUS_ICONS.keys())

DAY_SHORT = ["L", "M", "M", "J", "V", "S", "D"]
DAY_FULL = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"]


def today_gt() -> dt.date:
    return dt.datetime.now(GT_TZ).date()


def _monday_of(d: dt.date) -> dt.date:
    return d - dt.timedelta(days=d.weekday())


def _short_store(name: str) -> str:
    if not name:
        return "?"
    n = name.replace("Tienda ", "").replace("Avenida", "Ave").strip()
    parts = n.split()
    return parts[0] if parts else n


def _time_or_none(t):
    if t is None:
        return None
    if isinstance(t, dt.time):
        return t.strftime("%H:%M")
    return str(t)


def _parse_t(s, fallback):
    if not s:
        return fallback
    try:
        h, m = str(s).split(":")
        return dt.time(int(h), int(m))
    except Exception:
        return fallback


def _fmt_time(s):
    if not s:
        return ""
    try:
        h, m = s.split(":")
        return f"{int(h)}:{m}"
    except Exception:
        return s


def _inject_css():
    st.markdown(
        """
        <style>
        /* Make popover trigger compact and cell-like */
        div[data-testid="stPopover"] > div > button {
            width: 100% !important;
            min-width: 0 !important;
            padding: 8px 6px !important;
            font-size: 11px !important;
            line-height: 1.3 !important;
            background: transparent !important;
            border: 1px solid transparent !important;
            border-radius: 3px !important;
            text-align: center !important;
            color: #0B0F19 !important;
            font-weight: 500 !important;
            white-space: normal !important;
        }
        div[data-testid="stPopover"] > div > button:hover {
            background: #F2F3F5 !important;
            border-color: #D8DCE2 !important;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def _build_week_grid(
    monday: dt.date,
    employees: list[dict],
    stores: list[dict],
    attendance: list[dict],
) -> dict:
    days = [monday + dt.timedelta(days=i) for i in range(7)]
    by_key = {}
    for r in attendance:
        by_key[(r["date"], r["employee_id"])] = r

    employees_sorted = sorted(employees, key=lambda e: e["name"].lower())
    rows = []
    col_totals = [
        {"by_store": {s["id"]: 0 for s in stores}, "absent": 0, "no_record": 0}
        for _ in days
    ]

    for emp in employees_sorted:
        emp_cells = []
        totals = {"worked": 0, "day_off": 0, "absent": 0, "no_record": 0}

        for i, d in enumerate(days):
            rec = by_key.get((d.isoformat(), emp["id"]))
            cell = _build_cell(emp, d, rec, stores)
            emp_cells.append(cell)

            if cell["status"] == "working":
                totals["worked"] += 1
                primary_store = cell.get("worked_store_id") or emp["store_id"]
                if primary_store in col_totals[i]["by_store"]:
                    col_totals[i]["by_store"][primary_store] += 1
            elif cell["status"] == "day_off":
                totals["day_off"] += 1
            elif cell["status"] in ("permission", "vacation", "sick"):
                totals["absent"] += 1
                col_totals[i]["absent"] += 1
            else:
                totals["no_record"] += 1
                col_totals[i]["no_record"] += 1

        rows.append({
            "employee": emp,
            "cells": emp_cells,
            "totals": totals,
        })

    return {"days": days, "rows": rows, "col_totals": col_totals}


def _build_cell(emp: dict, d: dt.date, rec: dict | None, stores: list[dict]) -> dict:
    store_labels = {s["id"]: s["name"] for s in stores}

    if not rec:
        return {
            "date": d.isoformat(),
            "status": "no_record",
            "label": "—",
            "tooltip": "Sin registro",
            "worked_store_id": "",
            "is_support": False,
            "shift_split": False,
            "rec": {},
        }

    status = rec.get("status", "working")
    if status != "working":
        icon = STATUS_ICONS.get(status, "•")
        tooltip = STATUS_LABELS.get(status, status)
        if rec.get("notes"):
            tooltip += f" — {rec['notes']}"
        return {
            "date": d.isoformat(),
            "status": status,
            "label": icon,
            "tooltip": tooltip,
            "worked_store_id": "",
            "is_support": False,
            "shift_split": False,
            "rec": rec,
        }

    s1_store = (rec.get("worked_store_id") or emp["store_id"]).strip()
    s1_store_name = store_labels.get(s1_store, "?")
    s1_short = _short_store(s1_store_name)
    is_support_s1 = (s1_store != emp["store_id"])

    if rec.get("shift_split"):
        s2_store = (rec.get("segment2_store_id") or "").strip()
        s2_store_name = store_labels.get(s2_store, "?")
        s2_short = _short_store(s2_store_name)
        is_support_s2 = bool(s2_store) and (s2_store != emp["store_id"])
        label = f"✅ {s1_short}→{s2_short}"
        tooltip = (
            f"Tramo 1: {_fmt_time(rec.get('shift_start'))}–{_fmt_time(rec.get('shift_end'))} "
            f"en {s1_store_name}  ·  "
            f"Tramo 2: {_fmt_time(rec.get('segment2_start'))}–{_fmt_time(rec.get('segment2_end'))} "
            f"en {s2_store_name}"
        )
        if rec.get("lunch_start"):
            tooltip += f"  ·  Almuerzo: {_fmt_time(rec.get('lunch_start'))}–{_fmt_time(rec.get('lunch_end'))}"
        is_support = is_support_s1 or is_support_s2
    else:
        label = f"✅ {s1_short}"
        tooltip = f"{_fmt_time(rec.get('shift_start'))}–{_fmt_time(rec.get('shift_end'))} en {s1_store_name}"
        if rec.get("lunch_start"):
            tooltip += f" · Almuerzo {_fmt_time(rec.get('lunch_start'))}–{_fmt_time(rec.get('lunch_end'))}"
        is_support = is_support_s1

    if rec.get("is_late"):
        tooltip = f"⚠ Tarde ({_fmt_time(rec.get('actual_start'))}) · " + tooltip
    if (rec.get("overtime_minutes") or 0) > 0:
        tooltip += f" · ⏰ +{rec['overtime_minutes']} min"

    return {
        "date": d.isoformat(),
        "status": "working",
        "label": label,
        "tooltip": tooltip,
        "worked_store_id": s1_store,
        "is_support": is_support,
        "shift_split": bool(rec.get("shift_split")),
        "rec": rec,
    }


def _render_cell_popover(
    emp: dict,
    cell: dict,
    stores: list[dict],
    store_options: list[str],
    store_labels: dict,
    current_user: dict,
    can_edit: bool = True,
):
    eid = emp["id"]
    d_iso = cell["date"]
    label = cell["label"]
    tooltip = cell.get("tooltip", "")

    trigger_label = label
    if cell.get("is_support"):
        trigger_label += " 🔀"

    with st.popover(
        trigger_label,
        use_container_width=True,
        help=tooltip,
    ):
        st.markdown(
            f"<div style='font-size:11px;letter-spacing:2px;text-transform:uppercase;"
            f"color:#0B0F19;font-weight:700;margin-bottom:6px;'>"
            f"{emp['name']} · {d_iso}</div>",
            unsafe_allow_html=True,
        )
        rec = cell.get("rec", {})

        if not can_edit:
            # Read-only view for viewer (Lic.)
            _render_readonly_detail(emp, cell, store_labels)
            return

        prev_status = cell["status"] if cell["status"] != "no_record" else "working"
        _render_edit_form(emp, d_iso, rec, store_options, store_labels,
                          prev_status, current_user)


def _render_readonly_detail(emp: dict, cell: dict, store_labels: dict):
    """Read-only detail view for the popover when can_edit=False."""
    status = cell["status"]
    rec = cell.get("rec", {})

    if status == "no_record":
        st.caption("Sin registro para esta fecha.")
        return

    status_label = STATUS_LABELS.get(status, status)
    icon = STATUS_ICONS.get(status, "•")
    st.markdown(f"**Estado:** {icon} {status_label}")

    if status != "working":
        if rec.get("notes"):
            st.markdown(f"**Nota:** {rec['notes']}")
        return

    # Working details
    s1_store = (rec.get("worked_store_id") or emp["store_id"]).strip()
    s1_name = store_labels.get(s1_store, "?")
    is_support_1 = (s1_store != emp["store_id"])

    if rec.get("shift_split"):
        s2_store = (rec.get("segment2_store_id") or "").strip()
        s2_name = store_labels.get(s2_store, "?")
        is_support_2 = bool(s2_store) and (s2_store != emp["store_id"])
        st.markdown(
            f"**Tramo 1:** {_fmt_time(rec.get('shift_start'))}–"
            f"{_fmt_time(rec.get('shift_end'))} en **{s1_name}**"
            f"{' 🔀 Apoyo' if is_support_1 else ''}"
        )
        st.markdown(
            f"**Tramo 2:** {_fmt_time(rec.get('segment2_start'))}–"
            f"{_fmt_time(rec.get('segment2_end'))} en **{s2_name}**"
            f"{' 🔀 Apoyo' if is_support_2 else ''}"
        )
    else:
        st.markdown(
            f"**Horario:** {_fmt_time(rec.get('shift_start'))}–"
            f"{_fmt_time(rec.get('shift_end'))} en **{s1_name}**"
            f"{' 🔀 Apoyo' if is_support_1 else ''}"
        )

    if rec.get("lunch_start"):
        st.markdown(
            f"**Almuerzo:** {_fmt_time(rec.get('lunch_start'))}–"
            f"{_fmt_time(rec.get('lunch_end'))}"
        )
    if rec.get("is_late"):
        st.markdown(
            f"⚠ **Llegada tarde** a las {_fmt_time(rec.get('actual_start'))}"
        )
    if (rec.get("overtime_minutes") or 0) > 0:
        st.markdown(f"⏰ **Hora extra:** {rec['overtime_minutes']} minutos")
    if rec.get("notes"):
        st.markdown(f"**Notas:** {rec['notes']}")


def _render_edit_form(
    emp: dict,
    d_iso: str,
    rec: dict,
    store_options: list[str],
    store_labels: dict,
    prev_status: str,
    current_user: dict,
):
    eid = emp["id"]
    dk = d_iso

    status_choice = st.radio(
        "Estado del día",
        STATUS_OPTIONS,
        format_func=lambda k: f"{STATUS_ICONS[k]} {STATUS_LABELS[k]}",
        index=STATUS_OPTIONS.index(prev_status) if prev_status in STATUS_OPTIONS else 0,
        horizontal=False,
        key=f"wk_status_{eid}_{dk}",
    )

    record = {
        "date": d_iso,
        "employee_id": eid,
        "status": status_choice,
        "shift_start": None,
        "shift_end": None,
        "lunch_start": None,
        "lunch_end": None,
        "overtime_minutes": 0,
        "is_late": False,
        "actual_start": None,
        "notes": "",
        "worked_store_id": "",
        "shift_split": False,
        "segment2_store_id": "",
        "segment2_start": "",
        "segment2_end": "",
    }

    if status_choice == "working":
        default_store = (rec.get("worked_store_id") or emp["store_id"])
        if default_store not in store_options:
            default_store = emp["store_id"]
        s1_store_idx = store_options.index(default_store)

        shift_split = st.toggle(
            "🔀 Trabajo dividido en 2 tiendas",
            value=bool(rec.get("shift_split")),
            key=f"wk_split_{eid}_{dk}",
        )
        record["shift_split"] = shift_split

        d_ss = dt.time(9, 0)
        d_se = dt.time(19, 0)
        d_ls = dt.time(13, 0)
        d_le = dt.time(14, 0)

        if shift_split:
            st.markdown(
                "<div style='font-size:10px;letter-spacing:1.5px;text-transform:uppercase;"
                "color:#C9982A;font-weight:700;margin-top:8px;'>TRAMO 1</div>",
                unsafe_allow_html=True,
            )
            chosen_store_1 = st.selectbox(
                "Tienda — Tramo 1",
                store_options,
                format_func=lambda x: store_labels[x],
                index=s1_store_idx,
                key=f"wk_store_{eid}_{dk}",
            )
            c1 = st.columns(2)
            ss_t = c1[0].time_input(
                "Entrada",
                value=_parse_t(rec.get("shift_start"), d_ss),
                key=f"wk_ss_{eid}_{dk}", step=1800,
            )
            se_t = c1[1].time_input(
                "Salida",
                value=_parse_t(rec.get("shift_end"), d_se),
                key=f"wk_se_{eid}_{dk}", step=1800,
            )

            st.markdown(
                "<div style='font-size:10px;letter-spacing:1.5px;text-transform:uppercase;"
                "color:#C9982A;font-weight:700;margin-top:8px;'>TRAMO 2</div>",
                unsafe_allow_html=True,
            )
            other_store = next(
                (s for s in store_options if s != chosen_store_1), store_options[0]
            )
            prev_seg2 = rec.get("segment2_store_id") or other_store
            if prev_seg2 not in store_options:
                prev_seg2 = other_store
            s2_idx = store_options.index(prev_seg2)
            chosen_store_2 = st.selectbox(
                "Tienda — Tramo 2",
                store_options,
                format_func=lambda x: store_labels[x],
                index=s2_idx,
                key=f"wk_store2_{eid}_{dk}",
            )
            c2 = st.columns(2)
            s2s_t = c2[0].time_input(
                "Entrada — Tramo 2",
                value=_parse_t(rec.get("segment2_start"), dt.time(14, 0)),
                key=f"wk_s2s_{eid}_{dk}", step=1800,
            )
            s2e_t = c2[1].time_input(
                "Salida — Tramo 2",
                value=_parse_t(rec.get("segment2_end"), d_se),
                key=f"wk_s2e_{eid}_{dk}", step=1800,
            )
            record["worked_store_id"] = chosen_store_1
            record["segment2_store_id"] = chosen_store_2
            record["segment2_start"] = _time_or_none(s2s_t)
            record["segment2_end"] = _time_or_none(s2e_t)
        else:
            chosen_store = st.selectbox(
                "🏪 Tienda donde trabajará",
                store_options,
                format_func=lambda x: store_labels[x],
                index=s1_store_idx,
                key=f"wk_store_{eid}_{dk}",
            )
            c = st.columns(2)
            ss_t = c[0].time_input(
                "Entrada",
                value=_parse_t(rec.get("shift_start"), d_ss),
                key=f"wk_ss_{eid}_{dk}", step=1800,
            )
            se_t = c[1].time_input(
                "Salida",
                value=_parse_t(rec.get("shift_end"), d_se),
                key=f"wk_se_{eid}_{dk}", step=1800,
            )
            record["worked_store_id"] = chosen_store

        cL = st.columns(2)
        ls_t = cL[0].time_input(
            "🍽 Almuerzo desde",
            value=_parse_t(rec.get("lunch_start"), d_ls),
            key=f"wk_ls_{eid}_{dk}", step=1800,
        )
        le_t = cL[1].time_input(
            "🍽 Almuerzo hasta",
            value=_parse_t(rec.get("lunch_end"), d_le),
            key=f"wk_le_{eid}_{dk}", step=1800,
        )

        cX = st.columns([1, 1])
        ot = cX[0].number_input(
            "⏰ Hora extra (min)", min_value=0, max_value=600, step=15,
            value=int(rec.get("overtime_minutes") or 0),
            key=f"wk_ot_{eid}_{dk}",
        )
        is_late = cX[1].checkbox(
            "Llegada tarde",
            value=bool(rec.get("is_late", False)),
            key=f"wk_late_{eid}_{dk}",
        )
        actual_start_t = None
        if is_late:
            actual_start_t = st.time_input(
                "Hora real de llegada",
                value=_parse_t(rec.get("actual_start"), ss_t),
                key=f"wk_actstart_{eid}_{dk}", step=900,
            )

        notes_val = st.text_input(
            "📝 Notas (opcional)",
            value=rec.get("notes", ""),
            key=f"wk_notes_w_{eid}_{dk}",
        )

        record.update({
            "shift_start": _time_or_none(ss_t),
            "shift_end": _time_or_none(se_t),
            "lunch_start": _time_or_none(ls_t),
            "lunch_end": _time_or_none(le_t),
            "overtime_minutes": int(ot),
            "is_late": bool(is_late),
            "actual_start": _time_or_none(actual_start_t) if is_late else None,
            "notes": notes_val,
        })
    else:
        record["notes"] = st.text_input(
            "📝 Motivo / Nota",
            value=rec.get("notes", ""),
            key=f"wk_notes_a_{eid}_{dk}",
        )
        record["worked_store_id"] = rec.get("worked_store_id", "") or ""

    if st.button(
        "💾 Guardar este día",
        key=f"wk_save_{eid}_{dk}",
        type="primary",
        use_container_width=True,
    ):
        try:
            sheets.upsert_attendance(record, updated_by=current_user["email"])
            sheets.get_attendance_for_date.clear()
            sheets.get_attendance_for_range.clear()
            st.success("✓ Guardado")
            st.rerun()
        except Exception as e:
            st.error(f"Error: `{e}`")


def _render_grid(
    grid: dict,
    stores: list[dict],
    store_options: list[str],
    store_labels: dict,
    current_user: dict,
    can_edit: bool = True,
):
    days = grid["days"]
    today_iso = today_gt().isoformat()

    # === HEADER ROW ===
    header_cols = st.columns([2.2] + [1] * 7 + [1.3])
    header_cols[0].markdown(
        "<div style='font-size:10px;letter-spacing:2px;text-transform:uppercase;"
        "color:#6C7280;font-weight:700;padding:6px 4px;'>EMPLEADO</div>",
        unsafe_allow_html=True,
    )
    for i, d in enumerate(days):
        is_today = (d.isoformat() == today_iso)
        bg = "#C9982A" if is_today else "transparent"
        color = "#FFFFFF" if is_today else "#6C7280"
        header_cols[i + 1].markdown(
            f"<div style='text-align:center;background:{bg};color:{color};"
            f"border-radius:3px;font-size:10px;letter-spacing:1.5px;font-weight:700;"
            f"padding:6px 2px;'>"
            f"<div>{DAY_SHORT[i]}</div>"
            f"<div style='font-size:9px;opacity:0.8;'>{d.day}</div></div>",
            unsafe_allow_html=True,
        )
    header_cols[8].markdown(
        "<div style='text-align:center;font-size:10px;letter-spacing:2px;text-transform:uppercase;"
        "color:#6C7280;font-weight:700;padding:6px 4px;'>TOTAL</div>",
        unsafe_allow_html=True,
    )

    st.markdown(
        "<hr style='margin:6px 0 10px;border:none;border-top:1px solid #D8DCE2;'>",
        unsafe_allow_html=True,
    )

    # === EMPLOYEE ROWS ===
    for row in grid["rows"]:
        emp = row["employee"]
        cells = row["cells"]
        totals = row["totals"]

        cols = st.columns([2.2] + [1] * 7 + [1.3])

        initials = "".join([p[0] for p in emp["name"].split()[:2]]).upper() or "?"
        fg, bg = color_for_name(emp["name"])
        home_short = _short_store(store_labels.get(emp["store_id"], "?"))
        cols[0].markdown(
            f"<div style='display:flex;align-items:center;gap:8px;padding:6px 4px;'>"
            f"<div style='width:28px;height:28px;border-radius:50%;background:{bg};"
            f"color:{fg};display:grid;place-items:center;font-weight:700;font-size:10.5px;"
            f"font-family:Geist Mono,monospace;flex-shrink:0;'>{initials}</div>"
            f"<div><div style='font-weight:600;font-size:12.5px;color:#0B0F19;'>{emp['name']}</div>"
            f"<div style='font-size:9.5px;color:#9CA3AF;letter-spacing:0.5px;'>"
            f"habitual: {home_short}</div></div></div>",
            unsafe_allow_html=True,
        )

        for i, cell in enumerate(cells):
            with cols[i + 1]:
                _render_cell_popover(
                    emp, cell, stores, store_options, store_labels,
                    current_user, can_edit=can_edit,
                )

        if totals["worked"] > 0 or totals["day_off"] > 0 or totals["absent"] > 0:
            parts = []
            if totals["worked"]:
                parts.append(f"✅{totals['worked']}")
            if totals["day_off"]:
                parts.append(f"💤{totals['day_off']}")
            if totals["absent"]:
                parts.append(f"📋{totals['absent']}")
            cols[8].markdown(
                f"<div style='text-align:center;font-size:11px;color:#3D4554;padding:8px 4px;"
                f"font-family:Geist Mono,monospace;'>{' '.join(parts)}</div>",
                unsafe_allow_html=True,
            )
        else:
            cols[8].markdown(
                "<div style='text-align:center;font-size:10px;color:#9CA3AF;padding:8px 4px;"
                "font-style:italic;'>—</div>",
                unsafe_allow_html=True,
            )

    # === FOOTER: PER-COLUMN TOTALS BY STORE ===
    st.markdown(
        "<hr style='margin:12px 0 6px;border:none;border-top:2px solid #D8DCE2;'>",
        unsafe_allow_html=True,
    )

    for store in stores:
        sid = store["id"]
        sname_short = _short_store(store["name"])
        foot_cols = st.columns([2.2] + [1] * 7 + [1.3])
        foot_cols[0].markdown(
            f"<div style='font-size:10px;letter-spacing:2px;text-transform:uppercase;"
            f"color:#0B0F19;font-weight:700;padding:6px 4px;'>"
            f"Total · {sname_short}</div>",
            unsafe_allow_html=True,
        )
        for i, ct in enumerate(grid["col_totals"]):
            cnt = ct["by_store"].get(sid, 0)
            color = "#0B0F19" if cnt > 0 else "#9CA3AF"
            foot_cols[i + 1].markdown(
                f"<div style='text-align:center;font-family:Geist Mono,monospace;"
                f"font-size:13px;font-weight:700;color:{color};padding:4px 0;'>{cnt}</div>",
                unsafe_allow_html=True,
            )
        week_total = sum(ct["by_store"].get(sid, 0) for ct in grid["col_totals"])
        foot_cols[8].markdown(
            f"<div style='text-align:center;font-family:Geist Mono,monospace;"
            f"font-size:13px;font-weight:700;color:#C9982A;padding:4px 0;'>"
            f"{week_total} d/p</div>",
            unsafe_allow_html=True,
        )

    foot_cols = st.columns([2.2] + [1] * 7 + [1.3])
    foot_cols[0].markdown(
        "<div style='font-size:10px;letter-spacing:2px;text-transform:uppercase;"
        "color:#B42318;font-weight:700;padding:6px 4px;'>"
        "Ausencias</div>",
        unsafe_allow_html=True,
    )
    for i, ct in enumerate(grid["col_totals"]):
        cnt = ct["absent"]
        color = "#B42318" if cnt > 0 else "#9CA3AF"
        foot_cols[i + 1].markdown(
            f"<div style='text-align:center;font-family:Geist Mono,monospace;"
            f"font-size:12px;font-weight:700;color:{color};padding:4px 0;'>{cnt}</div>",
            unsafe_allow_html=True,
        )
    foot_cols[8].markdown("<div></div>", unsafe_allow_html=True)


def render_weekly_view(current_user: dict, can_edit: bool = True):
    _inject_css()

    today = today_gt()
    monday = _monday_of(today)
    sunday = monday + dt.timedelta(days=6)

    SPANISH_MONTHS_SHORT = [
        "ene", "feb", "mar", "abr", "may", "jun",
        "jul", "ago", "sep", "oct", "nov", "dic",
    ]
    if monday.month == sunday.month:
        range_label = f"{monday.day} – {sunday.day} {SPANISH_MONTHS_SHORT[sunday.month - 1]} {sunday.year}"
    else:
        range_label = (
            f"{monday.day} {SPANISH_MONTHS_SHORT[monday.month - 1]} – "
            f"{sunday.day} {SPANISH_MONTHS_SHORT[sunday.month - 1]} {sunday.year}"
        )

    edit_hint = (
        "Click en cualquier celda para editar."
        if can_edit
        else "Click en cualquier celda para ver detalles."
    )

    st.markdown(
        f"<div style='display:flex;justify-content:space-between;align-items:center;"
        f"margin:6px 0 14px;flex-wrap:wrap;gap:8px;'>"
        f"<div>"
        f"<div style='font-size:11px;letter-spacing:2.5px;text-transform:uppercase;"
        f"color:#C9982A;font-weight:600;'>VISTA SEMANAL · LUNES A DOMINGO</div>"
        f"<div style='font-size:18px;font-weight:600;color:#0B0F19;'>"
        f"{range_label}</div></div>"
        f"<div style='font-size:11px;color:#6C7280;text-align:right;'>"
        f"{edit_hint}<br>"
        f"<span style='color:#C9982A;'>●</span> hoy resaltado en gold</div>"
        f"</div>",
        unsafe_allow_html=True,
    )

    try:
        employees = sheets.get_employees()
        stores = sheets.get_stores()
        attendance = sheets.get_attendance_for_range(
            monday.isoformat(), sunday.isoformat()
        )
    except Exception as e:
        st.error(f"No se pudieron cargar datos: `{e}`")
        return

    if not employees:
        st.info("No hay empleados activos.")
        return

    if not stores:
        st.warning("No hay tiendas configuradas.")
        return

    store_options = [s["id"] for s in stores]
    store_labels = {s["id"]: s["name"] for s in stores}

    grid = _build_week_grid(monday, employees, stores, attendance)
    _render_grid(grid, stores, store_options, store_labels, current_user, can_edit)
