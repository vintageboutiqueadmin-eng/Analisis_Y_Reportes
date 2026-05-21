"""
Hours summary view — tabular metrics per employee.

Renders two synchronized panels:
  - Weekly summary (Mon-Sun): hours worked per employee per store
  - Daily breakdown: detail for any selected day

Metrics shown per employee:
  - Worked hours (net = total time minus lunch)
  - Overtime minutes
  - Hours per store (split when shift_split)
  - Days worked / days off / absences

Net hours = (end - start) - (lunch_end - lunch_start)
            + segment2_end - segment2_start  (for split shifts)
            + overtime_minutes

Lunch is assumed to fall within ONE of the segments (per app convention).
"""

from __future__ import annotations

import datetime as dt
from zoneinfo import ZoneInfo

import streamlit as st

from . import sheets
from .dashboard_html import color_for_name


GT_TZ = ZoneInfo("America/Guatemala")

DAY_SHORT = ["L", "M", "M", "J", "V", "S", "D"]
DAY_FULL = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"]
SPANISH_MONTHS = [
    "enero", "febrero", "marzo", "abril", "mayo", "junio",
    "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre",
]


def _today_gt() -> dt.date:
    return dt.datetime.now(GT_TZ).date()


def _monday_of(d: dt.date) -> dt.date:
    return d - dt.timedelta(days=d.weekday())


def _parse_hhmm_to_minutes(s) -> int | None:
    if not s:
        return None
    try:
        h, m = str(s).split(":")
        return int(h) * 60 + int(m)
    except Exception:
        return None


def _fmt_hours(minutes: int) -> str:
    """Format minutes as 'Xh Ym' or 'Xh' or '—' for zero."""
    if minutes <= 0:
        return "—"
    h = minutes // 60
    m = minutes % 60
    if m == 0:
        return f"{h}h"
    return f"{h}h {m}m"


def _fmt_hours_decimal(minutes: int) -> str:
    """Format minutes as decimal hours like '9.5h'."""
    if minutes <= 0:
        return "0h"
    return f"{minutes / 60:.1f}h"


def _short_store(name: str) -> str:
    """Compact store labels: 'Tienda 6ta Avenida' → '6ta', '7ma Avenida' → '7ma'."""
    if not name:
        return "?"
    n = name.replace("Tienda ", "").replace("Avenida", "").strip()
    parts = n.split()
    return parts[0] if parts else n


def _compute_record_hours(rec: dict) -> dict:
    """
    Compute hours for a single attendance record, broken down by store.
    Returns:
      {
        "net_minutes_by_store": {store_id: minutes, ...},  # only worked time, lunch removed
        "overtime_minutes": int,
        "total_net_minutes": int,  # sum across stores
        "status": str,
      }
    """
    status = rec.get("status", "working")
    overtime = int(rec.get("overtime_minutes") or 0)

    result = {
        "net_minutes_by_store": {},
        "overtime_minutes": overtime,
        "total_net_minutes": 0,
        "status": status,
    }

    if status != "working":
        return result

    s1_store = rec.get("worked_store_id") or ""
    ss1 = _parse_hhmm_to_minutes(rec.get("shift_start"))
    se1 = _parse_hhmm_to_minutes(rec.get("shift_end"))
    ls = _parse_hhmm_to_minutes(rec.get("lunch_start"))
    le = _parse_hhmm_to_minutes(rec.get("lunch_end"))

    seg1_minutes = 0
    if ss1 is not None and se1 is not None and se1 > ss1:
        seg1_minutes = se1 - ss1

    seg2_minutes = 0
    s2_store = (rec.get("segment2_store_id") or "").strip()
    if rec.get("shift_split") and s2_store:
        s2s = _parse_hhmm_to_minutes(rec.get("segment2_start"))
        s2e = _parse_hhmm_to_minutes(rec.get("segment2_end"))
        if s2s is not None and s2e is not None and s2e > s2s:
            seg2_minutes = s2e - s2s

    # Subtract lunch from whichever segment contains it. If we can't tell, subtract
    # from segment 1 (most common case).
    lunch_minutes = 0
    if ls is not None and le is not None and le > ls:
        lunch_minutes = le - ls
        # Try to detect which segment contains the lunch
        if seg2_minutes > 0:
            s2s = _parse_hhmm_to_minutes(rec.get("segment2_start"))
            s2e = _parse_hhmm_to_minutes(rec.get("segment2_end"))
            if s2s is not None and ls >= s2s and le <= s2e:
                seg2_minutes -= lunch_minutes
            else:
                seg1_minutes -= lunch_minutes
        else:
            seg1_minutes -= lunch_minutes

    seg1_minutes = max(0, seg1_minutes)
    seg2_minutes = max(0, seg2_minutes)

    if seg1_minutes > 0 and s1_store:
        result["net_minutes_by_store"][s1_store] = (
            result["net_minutes_by_store"].get(s1_store, 0) + seg1_minutes
        )
    if seg2_minutes > 0 and s2_store:
        result["net_minutes_by_store"][s2_store] = (
            result["net_minutes_by_store"].get(s2_store, 0) + seg2_minutes
        )

    result["total_net_minutes"] = seg1_minutes + seg2_minutes
    return result


