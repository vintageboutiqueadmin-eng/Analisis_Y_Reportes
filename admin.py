"""
Dashboard HTML renderer.

Generates the attendance dashboard view as HTML/CSS.
Designed as an executive analytics dashboard:
- Clean light-gray background
- Geist Sans typography (no decorative serifs)
- Crisp white cards with subtle borders
- Brand gold used sparingly (logo + overtime accent only)
- Status colors are corporate, not playful
"""

from __future__ import annotations

from typing import Iterable
from datetime import datetime, time


# Logo embedded as base64 (small JPEG, ~6KB) so it travels with the app.
LOGO_B64 = (
    "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"
)


# ---------------------------------------------------------------------------
# Time helpers
# ---------------------------------------------------------------------------

def parse_time(t: str | None) -> int | None:
    """Parse 'HH:MM' to minutes from midnight."""
    if not t:
        return None
    if isinstance(t, time):
        return t.hour * 60 + t.minute
    parts = str(t).split(":")
    return int(parts[0]) * 60 + int(parts[1])


def fmt_time_12h(minutes: int | None) -> str:
    """Format minutes-from-midnight as '10:00 AM' / '7:00 PM'."""
    if minutes is None:
        return ""
    h, m = divmod(minutes, 60)
    suffix = "AM" if h < 12 else "PM"
    h12 = h if 1 <= h <= 12 else (12 if h == 0 else h - 12)
    return f"{h12}:{m:02d} {suffix}"


def fmt_duration(minutes: int) -> str:
    """Format a duration in minutes as '8h' or '7h 30m'."""
    if minutes <= 0:
        return "0h"
    h, m = divmod(minutes, 60)
    if m == 0:
        return f"{h}h"
    return f"{h}h {m:02d}m"


# ---------------------------------------------------------------------------
# Status definitions
# ---------------------------------------------------------------------------

STATUS_META = {
    "working":    {"label": "Trabajando",         "key": "working"},
    "day_off":    {"label": "Día libre",          "key": "off"},
    "permission": {"label": "Permiso",            "key": "permission"},
    "vacation":   {"label": "Vacaciones",         "key": "vacation"},
    "sick":       {"label": "Incapacidad",        "key": "sick"},
}


# ---------------------------------------------------------------------------
# CSS
# ---------------------------------------------------------------------------

CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Geist:wght@300;400;500;600;700&family=Geist+Mono:wght@400;500;600&display=swap');

:root {
  --bg: #F2F3F5;
  --surface: #FFFFFF;
  --surface-2: #FAFBFC;
  --surface-3: #F6F7F9;
  --border: #D8DCE2;
  --border-soft: #E8EBF0;
  --ink: #0B0F19;
  --ink-2: #3D4554;
  --ink-3: #6C7280;
  --ink-4: #9CA3AF;
  --brand-black: #0B0F19;
  --brand-gold: #C9982A;
  --brand-gold-bright: #E8C063;

  --working: #1B7340;
  --working-2: #0F5A30;
  --lunch: #B5390C;
  --lunch-2: #8A2A05;
  --overtime: #C9982A;
  --overtime-2: #A37D1F;
  --off: #8B919E;
  --off-bg: #E8EAEE;
  --late: #C2410C;
  --permission: #1D4ED8;
  --vacation: #0891B2;
  --sick: #7C2D12;

  --sans: 'Geist', system-ui, -apple-system, sans-serif;
  --mono: 'Geist Mono', ui-monospace, 'SF Mono', Menlo, monospace;
}

* { margin: 0; padding: 0; box-sizing: border-box; }
html, body { font-family: var(--sans); background: var(--bg); color: var(--ink); font-size: 13px; line-height: 1.45; -webkit-font-smoothing: antialiased; -moz-osx-font-smoothing: grayscale; }

.vb-app { min-height: 100vh; }

/* ============ TOPBAR ============ */
.vb-topbar { background: var(--brand-black); color: #E5E7EB; padding: 14px 32px; display: flex; align-items: center; justify-content: space-between; border-bottom: 1px solid #0B0F19; }
.vb-brand { display: flex; align-items: center; gap: 12px; }
.vb-logo { width: 38px; height: 38px; border-radius: 4px; background-size: cover; background-position: center; border: 1px solid #1F2937; flex-shrink: 0; }
.vb-brand-text { display: flex; flex-direction: column; line-height: 1.1; }
.vb-brand-name { font-size: 14px; font-weight: 600; letter-spacing: -0.2px; color: #F9FAFB; }
.vb-brand-sub { font-size: 9px; font-weight: 500; letter-spacing: 2.5px; color: var(--brand-gold-bright); text-transform: uppercase; margin-top: 2px; }
.vb-topbar-divider { width: 1px; height: 28px; background: #1F2937; margin: 0 20px; }
.vb-topbar-meta { font-size: 10px; text-transform: uppercase; letter-spacing: 2px; color: #6B7280; font-weight: 600; }
.vb-topbar-right { display: flex; align-items: center; gap: 14px; }
.vb-user { text-align: right; }
.vb-user-role { font-size: 9px; text-transform: uppercase; letter-spacing: 2px; color: #6B7280; font-weight: 600; margin-bottom: 2px; }
.vb-user-name { font-size: 13px; color: #F9FAFB; font-weight: 500; }
.vb-user-avatar { width: 32px; height: 32px; border-radius: 50%; background: #1F2937; color: #E5E7EB; display: grid; place-items: center; font-weight: 600; font-size: 11px; border: 1px solid #374151; }

/* ============ CONTAINER ============ */
.vb-container { max-width: 1480px; margin: 0 auto; padding: 28px 32px 60px; }

/* ============ PAGE HEAD ============ */
.vb-page-head { display: flex; justify-content: space-between; align-items: flex-end; padding-bottom: 18px; margin-bottom: 24px; border-bottom: 1px solid var(--border); }
.vb-eyebrow { font-size: 10px; color: var(--ink-3); text-transform: uppercase; letter-spacing: 2.5px; font-weight: 600; margin-bottom: 10px; display: flex; align-items: center; gap: 10px; }
.vb-eyebrow::before { content: ''; width: 14px; height: 1px; background: var(--brand-gold); }
.vb-page-head h1 { font-size: 28px; font-weight: 600; letter-spacing: -0.6px; color: var(--ink); line-height: 1; margin-bottom: 8px; }
.vb-page-date { font-size: 12px; color: var(--ink-2); font-weight: 500; font-family: var(--mono); letter-spacing: 0.2px; text-transform: uppercase; }
.vb-page-date strong { color: var(--ink); font-weight: 600; }
.vb-date-nav { display: flex; align-items: center; gap: 0; background: var(--surface); border: 1px solid var(--border); border-radius: 4px; overflow: hidden; }
.vb-date-nav button, .vb-date-nav a { background: transparent; border: none; padding: 9px 14px; font-family: var(--sans); font-size: 11px; font-weight: 500; color: var(--ink-2); cursor: pointer; border-right: 1px solid var(--border-soft); transition: all 0.15s ease; text-decoration: none; display: inline-block; }
.vb-date-nav button:last-child, .vb-date-nav a:last-child { border-right: none; }
.vb-date-nav button.active, .vb-date-nav a.active { background: var(--ink); color: #FFF; }
.vb-date-nav button:hover:not(.active), .vb-date-nav a:hover:not(.active) { background: var(--surface-3); color: var(--ink); }

/* ============ STATS ============ */
.vb-stats { display: grid; grid-template-columns: repeat(5, 1fr); gap: 0; margin-bottom: 24px; background: var(--surface); border: 1px solid var(--border); border-radius: 4px; }
.vb-stat { padding: 18px 22px; border-right: 1px solid var(--border-soft); }
.vb-stat:last-child { border-right: none; }
.vb-stat-label { font-size: 10px; color: var(--ink-3); text-transform: uppercase; letter-spacing: 2px; margin-bottom: 10px; font-weight: 600; }
.vb-stat-value { font-family: var(--mono); font-weight: 600; font-size: 32px; line-height: 1; color: var(--ink); letter-spacing: -0.8px; display: flex; align-items: baseline; gap: 6px; }
.vb-stat-value .of { font-size: 14px; color: var(--ink-4); font-weight: 500; letter-spacing: 0; }
.vb-stat-detail { font-size: 11px; color: var(--ink-2); margin-top: 8px; display: flex; align-items: center; gap: 7px; }
.vb-stat-dot { width: 7px; height: 7px; border-radius: 50%; display: inline-block; flex-shrink: 0; }

/* ============ LEGEND ============ */
.vb-legend { display: flex; gap: 22px; padding: 12px 22px; background: var(--surface); border: 1px solid var(--border); border-radius: 4px; margin-bottom: 24px; align-items: center; flex-wrap: wrap; }
.vb-legend-label { font-size: 10px; text-transform: uppercase; letter-spacing: 2px; color: var(--ink-3); font-weight: 600; border-right: 1px solid var(--border-soft); padding-right: 22px; }
.vb-legend-item { display: flex; align-items: center; gap: 8px; font-size: 11px; color: var(--ink-2); font-weight: 500; }
.vb-legend-swatch { width: 16px; height: 10px; border-radius: 2px; }
.vb-legend-swatch.working { background: var(--working); }
.vb-legend-swatch.lunch { background: var(--lunch); }
.vb-legend-swatch.overtime { background: var(--overtime); }
.vb-legend-swatch.off { background: var(--off-bg); border: 1px dashed var(--off); }
.vb-legend-swatch.permission { background: var(--permission); }
.vb-legend-swatch.vacation { background: var(--vacation); }
.vb-legend-swatch.sick { background: var(--sick); }
.vb-legend-swatch.late { background: var(--late); }

/* ============ STORE SECTION ============ */
.vb-store { margin-bottom: 22px; background: var(--surface); border: 1px solid var(--border); border-radius: 4px; overflow: hidden; }
.vb-store-head { padding: 16px 22px; border-bottom: 1px solid var(--border); display: flex; justify-content: space-between; align-items: center; background: var(--surface-2); }
.vb-store-head-left { display: flex; align-items: center; gap: 14px; }
.vb-store-marker { font-family: var(--mono); font-size: 10px; text-transform: uppercase; letter-spacing: 1.5px; color: var(--ink-3); font-weight: 600; padding: 4px 8px; border: 1px solid var(--border); border-radius: 3px; background: var(--surface); }
.vb-store-title { font-size: 18px; font-weight: 600; line-height: 1; color: var(--ink); letter-spacing: -0.3px; }
.vb-store-meta { font-size: 10px; color: var(--ink-3); text-transform: uppercase; letter-spacing: 1.5px; text-align: right; font-weight: 600; }
.vb-store-meta strong { color: var(--ink); font-family: var(--mono); font-size: 14px; font-weight: 600; text-transform: none; letter-spacing: 0; display: block; margin-top: 2px; }

/* ============ TIMELINE HEADER ============ */
.vb-timeline-head { display: grid; grid-template-columns: 240px 1fr; border-bottom: 1px solid var(--border); background: var(--surface-3); }
.vb-timeline-head-left { border-right: 1px solid var(--border); padding: 8px 22px; font-size: 9px; color: var(--ink-3); text-transform: uppercase; letter-spacing: 2px; display: flex; align-items: center; font-weight: 600; }
.vb-hours { display: grid; position: relative; }
.vb-hour { padding: 8px 0 8px 7px; font-size: 10px; color: var(--ink-3); font-weight: 600; border-left: 1px solid var(--border-soft); font-family: var(--mono); letter-spacing: 0.3px; }
.vb-hour:first-child { border-left: none; }
.vb-hour .ampm { font-size: 8px; color: var(--ink-4); margin-left: 2px; }
.vb-now-tag { position: absolute; top: 0; transform: translateX(-50%); background: var(--ink); color: #FFF; font-size: 9px; font-weight: 600; letter-spacing: 1px; padding: 3px 7px; border-radius: 2px; z-index: 4; white-space: nowrap; font-family: var(--mono); }

/* ============ EMPLOYEE ROW ============ */
.vb-emp { display: grid; grid-template-columns: 240px 1fr; border-bottom: 1px solid var(--border-soft); min-height: 72px; transition: background 0.12s ease; }
.vb-emp:last-child { border-bottom: none; }
.vb-emp:hover { background: var(--surface-3); }
.vb-emp-info { padding: 14px 18px 14px 22px; border-right: 1px solid var(--border-soft); display: flex; align-items: center; gap: 12px; }
.vb-avatar { width: 34px; height: 34px; border-radius: 50%; background: var(--surface-3); color: var(--ink-2); display: grid; place-items: center; font-weight: 600; font-size: 12px; border: 1px solid var(--border); flex-shrink: 0; font-family: var(--mono); }
.vb-emp-meta { flex: 1; min-width: 0; }
.vb-emp-name { font-weight: 600; font-size: 13px; color: var(--ink); margin-bottom: 3px; letter-spacing: -0.1px; }
.vb-emp-times { font-size: 10.5px; color: var(--ink-3); display: flex; align-items: center; gap: 5px; font-family: var(--mono); }
.vb-emp-times .dot { width: 2px; height: 2px; background: var(--ink-4); border-radius: 50%; }
.vb-emp-times .pill { color: var(--ink); font-weight: 600; }
.vb-emp-times .pill-late { color: var(--late); font-weight: 600; }

/* ============ BAR TRACK ============ */
.vb-bar-wrap { position: relative; padding: 22px 0; }
.vb-bar-track { position: relative; height: 28px; }
.vb-bar-grid { position: absolute; top: -10px; bottom: -10px; left: 0; right: 0; pointer-events: none; }
.vb-bar-grid::before { content: ''; position: absolute; inset: 0; background-image: repeating-linear-gradient(to right, transparent 0, transparent calc(var(--half-step) - 1px), var(--border-soft) calc(var(--half-step) - 1px), var(--border-soft) var(--half-step)); }
.vb-bar-grid::after { content: ''; position: absolute; inset: 0; background-image: repeating-linear-gradient(to right, transparent 0, transparent calc(var(--hour-step) - 1px), var(--border) calc(var(--hour-step) - 1px), var(--border) var(--hour-step)); }
.vb-now-line { position: absolute; top: -10px; bottom: -10px; width: 1px; background: var(--ink); z-index: 3; pointer-events: none; }
.vb-now-line::before { content: ''; position: absolute; top: -3px; left: -3px; width: 7px; height: 7px; border-radius: 50%; background: var(--ink); }

.vb-bar { position: absolute; top: 0; height: 100%; border-radius: 2px; display: flex; align-items: center; padding: 0 9px; font-size: 9.5px; font-weight: 600; letter-spacing: 0.5px; color: rgba(255,255,255,0.97); overflow: hidden; white-space: nowrap; text-transform: uppercase; z-index: 2; transition: filter 0.15s ease; box-shadow: 0 1px 1px rgba(0,0,0,0.06); }
.vb-bar:hover { filter: brightness(1.1); z-index: 5; }
.vb-bar.working { background: linear-gradient(180deg, var(--working) 0%, var(--working-2) 100%); }
.vb-bar.lunch { background: linear-gradient(180deg, var(--lunch) 0%, var(--lunch-2) 100%); }
.vb-bar.overtime { background: linear-gradient(180deg, var(--overtime) 0%, var(--overtime-2) 100%); color: var(--ink); }
.vb-bar.late-marker { background: var(--late); color: #FFF; }

/* Absence/off row styles */
.vb-absence { position: absolute; top: 0; left: 0; right: 0; height: 100%; border-radius: 2px; display: flex; align-items: center; justify-content: center; font-weight: 600; font-size: 10px; letter-spacing: 2px; text-transform: uppercase; }
.vb-absence.off { background: repeating-linear-gradient(135deg, var(--off-bg) 0 8px, transparent 8px 16px); border: 1px dashed var(--off); color: var(--ink-2); }
.vb-absence.permission { background: rgba(29, 78, 216, 0.08); border: 1px dashed var(--permission); color: var(--permission); }
.vb-absence.vacation { background: rgba(8, 145, 178, 0.08); border: 1px dashed var(--vacation); color: var(--vacation); }
.vb-absence.sick { background: rgba(124, 45, 18, 0.08); border: 1px dashed var(--sick); color: var(--sick); }

/* Late indicator on working row */
.vb-late-flag { position: absolute; top: -6px; right: 6px; background: var(--late); color: #FFF; font-size: 8px; font-weight: 700; letter-spacing: 1px; padding: 2px 6px; border-radius: 2px; text-transform: uppercase; z-index: 4; }

/* Empty state */
.vb-empty { padding: 60px 22px; text-align: center; color: var(--ink-3); font-size: 13px; }
.vb-empty strong { display: block; color: var(--ink); margin-bottom: 6px; font-size: 14px; }

/* Footer ornament */
.vb-foot { margin-top: 32px; text-align: center; padding-top: 22px; border-top: 1px solid var(--border); }
.vb-foot-dot { color: var(--brand-gold); letter-spacing: 4px; font-size: 11px; }
.vb-foot-text { font-size: 10px; color: var(--ink-3); letter-spacing: 2px; text-transform: uppercase; margin-top: 6px; font-weight: 600; }

@media (max-width: 1100px) {
  .vb-stats { grid-template-columns: repeat(3, 1fr); }
  .vb-stat:nth-child(3) { border-right: none; }
  .vb-stat:nth-child(1), .vb-stat:nth-child(2), .vb-stat:nth-child(3) { border-bottom: 1px solid var(--border-soft); }
}
</style>
"""


# ---------------------------------------------------------------------------
# Render: top bar
# ---------------------------------------------------------------------------

def render_topbar(user_name: str, user_role: str) -> str:
    initials = "".join([p[0] for p in user_name.split()[:2]]).upper() or "?"
    return f"""
<div class="vb-topbar">
  <div class="vb-brand">
    <div class="vb-logo" style="background-image: url('data:image/jpeg;base64,{LOGO_B64}');"></div>
    <div class="vb-brand-text">
      <div class="vb-brand-name">Vintage Boutique</div>
      <div class="vb-brand-sub">Sistema de Asistencia</div>
    </div>
    <div class="vb-topbar-divider"></div>
    <div class="vb-topbar-meta">Panel Ejecutivo</div>
  </div>
  <div class="vb-topbar-right">
    <div class="vb-user">
      <div class="vb-user-role">{user_role}</div>
      <div class="vb-user-name">{user_name}</div>
    </div>
    <div class="vb-user-avatar">{initials}</div>
  </div>
</div>
"""


# ---------------------------------------------------------------------------
# Render: stats row
# ---------------------------------------------------------------------------

def render_stats(stats: dict) -> str:
    total = stats.get("total", 0)
    working = stats.get("working", 0)
    lunch = stats.get("lunch", 0)
    off = stats.get("off", 0)
    other = stats.get("other_absent", 0)
    return f"""
<div class="vb-stats">
  <div class="vb-stat">
    <div class="vb-stat-label">Personal Programado</div>
    <div class="vb-stat-value">{total - off - other}<span class="of">/ {total}</span></div>
    <div class="vb-stat-detail">activos en ambas tiendas</div>
  </div>
  <div class="vb-stat">
    <div class="vb-stat-label">Trabajando Ahora</div>
    <div class="vb-stat-value">{working}</div>
    <div class="vb-stat-detail"><span class="vb-stat-dot" style="background:var(--working)"></span>en piso de venta</div>
  </div>
  <div class="vb-stat">
    <div class="vb-stat-label">En Almuerzo</div>
    <div class="vb-stat-value">{lunch}</div>
    <div class="vb-stat-detail"><span class="vb-stat-dot" style="background:var(--lunch)"></span>pausa de comida</div>
  </div>
  <div class="vb-stat">
    <div class="vb-stat-label">Día Libre</div>
    <div class="vb-stat-value">{off}</div>
    <div class="vb-stat-detail"><span class="vb-stat-dot" style="background:var(--off)"></span>descanso programado</div>
  </div>
  <div class="vb-stat">
    <div class="vb-stat-label">Otras Ausencias</div>
    <div class="vb-stat-value">{other}</div>
    <div class="vb-stat-detail"><span class="vb-stat-dot" style="background:var(--permission)"></span>permiso · vacaciones · incapacidad</div>
  </div>
</div>
"""


# ---------------------------------------------------------------------------
# Render: legend
# ---------------------------------------------------------------------------

def render_legend() -> str:
    return """
<div class="vb-legend">
  <span class="vb-legend-label">Referencia</span>
  <div class="vb-legend-item"><span class="vb-legend-swatch working"></span>Trabajando</div>
  <div class="vb-legend-item"><span class="vb-legend-swatch lunch"></span>Almuerzo</div>
  <div class="vb-legend-item"><span class="vb-legend-swatch overtime"></span>Hora extra</div>
  <div class="vb-legend-item"><span class="vb-legend-swatch late"></span>Llegada tarde</div>
  <div class="vb-legend-item"><span class="vb-legend-swatch off"></span>Día libre</div>
  <div class="vb-legend-item"><span class="vb-legend-swatch permission"></span>Permiso</div>
  <div class="vb-legend-item"><span class="vb-legend-swatch vacation"></span>Vacaciones</div>
  <div class="vb-legend-item"><span class="vb-legend-swatch sick"></span>Incapacidad</div>
</div>
"""


# ---------------------------------------------------------------------------
# Timeline rendering helpers
# ---------------------------------------------------------------------------

def compute_timeline_range(
    employees_by_store: dict,
    default_start_hour: int = 9,
    default_end_hour: int = 19,
    padding_hours: int = 0,
) -> tuple[int, int]:
    """
    Decide the visible timeline range (in hours, 24-format).
    Starts from earliest start time (incl. lunch and overtime) but at most default_start_hour.
    Ends at latest end time but at least default_end_hour.
    """
    earliest = default_start_hour * 60
    latest = default_end_hour * 60
    for store in employees_by_store.values():
        for emp in store:
            if emp.get("status") != "working":
                continue
            ss = parse_time(emp.get("shift_start"))
            se = parse_time(emp.get("shift_end"))
            if ss is not None:
                earliest = min(earliest, ss)
            if se is not None:
                latest = max(latest, se + (emp.get("overtime_minutes") or 0))
    # Round to whole hours
    start_h = max(5, (earliest // 60))
    end_h = min(23, ((latest + 59) // 60))
    # Ensure minimum width
    if end_h - start_h < 8:
        end_h = start_h + 8
    return start_h, end_h


def render_hour_labels(start_h: int, end_h: int, now_minutes: int | None) -> str:
    cells = []
    total_hours = end_h - start_h
    for i in range(total_hours):
        h = start_h + i
        if h == 0:
            label = "12<span class=\"ampm\">am</span>"
        elif h < 12:
            label = f"{h}<span class=\"ampm\">am</span>" if i == 0 or h == 12 else str(h)
        elif h == 12:
            label = "12<span class=\"ampm\">pm</span>"
        else:
            h12 = h - 12
            label = f"{h12}<span class=\"ampm\">pm</span>" if i == 0 or h == 13 else str(h12)
        cells.append(f'<div class="vb-hour">{label}</div>')
    grid_cols = f"repeat({total_hours}, 1fr)"
    now_tag = ""
    if now_minutes is not None and start_h * 60 <= now_minutes <= end_h * 60:
        pct = (now_minutes - start_h * 60) / (total_hours * 60) * 100
        now_tag = f'<div class="vb-now-tag" style="left: {pct:.2f}%;">AHORA · {fmt_time_12h(now_minutes)}</div>'
    return f'<div class="vb-hours" style="grid-template-columns: {grid_cols};">{"".join(cells)}{now_tag}</div>'


def pct(minutes: int, start_h: int, end_h: int) -> float:
    total = (end_h - start_h) * 60
    return (minutes - start_h * 60) / total * 100


# ---------------------------------------------------------------------------
# Render: employee row
# ---------------------------------------------------------------------------

def render_employee_row(emp: dict, start_h: int, end_h: int, now_minutes: int | None) -> str:
    name = emp.get("name", "")
    initials = "".join([p[0] for p in name.split()[:2]]).upper() or "?"
    status = emp.get("status", "working")

    total_hours = end_h - start_h
    half_step = f"calc((100% / {total_hours * 2}))"
    hour_step = f"calc((100% / {total_hours}))"

    now_line = ""
    if now_minutes is not None and start_h * 60 <= now_minutes <= end_h * 60:
        now_pct = pct(now_minutes, start_h, end_h)
        now_line = f'<div class="vb-now-line" style="left: {now_pct:.2f}%;"></div>'

    # ----- Working day -----
    if status == "working":
        ss = parse_time(emp.get("shift_start"))
        se = parse_time(emp.get("shift_end"))
        ls = parse_time(emp.get("lunch_start"))
        le = parse_time(emp.get("lunch_end"))
        overtime_min = emp.get("overtime_minutes") or 0
        is_late = emp.get("is_late", False)
        actual_start = parse_time(emp.get("actual_start"))

        # Total working minutes (excluding lunch)
        total_min = 0
        if ss is not None and se is not None:
            total_min = se - ss
            if ls is not None and le is not None:
                total_min -= (le - ls)
        worked_label = fmt_duration(total_min)
        extra_label = f" + {fmt_duration(overtime_min)} extra" if overtime_min else ""

        # Schedule string
        time_line_parts = [
            f"{fmt_time_12h(ss)}",
            '<span class="dot"></span>',
            f"{fmt_time_12h(se + overtime_min) if se else ''}",
            '<span class="dot"></span>',
            f'<span class="pill">{worked_label}{extra_label}</span>',
        ]
        if is_late and actual_start is not None:
            time_line_parts.append('<span class="dot"></span>')
            time_line_parts.append(
                f'<span class="pill-late">tarde · llegó {fmt_time_12h(actual_start)}</span>'
            )

        # Bars
        bars_html = []
        if ss is not None and se is not None:
            effective_start = actual_start if (is_late and actual_start) else ss
            # If late, render small "late" gap before bar? We'll just start the bar at the actual_start.
            if ls is not None and le is not None and ls > effective_start and le < se:
                # Working morning
                left = pct(effective_start, start_h, end_h)
                width = pct(ls, start_h, end_h) - left
                if width > 0:
                    bars_html.append(
                        f'<div class="vb-bar working" style="left: {left:.2f}%; width: {width:.2f}%;">{fmt_time_12h(effective_start)}</div>'
                    )
                # Lunch
                left = pct(ls, start_h, end_h)
                width = pct(le, start_h, end_h) - left
                bars_html.append(
                    f'<div class="vb-bar lunch" style="left: {left:.2f}%; width: {width:.2f}%;">Almuerzo</div>'
                )
                # Working afternoon
                left = pct(le, start_h, end_h)
                width = pct(se, start_h, end_h) - left
                exit_label = f"Sale {fmt_time_12h(se)}"
                bars_html.append(
                    f'<div class="vb-bar working" style="left: {left:.2f}%; width: {width:.2f}%;">{exit_label}</div>'
                )
            else:
                left = pct(effective_start, start_h, end_h)
                width = pct(se, start_h, end_h) - left
                bars_html.append(
                    f'<div class="vb-bar working" style="left: {left:.2f}%; width: {width:.2f}%;">{fmt_time_12h(effective_start)} → {fmt_time_12h(se)}</div>'
                )
            # Overtime
            if overtime_min:
                left = pct(se, start_h, end_h)
                width = pct(se + overtime_min, start_h, end_h) - left
                if width > 0:
                    bars_html.append(
                        f'<div class="vb-bar overtime" style="left: {left:.2f}%; width: {width:.2f}%;">+ Extra</div>'
                    )
            # Late flag
            if is_late:
                bars_html.append('<div class="vb-late-flag">Tarde</div>')

        return f"""
<div class="vb-emp">
  <div class="vb-emp-info">
    <div class="vb-avatar">{initials}</div>
    <div class="vb-emp-meta">
      <div class="vb-emp-name">{name}</div>
      <div class="vb-emp-times">{''.join(time_line_parts)}</div>
    </div>
  </div>
  <div class="vb-bar-wrap">
    <div class="vb-bar-track">
      <div class="vb-bar-grid" style="--half-step: {half_step}; --hour-step: {hour_step};"></div>
      {''.join(bars_html)}
      {now_line}
    </div>
  </div>
</div>
"""

    # ----- Absence states -----
    absence_classes = {
        "day_off": ("off", "Día libre"),
        "permission": ("permission", "Permiso"),
        "vacation": ("vacation", "Vacaciones"),
        "sick": ("sick", "Incapacidad"),
    }
    cls, label = absence_classes.get(status, ("off", "—"))
    notes = emp.get("notes", "")
    sub_line = notes if notes else label

    return f"""
<div class="vb-emp">
  <div class="vb-emp-info">
    <div class="vb-avatar">{initials}</div>
    <div class="vb-emp-meta">
      <div class="vb-emp-name">{name}</div>
      <div class="vb-emp-times">{sub_line}</div>
    </div>
  </div>
  <div class="vb-bar-wrap">
    <div class="vb-bar-track">
      <div class="vb-bar-grid" style="--half-step: {half_step}; --hour-step: {hour_step};"></div>
      <div class="vb-absence {cls}">{label}</div>
      {now_line}
    </div>
  </div>
</div>
"""


# ---------------------------------------------------------------------------
# Render: store section
# ---------------------------------------------------------------------------

def render_store(
    title: str,
    marker: str,
    employees: list[dict],
    start_h: int,
    end_h: int,
    now_minutes: int | None,
) -> str:
    # Total scheduled hours
    total_min = 0
    for emp in employees:
        if emp.get("status") != "working":
            continue
        ss = parse_time(emp.get("shift_start"))
        se = parse_time(emp.get("shift_end"))
        ls = parse_time(emp.get("lunch_start"))
        le = parse_time(emp.get("lunch_end"))
        ot = emp.get("overtime_minutes") or 0
        if ss is not None and se is not None:
            total_min += (se - ss) + ot
            if ls is not None and le is not None:
                total_min -= (le - ls)

    rows = [render_employee_row(emp, start_h, end_h, now_minutes) for emp in employees]
    if not rows:
        rows_html = '<div class="vb-empty"><strong>Sin personal asignado</strong>Marisol aún no ha cargado la asistencia de esta tienda para la fecha seleccionada.</div>'
    else:
        rows_html = "".join(rows)

    return f"""
<div class="vb-store">
  <div class="vb-store-head">
    <div class="vb-store-head-left">
      <span class="vb-store-marker">{marker}</span>
      <div class="vb-store-title">Tienda {title}</div>
    </div>
    <div class="vb-store-meta">Horas programadas<strong>{fmt_duration(total_min)}</strong></div>
  </div>
  <div class="vb-timeline-head">
    <div class="vb-timeline-head-left">Personal</div>
    {render_hour_labels(start_h, end_h, now_minutes)}
  </div>
  {rows_html}
</div>
"""


# ---------------------------------------------------------------------------
# Render: full dashboard
# ---------------------------------------------------------------------------

def render_dashboard(data: dict, user_name: str = "Lic. Juan Orozco", user_role: str = "Gerencia") -> str:
    """Render the complete dashboard view as HTML."""
    date_display = data.get("date_display", "")
    now_minutes = data.get("now_minutes")  # None for past/future dates
    stats = data.get("stats", {})
    stores = data.get("stores", [])

    employees_by_store = {s["title"]: s["employees"] for s in stores}
    start_h, end_h = compute_timeline_range(employees_by_store)

    stores_html = "".join(
        render_store(
            title=s["title"],
            marker=s.get("marker", ""),
            employees=s["employees"],
            start_h=start_h,
            end_h=end_h,
            now_minutes=now_minutes,
        )
        for s in stores
    )

    return f"""
{CSS}
<div class="vb-app">
  {render_topbar(user_name, user_role)}
  <div class="vb-container">
    <div class="vb-page-head">
      <div>
        <div class="vb-eyebrow">Vista diaria</div>
        <h1>Asistencia</h1>
        <div class="vb-page-date">{date_display}</div>
      </div>
    </div>
    {render_stats(stats)}
    {render_legend()}
    {stores_html}
    <div class="vb-foot">
      <div class="vb-foot-dot">· ✦ ·</div>
      <div class="vb-foot-text">Vintage Boutique · Antigua Guatemala</div>
    </div>
  </div>
</div>
"""