def _build_weekly_summary(
    monday: dt.date,
    employees: list[dict],
    stores: list[dict],
    attendance: list[dict],
) -> dict:
    """
    Build the weekly summary data structure.
    Returns:
      {
        "days": [date1, ..., date7],
        "rows": [
          {
            "employee": emp_dict,
            "per_day": [day_dict, ...],
            "totals": {
              "net_minutes_by_store": {sid: minutes, ...},
              "total_net_minutes": int,
              "overtime_minutes": int,
              "days_worked": int,
              "days_off": int,
              "absences": int,    # permission + vacation + sick
              "no_record": int,
            },
          }, ...
        ],
      }
    """
    days = [monday + dt.timedelta(days=i) for i in range(7)]
    by_key = {(r["date"], r["employee_id"]): r for r in attendance}

    employees_sorted = sorted(employees, key=lambda e: e["name"].lower())
    rows = []

    for emp in employees_sorted:
        per_day = []
        totals = {
            "net_minutes_by_store": {},
            "total_net_minutes": 0,
            "overtime_minutes": 0,
            "days_worked": 0,
            "days_off": 0,
            "absences": 0,
            "no_record": 0,
        }

        for d in days:
            rec = by_key.get((d.isoformat(), emp["id"]))
            if not rec:
                per_day.append({"status": "no_record", "rec": None, "hours": None})
                totals["no_record"] += 1
                continue

            status = rec.get("status", "working")
            hours = _compute_record_hours(rec)
            per_day.append({"status": status, "rec": rec, "hours": hours})

            if status == "working":
                totals["days_worked"] += 1
                totals["total_net_minutes"] += hours["total_net_minutes"]
                totals["overtime_minutes"] += hours["overtime_minutes"]
                for sid, mins in hours["net_minutes_by_store"].items():
                    totals["net_minutes_by_store"][sid] = (
                        totals["net_minutes_by_store"].get(sid, 0) + mins
                    )
            elif status == "day_off":
                totals["days_off"] += 1
            elif status in ("permission", "vacation", "sick"):
                totals["absences"] += 1

        rows.append({
            "employee": emp,
            "per_day": per_day,
            "totals": totals,
        })

    return {"days": days, "rows": rows}


def _format_spanish_date(d: dt.date) -> str:
    return f"{DAY_FULL[d.weekday()]} {d.day} de {SPANISH_MONTHS[d.month - 1]} {d.year}"


def _inject_css():
    st.markdown(
        """
        <style>
        @import url('https://fonts.googleapis.com/css2?family=Geist:wght@300;400;500;600;700&family=Geist+Mono:wght@400;500;600&display=swap');
        html, body, [class*="css"], button, input, select, textarea {
            font-family: 'Geist', system-ui, sans-serif !important;
        }
        .block-container { padding-top: 1.5rem !important; max-width: 1400px !important; }

        .hs-header {
            background: #0B0F19; color: #F9FAFB; padding: 18px 26px;
            border-radius: 6px; margin-bottom: 18px;
            display: flex; justify-content: space-between; align-items: center;
        }
        .hs-header .ttl { font-size: 19px; font-weight: 600; letter-spacing: -0.2px; }
        .hs-header .sub {
            font-size: 10px; letter-spacing: 2.5px; text-transform: uppercase;
            color: #C9982A; font-weight: 600; margin-bottom: 3px;
        }

        .hs-kpi-grid {
            display: grid; grid-template-columns: repeat(4, 1fr); gap: 14px;
            margin-bottom: 22px;
        }
        .hs-kpi {
            background: #FFFFFF; border: 1px solid #D8DCE2; border-radius: 6px;
            padding: 16px 18px;
        }
        .hs-kpi-label {
            font-size: 9.5px; letter-spacing: 2px; text-transform: uppercase;
            color: #6C7280; font-weight: 600; margin-bottom: 6px;
        }
        .hs-kpi-value {
            font-size: 22px; font-weight: 600; color: #0B0F19;
            letter-spacing: -0.3px; font-family: 'Geist Mono', monospace;
        }
        .hs-kpi-detail {
            font-size: 10.5px; color: #6C7280; margin-top: 4px;
        }

        .hs-section-label {
            font-size: 11px; letter-spacing: 2px; text-transform: uppercase;
            color: #0B0F19; font-weight: 700; margin: 24px 0 10px;
        }

        /* Compact table for the weekly summary */
        .hs-table-wrap {
            background: #FFFFFF; border: 1px solid #D8DCE2; border-radius: 6px;
            overflow: hidden;
        }
        .hs-row {
            display: grid;
            grid-template-columns: 200px repeat(7, 1fr) 90px 110px;
            border-bottom: 1px solid #EBEEF2;
            font-size: 12px; color: #3D4554;
            align-items: center;
        }
        .hs-row:last-child { border-bottom: none; }
        .hs-row.hs-head {
            background: #0B0F19; color: #F9FAFB;
            font-family: 'Geist Mono', monospace; font-size: 10px;
            letter-spacing: 1.8px; font-weight: 600; text-transform: uppercase;
        }
        .hs-row.hs-head > div {
            padding: 10px 6px; text-align: center;
            border-right: 1px solid #1F2937;
        }
        .hs-row.hs-head > div:first-child {
            text-align: left; padding-left: 16px;
        }
        .hs-row.hs-head > div:last-child { border-right: none; }
        .hs-row.hs-head .today-col {
            background: #C9982A; color: #FFFFFF;
        }
        .hs-row > div {
            padding: 10px 6px; border-right: 1px solid #EBEEF2;
            text-align: center; font-family: 'Geist Mono', monospace;
        }
        .hs-row > div:first-child {
            text-align: left; padding-left: 16px;
            font-family: 'Geist', system-ui, sans-serif;
        }
        .hs-row > div:last-child { border-right: none; }

        .hs-emp-info {
            display: flex; align-items: center; gap: 10px;
        }
        .hs-avatar {
            width: 30px; height: 30px; border-radius: 50%;
            display: grid; place-items: center; font-weight: 700; font-size: 10.5px;
            font-family: 'Geist Mono', monospace; flex-shrink: 0;
        }
        .hs-emp-name {
            font-weight: 600; font-size: 12.5px; color: #0B0F19;
            line-height: 1.2;
        }
        .hs-emp-home {
            font-size: 9.5px; color: #9CA3AF; letter-spacing: 0.5px;
            margin-top: 1px;
        }

        .hs-cell-empty { color: #9CA3AF; font-style: italic; }
        .hs-cell-worked { color: #1B7340; font-weight: 600; }
        .hs-cell-off { color: #6C7280; }
        .hs-cell-absent { color: #B91C1C; }
        .hs-cell-detail {
            font-size: 9px; color: #9CA3AF; font-family: 'Geist Mono', monospace;
            margin-top: 1px;
        }
        .hs-cell-support {
            display: inline-block; margin-left: 3px; padding: 0 4px;
            background: #FFEDD5; color: #9A3412; font-size: 8px;
            font-weight: 700; letter-spacing: 0.8px; border-radius: 2px;
        }

        .hs-row.hs-total-row {
            background: #F6F7F9; font-weight: 700;
            border-top: 2px solid #D8DCE2; border-bottom: none;
        }
        .hs-row.hs-total-row .hs-cell-worked { color: #0B0F19; }

        .hs-store-row {
            display: grid;
            grid-template-columns: 200px repeat(7, 1fr) 90px 110px;
            border-bottom: 1px solid #EBEEF2;
            font-size: 10.5px;
        }
        .hs-store-row > div {
            padding: 6px 6px; border-right: 1px solid #EBEEF2;
            text-align: center; font-family: 'Geist Mono', monospace;
            color: #6C7280;
        }
        .hs-store-row > div:first-child {
            text-align: left; padding-left: 16px;
            font-family: 'Geist', system-ui, sans-serif;
            font-weight: 600; color: #0B0F19; font-size: 10px;
            letter-spacing: 1.5px; text-transform: uppercase;
        }
        .hs-store-row > div:last-child { border-right: none; }

        .hs-extras {
            display: flex; gap: 18px; flex-wrap: wrap; justify-content: center;
            font-size: 10px; color: #6C7280;
            font-family: 'Geist Mono', monospace;
        }
        .hs-extras strong { color: #0B0F19; }

        /* Daily detail panel */
        .hs-daily-panel {
            background: #FFFFFF; border: 1px solid #D8DCE2; border-radius: 6px;
            padding: 20px 24px; margin-bottom: 18px;
        }
        .hs-daily-title {
            font-size: 14px; font-weight: 600; color: #0B0F19;
            margin-bottom: 14px; letter-spacing: -0.2px;
        }
        .hs-daily-list { margin: 0; padding: 0; list-style: none; }
        .hs-daily-list li {
            display: flex; align-items: center; gap: 12px;
            padding: 10px 0; border-bottom: 1px solid #EBEEF2;
            font-size: 12.5px;
        }
        .hs-daily-list li:last-child { border-bottom: none; }
        .hs-daily-list .dl-name { flex: 1; font-weight: 600; color: #0B0F19; }
        .hs-daily-list .dl-store { color: #6C7280; font-size: 11px; }
        .hs-daily-list .dl-hours {
            font-family: 'Geist Mono', monospace; font-weight: 600;
            color: #1B7340; min-width: 60px; text-align: right;
        }
        .hs-daily-list .dl-off { color: #9CA3AF; font-style: italic; }
        </style>
        """,
        unsafe_allow_html=True,
    )


def _render_weekly_table(summary: dict, stores: list[dict], today_iso: str):
    days = summary["days"]
    rows = summary["rows"]
    store_labels = {s["id"]: s["name"] for s in stores}

    # ===== HEADER =====
    header_cells = []
    for i, d in enumerate(days):
        is_today = (d.isoformat() == today_iso)
        cls = "today-col" if is_today else ""
        header_cells.append(
            f'<div class="{cls}">{DAY_SHORT[i]} {d.day}</div>'
        )

    html = (
        '<div class="hs-table-wrap">'
        '<div class="hs-row hs-head">'
        '<div>Empleado</div>'
        + "".join(header_cells)
        + '<div>Sem.</div>'
        + '<div>Extras</div>'
        + '</div>'
    )

    # ===== EMPLOYEE ROWS =====
    for row in rows:
        emp = row["employee"]
        per_day = row["per_day"]
        totals = row["totals"]

        initials = "".join([p[0] for p in emp["name"].split()[:2]]).upper() or "?"
        fg, bg = color_for_name(emp["name"])
        home_short = _short_store(store_labels.get(emp["store_id"], "?"))

        # First column: avatar + name + home store
        emp_cell = (
            f'<div><div class="hs-emp-info">'
            f'<div class="hs-avatar" style="background:{bg};color:{fg};">{initials}</div>'
            f'<div><div class="hs-emp-name">{emp["name"]}</div>'
            f'<div class="hs-emp-home">{home_short}</div></div>'
            f'</div></div>'
        )

        # 7 day cells: hours + status icon
        day_cells = []
        for day_idx, dd in enumerate(per_day):
            status = dd["status"]
            if status == "no_record":
                day_cells.append('<div class="hs-cell-empty">—</div>')
                continue
            if status == "working":
                mins = dd["hours"]["total_net_minutes"]
                stores_in_day = dd["hours"]["net_minutes_by_store"]
                emp_home = emp["store_id"]
                # Build detail: stores worked
                store_parts = []
                support_in_day = False
                for sid, m in stores_in_day.items():
                    s_short = _short_store(store_labels.get(sid, "?"))
                    if sid != emp_home:
                        support_in_day = True
                    if len(stores_in_day) > 1:
                        store_parts.append(f"{s_short} {_fmt_hours_decimal(m)}")
                    else:
                        store_parts.append(s_short)
                detail = " · ".join(store_parts)
                support_html = (
                    '<span class="hs-cell-support">🔀</span>' if support_in_day else ''
                )
                day_cells.append(
                    f'<div><div class="hs-cell-worked">'
                    f'{_fmt_hours_decimal(mins)}{support_html}</div>'
                    f'<div class="hs-cell-detail">{detail}</div></div>'
                )
            elif status == "day_off":
                day_cells.append('<div><span class="hs-cell-off">💤</span></div>')
            elif status == "permission":
                day_cells.append('<div><span class="hs-cell-absent">📋</span></div>')
            elif status == "vacation":
                day_cells.append('<div><span class="hs-cell-absent">🏖️</span></div>')
            elif status == "sick":
                day_cells.append('<div><span class="hs-cell-absent">🤒</span></div>')
            else:
                day_cells.append('<div class="hs-cell-empty">—</div>')

        # Total cell
        total_str = _fmt_hours_decimal(totals["total_net_minutes"])
        total_cell = f'<div class="hs-cell-worked">{total_str}</div>'

        # Extras cell
        days_w = totals["days_worked"]
        ot = totals["overtime_minutes"]
        extras_parts = [f"{days_w}d"]
        if ot > 0:
            extras_parts.append(f"+{ot}m")
        if totals["days_off"] > 0:
            extras_parts.append(f"💤{totals['days_off']}")
        if totals["absences"] > 0:
            extras_parts.append(f"📋{totals['absences']}")
        extras_cell = f'<div><div class="hs-extras">{" · ".join(extras_parts)}</div></div>'

        html += (
            '<div class="hs-row">'
            + emp_cell
            + "".join(day_cells)
            + total_cell
            + extras_cell
            + '</div>'
        )

    # ===== PER-STORE TOTAL ROWS =====
    for store in stores:
        sid = store["id"]
        sname_short = _short_store(store["name"])

        # First column: store label
        store_cells = [f'<div>Total · {sname_short}</div>']

        # Sum minutes per day at this store across all employees
        for i, d in enumerate(summary["days"]):
            day_total_at_store = 0
            for row in rows:
                if row["per_day"][i]["status"] == "working":
                    day_total_at_store += row["per_day"][i]["hours"]["net_minutes_by_store"].get(sid, 0)
            if day_total_at_store > 0:
                store_cells.append(f'<div>{_fmt_hours_decimal(day_total_at_store)}</div>')
            else:
                store_cells.append('<div>—</div>')

        # Week total for this store
        week_total = sum(
            row["totals"]["net_minutes_by_store"].get(sid, 0)
            for row in rows
        )
        store_cells.append(
            f'<div style="color:#C9982A;font-weight:700;">{_fmt_hours_decimal(week_total)}</div>'
        )
        store_cells.append('<div>—</div>')

        html += '<div class="hs-store-row">' + "".join(store_cells) + '</div>'

    html += '</div>'  # close hs-table-wrap

    st.markdown(html, unsafe_allow_html=True)


def _render_daily_panel(
    selected_date: dt.date,
    employees: list[dict],
    stores: list[dict],
    attendance: list[dict],
):
    store_labels = {s["id"]: s["name"] for s in stores}
    by_key = {(r["date"], r["employee_id"]): r for r in attendance}
    employees_sorted = sorted(employees, key=lambda e: e["name"].lower())

    # Gather per-employee data for the selected date
    day_iso = selected_date.isoformat()
    working_list = []
    off_list = []
    absent_list = []
    no_record_count = 0

    day_total_minutes = 0
    day_total_overtime = 0
    day_totals_by_store = {s["id"]: 0 for s in stores}

    for emp in employees_sorted:
        rec = by_key.get((day_iso, emp["id"]))
        if not rec:
            no_record_count += 1
            continue
        status = rec.get("status", "working")
        if status == "working":
            hours = _compute_record_hours(rec)
            day_total_minutes += hours["total_net_minutes"]
            day_total_overtime += hours["overtime_minutes"]
            for sid, m in hours["net_minutes_by_store"].items():
                if sid in day_totals_by_store:
                    day_totals_by_store[sid] += m
            working_list.append({
                "emp": emp, "rec": rec, "hours": hours,
            })
        elif status == "day_off":
            off_list.append({"emp": emp, "rec": rec})
        elif status in ("permission", "vacation", "sick"):
            absent_list.append({"emp": emp, "rec": rec, "status": status})

    # KPI summary at top
    kpis_html = (
        f'<div class="hs-kpi-grid">'
        f'<div class="hs-kpi">'
        f'<div class="hs-kpi-label">Total horas del día</div>'
        f'<div class="hs-kpi-value">{_fmt_hours_decimal(day_total_minutes)}</div>'
        f'<div class="hs-kpi-detail">{len(working_list)} empleado(s) activo(s)</div>'
        f'</div>'
    )
    for store in stores:
        sid = store["id"]
        sname_short = _short_store(store["name"])
        kpis_html += (
            f'<div class="hs-kpi">'
            f'<div class="hs-kpi-label">{sname_short} Avenida</div>'
            f'<div class="hs-kpi-value">{_fmt_hours_decimal(day_totals_by_store[sid])}</div>'
            f'<div class="hs-kpi-detail">'
            f'{sum(1 for w in working_list if sid in w["hours"]["net_minutes_by_store"])} '
            f'empleado(s) presente(s)</div>'
            f'</div>'
        )
    # Fourth KPI: overtime or off-count
    extras_label = ""
    if day_total_overtime > 0:
        extras_label = f'<div class="hs-kpi-label">Horas extra del día</div>' \
                       f'<div class="hs-kpi-value" style="color:#C9982A;">+{day_total_overtime}m</div>' \
                       f'<div class="hs-kpi-detail">total acumulado</div>'
    else:
        extras_label = (
            '<div class="hs-kpi-label">Día libre / Ausencias</div>'
            f'<div class="hs-kpi-value">{len(off_list)} / {len(absent_list)}</div>'
            f'<div class="hs-kpi-detail">'
            f'{len(off_list)} descanso(s) · {len(absent_list)} ausencia(s)'
            '</div>'
        )
    kpis_html += f'<div class="hs-kpi">{extras_label}</div></div>'

    st.markdown(kpis_html, unsafe_allow_html=True)

    # Working list
    st.markdown(
        f'<div class="hs-section-label">'
        f'✅ Trabajando ({len(working_list)})</div>',
        unsafe_allow_html=True,
    )
    if working_list:
        items = []
        for w in working_list:
            emp = w["emp"]
            initials = "".join([p[0] for p in emp["name"].split()[:2]]).upper() or "?"
            fg, bg = color_for_name(emp["name"])
            mins = w["hours"]["total_net_minutes"]
            ot = w["hours"]["overtime_minutes"]
            stores_in_day = w["hours"]["net_minutes_by_store"]
            store_parts = []
            for sid, m in stores_in_day.items():
                s_short = _short_store(store_labels.get(sid, "?"))
                support = " 🔀" if sid != emp["store_id"] else ""
                if len(stores_in_day) > 1:
                    store_parts.append(f"{s_short}{support} {_fmt_hours_decimal(m)}")
                else:
                    store_parts.append(f"{s_short}{support}")
            store_text = " · ".join(store_parts)
            ot_text = f" · +{ot}m extra" if ot > 0 else ""
            items.append(
                f'<li>'
                f'<div class="hs-avatar" style="background:{bg};color:{fg};">{initials}</div>'
                f'<div class="dl-name">{emp["name"]}<div class="dl-store">{store_text}{ot_text}</div></div>'
                f'<div class="dl-hours">{_fmt_hours_decimal(mins)}</div>'
                f'</li>'
            )
        st.markdown(
            '<div class="hs-daily-panel"><ul class="hs-daily-list">'
            + "".join(items)
            + '</ul></div>',
            unsafe_allow_html=True,
        )
    else:
        st.caption("Nadie trabajó este día.")

    # Off / Absent
    cols = st.columns(3)
    with cols[0]:
        st.markdown(
            f'<div class="hs-section-label">💤 Día libre ({len(off_list)})</div>',
            unsafe_allow_html=True,
        )
        if off_list:
            items = [f'<li><span class="dl-off">{x["emp"]["name"]}</span></li>' for x in off_list]
            st.markdown(
                '<div class="hs-daily-panel"><ul class="hs-daily-list">'
                + "".join(items)
                + '</ul></div>',
                unsafe_allow_html=True,
            )
        else:
            st.caption("—")
    with cols[1]:
        st.markdown(
            f'<div class="hs-section-label">📋 Ausencias ({len(absent_list)})</div>',
            unsafe_allow_html=True,
        )
        if absent_list:
            status_label = {
                "permission": "📋", "vacation": "🏖️", "sick": "🤒",
            }
            items = []
            for x in absent_list:
                icon = status_label.get(x["status"], "•")
                note = x["rec"].get("notes", "")
                note_html = f' <span class="dl-store">— {note}</span>' if note else ""
                items.append(
                    f'<li>{icon} <span class="dl-name">{x["emp"]["name"]}</span>{note_html}</li>'
                )
            st.markdown(
                '<div class="hs-daily-panel"><ul class="hs-daily-list">'
                + "".join(items)
                + '</ul></div>',
                unsafe_allow_html=True,
            )
        else:
            st.caption("—")
    with cols[2]:
        st.markdown(
            f'<div class="hs-section-label">⭕ Sin registro ({no_record_count})</div>',
            unsafe_allow_html=True,
        )
        if no_record_count > 0:
            st.caption(f"{no_record_count} empleado(s) sin captura para esta fecha.")
        else:
            st.caption("—")


GANTT_START_HOUR = 9
GANTT_END_HOUR = 21


def _gantt_pct(minutes: int) -> float:
    """Convert clock minutes (0–1440) to % position within Gantt range."""
    span = (GANTT_END_HOUR - GANTT_START_HOUR) * 60
    base = GANTT_START_HOUR * 60
    return ((minutes - base) / span) * 100


def _inject_gantt_css():
    st.markdown(
        """
        <style>
        .gantt-wrap {
            background: #FFFFFF; border: 1px solid #D8DCE2; border-radius: 6px;
            padding: 0; margin-bottom: 18px; overflow: hidden;
        }
        .gantt-hour-bar {
            display: grid;
            grid-template-columns: 140px 1fr;
            background: #0B0F19; color: #F9FAFB;
            font-family: 'Geist Mono', monospace; font-size: 9.5px;
            letter-spacing: 1.5px; font-weight: 600;
        }
        .gantt-hour-bar > div { padding: 8px 12px; }
        .gantt-hour-bar .hour-ticks {
            display: grid; grid-template-columns: repeat(12, 1fr);
            padding: 0;
        }
        .gantt-hour-bar .hour-ticks > div {
            text-align: center; border-left: 1px solid #1F2937;
            padding: 8px 0; color: #9CA3AF;
        }
        .gantt-hour-bar .hour-ticks > div:first-child { border-left: none; }
        .gantt-hour-bar .today-marker { color: #C9982A; }

        .gantt-day-row {
            display: grid;
            grid-template-columns: 140px 1fr;
            border-top: 1px solid #EBEEF2;
            min-height: 38px;
            align-items: stretch;
        }
        .gantt-day-row.today { background: #FEF9EE; }
        .gantt-day-label {
            padding: 10px 12px; font-size: 11px; color: #0B0F19;
            font-weight: 600; border-right: 1px solid #EBEEF2;
            display: flex; align-items: center; gap: 8px;
        }
        .gantt-day-label .day-num {
            font-family: 'Geist Mono', monospace; font-size: 13px;
            font-weight: 700; color: #C9982A; min-width: 26px;
        }
        .gantt-day-label .day-name {
            font-size: 9.5px; letter-spacing: 1.2px; text-transform: uppercase;
            color: #6C7280; font-weight: 600;
        }
        .gantt-day-track {
            position: relative; padding: 4px 0;
        }
        .gantt-day-track .gantt-grid {
            position: absolute; top: 0; bottom: 0; left: 0; right: 0;
            pointer-events: none;
            background-image: repeating-linear-gradient(
                to right, transparent 0,
                transparent calc((100% / 12) - 1px),
                #EBEEF2 calc((100% / 12) - 1px),
                #EBEEF2 calc(100% / 12)
            );
        }
        .gantt-emp-bar {
            position: absolute; height: 14px; border-radius: 2px;
            font-size: 9px; color: #FFFFFF; padding: 0 4px;
            font-family: 'Geist Mono', monospace; font-weight: 600;
            display: flex; align-items: center; white-space: nowrap;
            overflow: hidden; text-overflow: ellipsis; z-index: 2;
            transition: filter 0.12s ease;
        }
        .gantt-emp-bar:hover { filter: brightness(1.1); z-index: 5; }
        .gantt-emp-bar.working {
            background: linear-gradient(180deg, #1B7340 0%, #166434 100%);
        }
        .gantt-emp-bar.lunch {
            background: linear-gradient(180deg, #D97706 0%, #C2410C 100%);
        }
        .gantt-emp-bar.support {
            background: linear-gradient(180deg, #9A3412 0%, #7C2D12 100%);
        }
        .gantt-now-line {
            position: absolute; top: 0; bottom: 0; width: 1.5px;
            background: #C9982A; z-index: 3;
        }
        .gantt-non-working {
            padding: 8px 12px; font-size: 10.5px; color: #9CA3AF;
            font-style: italic; display: flex; align-items: center;
            gap: 6px; height: 100%;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def _render_stacked_gantt(
    monday: dt.date,
    employees: list[dict],
    stores: list[dict],
    attendance: list[dict],
    today_iso: str,
):
    """Render a stacked Gantt: 7 day rows, each showing all working employees as bars."""
    _inject_gantt_css()
    days = [monday + dt.timedelta(days=i) for i in range(7)]
    by_emp = {e["id"]: e for e in employees}
    store_labels = {s["id"]: s["name"] for s in stores}

    # Index attendance by (date, emp_id)
    by_key = {(r["date"], r["employee_id"]): r for r in attendance}

    # Hour ticks header (9–21)
    hour_ticks_html = ""
    for h in range(GANTT_START_HOUR, GANTT_END_HOUR):
        hour_ticks_html += f"<div>{h}h</div>"

    html = (
        '<div class="gantt-wrap">'
        '<div class="gantt-hour-bar">'
        '<div>EMPLEADOS / DÍA</div>'
        f'<div class="hour-ticks">{hour_ticks_html}</div>'
        '</div>'
    )

    # Compute "now" position only if today is in the week
    now = dt.datetime.now(GT_TZ)
    now_minutes_today = now.hour * 60 + now.minute

    for d in days:
        d_iso = d.isoformat()
        is_today = (d_iso == today_iso)
        row_cls = "gantt-day-row today" if is_today else "gantt-day-row"

        day_short = DAY_SHORT[d.weekday()]
        day_label_html = (
            f'<div class="gantt-day-label">'
            f'<div class="day-num">{d.day}</div>'
            f'<div class="day-name">{day_short}<br>'
            f'{SPANISH_MONTHS[d.month - 1][:3]}</div>'
            f'</div>'
        )

        # Collect all working bars for this day across all employees
        bars_html = []
        non_working_summary = []
        for emp in sorted(employees, key=lambda e: e["name"].lower()):
            rec = by_key.get((d_iso, emp["id"]))
            if not rec:
                continue
            status = rec.get("status", "working")
            if status != "working":
                # Group non-working into a summary (only count, no bars)
                continue

            # Build segments: segment 1 (always), optional segment 2
            segments = []
            s1_start = _parse_hhmm_to_minutes(rec.get("shift_start"))
            s1_end = _parse_hhmm_to_minutes(rec.get("shift_end"))
            s1_store = rec.get("worked_store_id") or emp["store_id"]
            if s1_start is not None and s1_end is not None:
                segments.append({
                    "store": s1_store, "start": s1_start, "end": s1_end,
                })
            if rec.get("shift_split"):
                s2_start = _parse_hhmm_to_minutes(rec.get("segment2_start"))
                s2_end = _parse_hhmm_to_minutes(rec.get("segment2_end"))
                s2_store = rec.get("segment2_store_id") or ""
                if s2_start is not None and s2_end is not None and s2_store:
                    segments.append({
                        "store": s2_store, "start": s2_start, "end": s2_end,
                    })

            ls = _parse_hhmm_to_minutes(rec.get("lunch_start"))
            le = _parse_hhmm_to_minutes(rec.get("lunch_end"))

            initials = "".join([p[0] for p in emp["name"].split()[:2]]).upper() or "?"

            for seg in segments:
                seg_start = seg["start"]
                seg_end = seg["end"]
                seg_store = seg["store"]
                seg_store_short = _short_store(store_labels.get(seg_store, "?"))
                is_support = (seg_store != emp["store_id"])

                # Determine if lunch falls inside this segment
                lunch_inside = (
                    ls is not None and le is not None
                    and ls >= seg_start and le <= seg_end
                )

                # Render segment, possibly split by lunch
                pieces = []
                if lunch_inside:
                    pieces.append((seg_start, ls, "working" if not is_support else "support",
                                   f"{initials} · {seg_store_short}"))
                    pieces.append((ls, le, "lunch", "Almuerzo"))
                    pieces.append((le, seg_end, "working" if not is_support else "support",
                                   f"{initials} · {seg_store_short}"))
                else:
                    pieces.append((seg_start, seg_end, "working" if not is_support else "support",
                                   f"{initials} · {seg_store_short}"))

                for (p_start, p_end, kind, label) in pieces:
                    if p_end <= p_start:
                        continue
                    # Clip to gantt range
                    if p_end < GANTT_START_HOUR * 60 or p_start > GANTT_END_HOUR * 60:
                        continue
                    left = max(0, _gantt_pct(p_start))
                    right = min(100, _gantt_pct(p_end))
                    width = right - left
                    if width <= 0:
                        continue

                    # Tooltip text
                    def fmt_t(mins):
                        return f"{mins // 60:02d}:{mins % 60:02d}"
                    if kind == "lunch":
                        tooltip = f"{emp['name']} · Almuerzo {fmt_t(p_start)}–{fmt_t(p_end)}"
                    elif kind == "support":
                        tooltip = (
                            f"{emp['name']} · {fmt_t(p_start)}–{fmt_t(p_end)} en "
                            f"{store_labels.get(seg_store, seg_store)} (APOYO)"
                        )
                    else:
                        tooltip = (
                            f"{emp['name']} · {fmt_t(p_start)}–{fmt_t(p_end)} en "
                            f"{store_labels.get(seg_store, seg_store)}"
                        )

                    bars_html.append(
                        f'<div class="gantt-emp-bar {kind}" '
                        f'style="left:{left:.2f}%; width:{width:.2f}%; '
                        f'top:{4 + 16 * (len(bars_html) % 0 + 0)}px;" '  # placeholder
                        f'title="{tooltip}">{label}</div>'
                    )

        # Now line for today
        now_line_html = ""
        if is_today and GANTT_START_HOUR * 60 <= now_minutes_today <= GANTT_END_HOUR * 60:
            now_pct = _gantt_pct(now_minutes_today)
            now_line_html = (
                f'<div class="gantt-now-line" style="left:{now_pct:.2f}%;"></div>'
            )

        # Auto-stack bars: assign vertical position per bar to avoid overlaps.
        # Simple approach: use rows by employee initials order; each employee gets a slot.
        # We rebuild bars with correct top position based on emp index for the day.
        # Rebuild this way:
        emp_slot_map = {}
        # Determine which employees have at least one bar this day, in display order
        working_today = []
        for emp in sorted(employees, key=lambda e: e["name"].lower()):
            rec = by_key.get((d_iso, emp["id"]))
            if rec and rec.get("status") == "working":
                working_today.append(emp)

        if not working_today:
            html += (
                f'<div class="{row_cls}">'
                + day_label_html
                + '<div class="gantt-non-working">'
                + 'Nadie trabajó este día'
                + '</div>'
                + '</div>'
            )
            continue

        # Rebuild bars with proper top offsets
        bars_html = []
        for slot_idx, emp in enumerate(working_today):
            rec = by_key.get((d_iso, emp["id"]))
            segments = []
            s1_start = _parse_hhmm_to_minutes(rec.get("shift_start"))
            s1_end = _parse_hhmm_to_minutes(rec.get("shift_end"))
            s1_store = rec.get("worked_store_id") or emp["store_id"]
            if s1_start is not None and s1_end is not None:
                segments.append({"store": s1_store, "start": s1_start, "end": s1_end})
            if rec.get("shift_split"):
                s2_start = _parse_hhmm_to_minutes(rec.get("segment2_start"))
                s2_end = _parse_hhmm_to_minutes(rec.get("segment2_end"))
                s2_store = rec.get("segment2_store_id") or ""
                if s2_start is not None and s2_end is not None and s2_store:
                    segments.append({"store": s2_store, "start": s2_start, "end": s2_end})

            ls = _parse_hhmm_to_minutes(rec.get("lunch_start"))
            le = _parse_hhmm_to_minutes(rec.get("lunch_end"))
            initials = "".join([p[0] for p in emp["name"].split()[:2]]).upper() or "?"

            top_px = 4 + slot_idx * 16  # 14px bar + 2px gap

            for seg in segments:
                seg_start = seg["start"]
                seg_end = seg["end"]
                seg_store = seg["store"]
                seg_store_short = _short_store(store_labels.get(seg_store, "?"))
                is_support = (seg_store != emp["store_id"])

                lunch_inside = (
                    ls is not None and le is not None
                    and ls >= seg_start and le <= seg_end
                )

                pieces = []
                if lunch_inside:
                    pieces.append((seg_start, ls, "working" if not is_support else "support",
                                   f"{initials}·{seg_store_short}"))
                    pieces.append((ls, le, "lunch", "Alm"))
                    pieces.append((le, seg_end, "working" if not is_support else "support",
                                   f"{initials}·{seg_store_short}"))
                else:
                    pieces.append((seg_start, seg_end, "working" if not is_support else "support",
                                   f"{initials}·{seg_store_short}"))

                for (p_start, p_end, kind, label) in pieces:
                    if p_end <= p_start:
                        continue
                    if p_end < GANTT_START_HOUR * 60 or p_start > GANTT_END_HOUR * 60:
                        continue
                    left = max(0, _gantt_pct(p_start))
                    right = min(100, _gantt_pct(p_end))
                    width = right - left
                    if width <= 0:
                        continue

                    def fmt_t(mins):
                        return f"{mins // 60:02d}:{mins % 60:02d}"
                    if kind == "lunch":
                        tooltip = f"{emp['name']} · Almuerzo {fmt_t(p_start)}–{fmt_t(p_end)}"
                    elif kind == "support":
                        tooltip = (
                            f"{emp['name']} · {fmt_t(p_start)}–{fmt_t(p_end)} en "
                            f"{store_labels.get(seg_store, seg_store)} (APOYO)"
                        )
                    else:
                        tooltip = (
                            f"{emp['name']} · {fmt_t(p_start)}–{fmt_t(p_end)} en "
                            f"{store_labels.get(seg_store, seg_store)}"
                        )

                    bars_html.append(
                        f'<div class="gantt-emp-bar {kind}" '
                        f'style="left:{left:.2f}%; width:{width:.2f}%; top:{top_px}px;" '
                        f'title="{tooltip}">{label}</div>'
                    )

        # Calculate row height based on number of working employees
        row_height = max(38, 4 + len(working_today) * 16 + 4)
        track_html = (
            f'<div class="gantt-day-track" style="min-height:{row_height}px;">'
            '<div class="gantt-grid"></div>'
            + "".join(bars_html)
            + now_line_html
            + '</div>'
        )

        html += f'<div class="{row_cls}">{day_label_html}{track_html}</div>'

    html += '</div>'

    st.markdown(html, unsafe_allow_html=True)


GANTT_HOUR_PADDING = 0  # placeholder for future extension


def render_hours_summary(current_user: dict) -> None:
    _inject_css()

    today = _today_gt()
    monday = _monday_of(today)
    sunday = monday + dt.timedelta(days=6)

    # Range label
    if monday.month == sunday.month:
        range_label = (
            f"{monday.day} – {sunday.day} {SPANISH_MONTHS[sunday.month - 1]} {sunday.year}"
        )
    else:
        range_label = (
            f"{monday.day} {SPANISH_MONTHS[monday.month - 1]} – "
            f"{sunday.day} {SPANISH_MONTHS[sunday.month - 1]} {sunday.year}"
        )

    st.markdown(
        f"""
        <div class="hs-header">
          <div>
            <div class="sub">● Vintage Boutique · Resumen de Horas</div>
            <div class="ttl">{range_label}</div>
          </div>
          <div style="text-align:right;font-size:11px;color:#9CA3AF;">
            <div style="color:#F9FAFB;font-weight:500;">{current_user['name']}</div>
            <div>{current_user['email']}</div>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # Load data
    try:
        employees = sheets.get_employees()
        stores = sheets.get_stores()
        attendance = sheets.get_attendance_for_range(
            monday.isoformat(), sunday.isoformat()
        )
    except Exception as e:
        st.error(f"No se pudieron cargar datos: `{e}`")
        return

    if not employees or not stores:
        st.info("No hay empleados o tiendas configurados aún.")
        return

    # ============== STACKED WEEKLY GANTT ==============
    st.markdown(
        '<div class="hs-section-label">'
        '🗓 Distribución de horarios por tienda (vista semanal)</div>',
        unsafe_allow_html=True,
    )

    _render_stacked_gantt(monday, employees, stores, attendance, today.isoformat())

    st.caption(
        "🟢 = trabajando · 🟡 = almuerzo · 🟠 = trabajando en tienda no habitual (Apoyo) · "
        "💤 / 📋 / 🏖 / 🤒 = día no laborable · Cada día va de 9:00 a 21:00 · "
        "Hover sobre una barra muestra el detalle."
    )

    # ============== WEEKLY SUMMARY TABLE ==============
    st.markdown(
        '<div class="hs-section-label">📊 Resumen semanal · horas trabajadas (neto, sin almuerzo)</div>',
        unsafe_allow_html=True,
    )

    summary = _build_weekly_summary(monday, employees, stores, attendance)
    _render_weekly_table(summary, stores, today.isoformat())

    st.caption(
        "🔀 = trabajó en una tienda distinta a su habitual ese día · "
        "💤 = día libre · 📋 = permiso · 🏖️ = vacaciones · 🤒 = enfermo · "
        "— = sin registro · El total semanal incluye solo tiempo de trabajo neto (almuerzo restado)."
    )

    # ============== DAILY DETAIL PANEL ==============
    st.markdown("---")
    st.markdown(
        '<div class="hs-section-label">📅 Detalle diario</div>',
        unsafe_allow_html=True,
    )

    col_dt, _ = st.columns([1, 3])
    with col_dt:
        selected_date = st.date_input(
            "Día a consultar",
            value=st.session_state.get("hours_day", today),
            min_value=monday,
            max_value=sunday,
            format="DD/MM/YYYY",
        )
        st.session_state.hours_day = selected_date

    st.markdown(
        f"<div style='font-size:13px;color:#3D4554;margin:6px 0 14px;'>"
        f"<strong>{_format_spanish_date(selected_date)}</strong>"
        f"</div>",
        unsafe_allow_html=True,
    )

    _render_daily_panel(selected_date, employees, stores, attendance)
