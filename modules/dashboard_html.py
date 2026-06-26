"""
Dashboard HTML renderer.

Generates the attendance dashboard as HTML/CSS.

Executive look:
  - Cool light-gray background, no decorative serifs
  - Geist Sans + Geist Mono typography
  - Crisp white cards, subtle gold accent only on logo + overtime
  - Inline SVG logo (no external assets)

Responsive:
  - Mobile (< 640px): timeline with horizontal scroll, sticky employee column
  - Tablet (640-1023px): 3-col stats, compact spacing
  - Desktop (1024-1599px): full 5-col layout, max 1480px wide
  - Large TV (1600px+): wider container (1800px), bigger typography
"""

from __future__ import annotations

from datetime import time


# ---------------------------------------------------------------------------
# Inline SVG logos (no external file dependency)
# ---------------------------------------------------------------------------

LOGO_LARGE_SVG = """
<svg viewBox="0 0 120 120" xmlns="http://www.w3.org/2000/svg">
  <rect x="0" y="0" width="120" height="120" rx="10" fill="#0B0F19"/>
  <rect x="6" y="6" width="108" height="108" rx="6" fill="none"
        stroke="#C9982A" stroke-width="1" opacity="0.55"/>
  <text x="60" y="29" font-family="Geist, -apple-system, sans-serif" font-size="7.5"
        font-weight="700" fill="#C9982A" text-anchor="middle" letter-spacing="3">VINTAGE</text>
  <line x1="22" y1="40" x2="36" y2="40" stroke="#C9982A" stroke-width="0.6" opacity="0.55"/>
  <line x1="84" y1="40" x2="98" y2="40" stroke="#C9982A" stroke-width="0.6" opacity="0.55"/>
  <text x="60" y="82" font-family="Georgia, 'Times New Roman', serif"
        font-size="58" font-weight="400" font-style="italic"
        fill="#C9982A" text-anchor="middle">V</text>
  <circle cx="60" cy="94" r="1" fill="#C9982A" opacity="0.7"/>
  <text x="60" y="106" font-family="Geist, -apple-system, sans-serif" font-size="6.5"
        font-weight="700" fill="#C9982A" text-anchor="middle" letter-spacing="2.5">BOUTIQUE</text>
</svg>
"""

LOGO_SMALL_SVG = """
<svg viewBox="0 0 40 40" xmlns="http://www.w3.org/2000/svg">
  <rect x="0" y="0" width="40" height="40" rx="4" fill="#0B0F19"/>
  <rect x="2" y="2" width="36" height="36" rx="2.5" fill="none"
        stroke="#C9982A" stroke-width="0.7" opacity="0.55"/>
  <text x="20" y="28" font-family="Georgia, 'Times New Roman', serif"
        font-size="22" font-weight="400" font-style="italic"
        fill="#C9982A" text-anchor="middle">V</text>
</svg>
"""


# ---------------------------------------------------------------------------
# Time helpers
# ---------------------------------------------------------------------------

def parse_time(t):
    """Parse 'HH:MM' to minutes from midnight."""
    if not t:
        return None
    if isinstance(t, time):
        return t.hour * 60 + t.minute
    parts = str(t).split(":")
    return int(parts[0]) * 60 + int(parts[1])


def fmt_time_12h(minutes):
    """Format minutes-from-midnight as '10:00 AM' / '7:00 PM'."""
    if minutes is None:
        return ""
    h, m = divmod(minutes, 60)
    suffix = "AM" if h < 12 else "PM"
    h12 = h if 1 <= h <= 12 else (12 if h == 0 else h - 12)
    return f"{h12}:{m:02d} {suffix}"


def fmt_duration(minutes):
    """Format duration in minutes as '8h' or '7h 30m'."""
    if minutes <= 0:
        return "0h"
    h, m = divmod(minutes, 60)
    if m == 0:
        return f"{h}h"
    return f"{h}h {m:02d}m"


# ---------------------------------------------------------------------------
# Status metadata
# ---------------------------------------------------------------------------

STATUS_META = {
    "working":    {"label": "Trabajando",  "key": "working"},
    "day_off":    {"label": "Día libre",   "key": "off"},
    "permission": {"label": "Permiso",     "key": "permission"},
    "vacation":   {"label": "Vacaciones",  "key": "vacation"},
    "sick":       {"label": "Incapacidad", "key": "sick"},
}


# ---------------------------------------------------------------------------
# CSS — mobile-first, with progressive breakpoints
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
html, body { font-family: var(--sans); background: var(--bg); color: var(--ink);
  font-size: 13px; line-height: 1.45;
  -webkit-font-smoothing: antialiased; -moz-osx-font-smoothing: grayscale; }

.vb-app { min-height: 100vh; width: 100%; }

/* ============ TOPBAR ============ */
.vb-topbar {
  background: var(--brand-black); color: #E5E7EB;
  padding: 10px 14px;
  display: flex; align-items: center; justify-content: space-between;
  border-bottom: 1px solid #0B0F19;
  gap: 8px;
}
.vb-brand { display: flex; align-items: center; gap: 10px; min-width: 0; }
.vb-logo {
  width: 34px; height: 34px; flex-shrink: 0;
  border-radius: 4px; overflow: hidden;
}
.vb-logo svg { width: 100%; height: 100%; display: block; }
.vb-brand-text { display: flex; flex-direction: column; line-height: 1.1; min-width: 0; }
.vb-brand-name { font-size: 13px; font-weight: 600; letter-spacing: -0.2px; color: #F9FAFB;
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.vb-brand-sub { font-size: 8.5px; font-weight: 600; letter-spacing: 2px;
  color: var(--brand-gold-bright); text-transform: uppercase; margin-top: 2px; }
.vb-topbar-divider { display: none; width: 1px; height: 28px; background: #1F2937; margin: 0 14px; }
.vb-topbar-meta { display: none; font-size: 10px; text-transform: uppercase;
  letter-spacing: 2px; color: #6B7280; font-weight: 600; }
.vb-topbar-right { display: flex; align-items: center; gap: 10px; flex-shrink: 0; }
.vb-user { display: none; text-align: right; }
.vb-user-role { font-size: 9px; text-transform: uppercase; letter-spacing: 2px;
  color: #6B7280; font-weight: 600; margin-bottom: 2px; }
.vb-user-name { font-size: 12px; color: #F9FAFB; font-weight: 500;
  white-space: nowrap; }
.vb-user-avatar { width: 30px; height: 30px; border-radius: 50%; background: #1F2937;
  color: #E5E7EB; display: grid; place-items: center; font-weight: 600;
  font-size: 10px; border: 1px solid #374151; flex-shrink: 0; }

/* ============ CONTAINER ============ */
.vb-container { width: 100%; padding: 14px 12px 40px; }

/* ============ PAGE HEAD ============ */
.vb-page-head { display: flex; justify-content: space-between; align-items: flex-end;
  padding-bottom: 14px; margin-bottom: 16px; border-bottom: 1px solid var(--border);
  flex-wrap: wrap; gap: 12px; }
.vb-eyebrow { font-size: 9.5px; color: var(--ink-3); text-transform: uppercase;
  letter-spacing: 2.5px; font-weight: 600; margin-bottom: 8px;
  display: flex; align-items: center; gap: 9px; }
.vb-eyebrow::before { content: ''; width: 12px; height: 1px; background: var(--brand-gold); }
.vb-page-head h1 { font-size: 22px; font-weight: 600; letter-spacing: -0.5px;
  color: var(--ink); line-height: 1; margin-bottom: 6px; }
.vb-page-date { font-size: 10.5px; color: var(--ink-2); font-weight: 500;
  font-family: var(--mono); letter-spacing: 0.2px; text-transform: uppercase; }

/* ============ STATS ============ */
.vb-stats { display: grid; grid-template-columns: 1fr 1fr; gap: 0;
  margin-bottom: 14px; background: var(--surface);
  border: 1px solid var(--border); border-radius: 4px; overflow: hidden; }
.vb-stat { padding: 14px 14px; border-right: 1px solid var(--border-soft);
  border-bottom: 1px solid var(--border-soft); }
.vb-stat:nth-child(2n) { border-right: none; }
.vb-stat:nth-last-child(-n+2) { border-bottom: none; }
.vb-stat-label { font-size: 9px; color: var(--ink-3); text-transform: uppercase;
  letter-spacing: 1.8px; margin-bottom: 8px; font-weight: 600; }
.vb-stat-value { font-family: var(--mono); font-weight: 600; font-size: 26px;
  line-height: 1; color: var(--ink); letter-spacing: -0.6px;
  display: flex; align-items: baseline; gap: 5px; }
.vb-stat-value .of { font-size: 12px; color: var(--ink-4); font-weight: 500;
  letter-spacing: 0; }
.vb-stat-detail { font-size: 10px; color: var(--ink-2); margin-top: 7px;
  display: flex; align-items: center; gap: 6px; line-height: 1.3; }
.vb-stat-dot { width: 6px; height: 6px; border-radius: 50%; display: inline-block;
  flex-shrink: 0; }

/* ============ LEGEND ============ */
.vb-legend { display: none; gap: 16px; padding: 10px 16px; background: var(--surface);
  border: 1px solid var(--border); border-radius: 4px; margin-bottom: 14px;
  align-items: center; flex-wrap: wrap; }
.vb-legend-label { font-size: 9.5px; text-transform: uppercase; letter-spacing: 2px;
  color: var(--ink-3); font-weight: 600;
  border-right: 1px solid var(--border-soft); padding-right: 16px; }
.vb-legend-item { display: flex; align-items: center; gap: 7px; font-size: 10.5px;
  color: var(--ink-2); font-weight: 500; }
.vb-legend-swatch { width: 14px; height: 9px; border-radius: 2px; }
.vb-legend-swatch.working { background: var(--working); }
.vb-legend-swatch.lunch { background: var(--lunch); }
.vb-legend-swatch.overtime { background: var(--overtime); }
.vb-legend-swatch.off { background: var(--off-bg); border: 1px dashed var(--off); }
.vb-legend-swatch.permission { background: var(--permission); }
.vb-legend-swatch.vacation { background: var(--vacation); }
.vb-legend-swatch.sick { background: var(--sick); }
.vb-legend-swatch.late { background: var(--late); }

/* ============ STORE ============ */
.vb-store { margin-bottom: 16px; background: var(--surface);
  border: 1px solid var(--border); border-radius: 4px; overflow: hidden; }
.vb-store-head { padding: 14px 16px; border-bottom: 1px solid var(--border);
  display: flex; justify-content: space-between; align-items: center;
  background: var(--surface-2); gap: 12px; flex-wrap: wrap; }
.vb-store-head-left { display: flex; align-items: center; gap: 10px; min-width: 0; }
.vb-store-marker { font-family: var(--mono); font-size: 9.5px;
  text-transform: uppercase; letter-spacing: 1.3px; color: var(--ink-3);
  font-weight: 600; padding: 3px 7px; border: 1px solid var(--border);
  border-radius: 3px; background: var(--surface); white-space: nowrap; }
.vb-store-title { font-size: 16px; font-weight: 600; line-height: 1;
  color: var(--ink); letter-spacing: -0.3px; }
.vb-store-date { font-size: 12.5px; color: var(--ink-3); font-weight: 500;
  letter-spacing: 0.2px; padding-left: 12px; margin-left: 2px;
  border-left: 1px solid var(--border); white-space: nowrap; }
.vb-store-meta { font-size: 9.5px; color: var(--ink-3); text-transform: uppercase;
  letter-spacing: 1.3px; text-align: right; font-weight: 600; }
.vb-store-meta strong { color: var(--ink); font-family: var(--mono); font-size: 13px;
  font-weight: 600; text-transform: none; letter-spacing: 0; display: block; margin-top: 2px; }

/* ============ TIMELINE (with mobile scroll) ============ */
.vb-store-scroll { overflow-x: auto; -webkit-overflow-scrolling: touch; }
.vb-timeline-head { display: grid; grid-template-columns: 130px 1fr; min-width: 680px;
  border-bottom: 1px solid var(--border); background: var(--surface-3); }
.vb-timeline-head-left { border-right: 1px solid var(--border); padding: 8px 14px;
  font-size: 8.5px; color: var(--ink-3); text-transform: uppercase; letter-spacing: 2px;
  display: flex; align-items: center; font-weight: 600;
  position: sticky; left: 0; background: var(--surface-3); z-index: 2; }
.vb-hours { display: grid; position: relative; }
.vb-hour { padding: 7px 0 7px 6px; font-size: 9.5px; color: var(--ink-3);
  font-weight: 600; border-left: 1px solid var(--border-soft);
  font-family: var(--mono); letter-spacing: 0.3px; }
.vb-hour:first-child { border-left: none; }
.vb-hour .ampm { font-size: 7.5px; color: var(--ink-4); margin-left: 2px; }
.vb-now-tag { position: absolute; top: 0; transform: translateX(-50%);
  background: var(--ink); color: #FFF; font-size: 8.5px; font-weight: 600;
  letter-spacing: 1px; padding: 3px 6px; border-radius: 2px; z-index: 4;
  white-space: nowrap; font-family: var(--mono); }

/* ============ EMPLOYEE ROW ============ */
.vb-emp { display: grid; grid-template-columns: 130px 1fr; min-width: 680px;
  border-bottom: 1px solid var(--border-soft); min-height: 66px;
  transition: background 0.12s ease; }
.vb-emp:last-child { border-bottom: none; }
.vb-emp:hover { background: var(--surface-3); }
.vb-emp-info { padding: 11px 12px; border-right: 1px solid var(--border-soft);
  display: flex; align-items: center; gap: 9px;
  position: sticky; left: 0; background: var(--surface); z-index: 1; }
.vb-emp:hover .vb-emp-info { background: var(--surface-3); }
.vb-avatar { width: 30px; height: 30px; border-radius: 50%; background: var(--surface-3);
  color: var(--ink-2); display: grid; place-items: center; font-weight: 600;
  font-size: 11px; border: 1px solid var(--border); flex-shrink: 0;
  font-family: var(--mono); }
.vb-emp-meta { flex: 1; min-width: 0; }
.vb-emp-name { font-weight: 600; font-size: 12px; color: var(--ink); margin-bottom: 2px;
  letter-spacing: -0.1px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.vb-support-badge {
    display: inline-block; margin-left: 6px; padding: 1px 6px;
    background: #FFEDD5; color: #9A3412; font-size: 8.5px; font-weight: 700;
    letter-spacing: 1px; border-radius: 2px; text-transform: uppercase;
    vertical-align: middle;
}
.vb-emp-times { font-size: 9.5px; color: var(--ink-3); display: flex; align-items: center;
  gap: 4px; font-family: var(--mono); flex-wrap: wrap; line-height: 1.3; }
.vb-emp-times .dot { width: 2px; height: 2px; background: var(--ink-4); border-radius: 50%; }
.vb-emp-times .pill { color: var(--ink); font-weight: 600; }
.vb-emp-times .pill-late { color: var(--late); font-weight: 600; }

/* ============ BARS ============ */
.vb-bar-wrap { position: relative; padding: 18px 0; }
.vb-bar-track { position: relative; height: 26px; }
.vb-bar-grid { position: absolute; top: -10px; bottom: -10px; left: 0; right: 0;
  pointer-events: none; }
.vb-bar-grid::before { content: ''; position: absolute; inset: 0;
  background-image: repeating-linear-gradient(to right, transparent 0,
    transparent calc(var(--half-step) - 1px), var(--border-soft)
    calc(var(--half-step) - 1px), var(--border-soft) var(--half-step)); }
.vb-bar-grid::after { content: ''; position: absolute; inset: 0;
  background-image: repeating-linear-gradient(to right, transparent 0,
    transparent calc(var(--hour-step) - 1px), var(--border)
    calc(var(--hour-step) - 1px), var(--border) var(--hour-step)); }
.vb-now-line { position: absolute; top: -10px; bottom: -10px; width: 1px;
  background: var(--ink); z-index: 3; pointer-events: none; }
.vb-now-line::before { content: ''; position: absolute; top: -3px; left: -3px;
  width: 7px; height: 7px; border-radius: 50%; background: var(--ink); }

.vb-bar { position: absolute; top: 0; height: 100%; border-radius: 2px;
  display: flex; align-items: center; padding: 0 8px; font-size: 9px;
  font-weight: 600; letter-spacing: 0.4px; color: rgba(255,255,255,0.97);
  overflow: hidden; white-space: nowrap; text-transform: uppercase; z-index: 2;
  transition: filter 0.15s ease; box-shadow: 0 1px 1px rgba(0,0,0,0.06); }
.vb-bar:hover { filter: brightness(1.1); z-index: 5; }
.vb-bar.working { background: linear-gradient(180deg, var(--working) 0%, var(--working-2) 100%); }
.vb-bar.lunch { background: linear-gradient(180deg, var(--lunch) 0%, var(--lunch-2) 100%);
  font-size: 8.5px; padding: 0 4px; letter-spacing: 0.2px;
  justify-content: center; }
.vb-bar.overtime { background: linear-gradient(180deg, var(--overtime) 0%, var(--overtime-2) 100%);
  color: var(--ink); }
.vb-bar.late-marker { background: var(--late); color: #FFF; }

.vb-absence { position: absolute; top: 0; left: 0; right: 0; height: 100%;
  border-radius: 2px; display: flex; align-items: center; justify-content: center;
  font-weight: 600; font-size: 9.5px; letter-spacing: 2px; text-transform: uppercase; }
.vb-absence.off { background: repeating-linear-gradient(135deg, var(--off-bg) 0 8px,
  transparent 8px 16px); border: 1px dashed var(--off); color: var(--ink-2); }
.vb-absence.permission { background: rgba(29, 78, 216, 0.08);
  border: 1px dashed var(--permission); color: var(--permission); }
.vb-absence.vacation { background: rgba(8, 145, 178, 0.08);
  border: 1px dashed var(--vacation); color: var(--vacation); }
.vb-absence.sick { background: rgba(124, 45, 18, 0.08);
  border: 1px dashed var(--sick); color: var(--sick); }

.vb-late-flag { position: absolute; top: -5px; right: 5px; background: var(--late);
  color: #FFF; font-size: 7.5px; font-weight: 700; letter-spacing: 1px;
  padding: 2px 5px; border-radius: 2px; text-transform: uppercase; z-index: 4; }

.vb-empty { padding: 50px 16px; text-align: center; color: var(--ink-3); font-size: 12px; }
.vb-empty strong { display: block; color: var(--ink); margin-bottom: 5px; font-size: 13px; }

.vb-foot { margin-top: 24px; text-align: center; padding-top: 18px;
  border-top: 1px solid var(--border); }
.vb-foot-dot { color: var(--brand-gold); letter-spacing: 4px; font-size: 10.5px; }
.vb-foot-text { font-size: 9.5px; color: var(--ink-3); letter-spacing: 2px;
  text-transform: uppercase; margin-top: 5px; font-weight: 600; }

/* ============================================================ */
/* TABLET (>= 640px) */
/* ============================================================ */
@media (min-width: 640px) {
  html, body { font-size: 13px; }
  .vb-topbar { padding: 12px 22px; gap: 12px; }
  .vb-logo { width: 38px; height: 38px; }
  .vb-brand-name { font-size: 14px; }
  .vb-brand-sub { font-size: 9px; letter-spacing: 2.5px; }
  .vb-user { display: block; }
  .vb-user-avatar { width: 32px; height: 32px; font-size: 11px; }
  .vb-container { padding: 20px 20px 50px; }
  .vb-page-head h1 { font-size: 24px; }
  .vb-page-date { font-size: 11px; }
  .vb-stats { grid-template-columns: repeat(3, 1fr); }
  .vb-stat:nth-child(2n) { border-right: 1px solid var(--border-soft); }
  .vb-stat:nth-child(3n) { border-right: none; }
  .vb-stat:nth-last-child(-n+2) { border-bottom: 1px solid var(--border-soft); }
  .vb-stat:nth-last-child(-n+1) { border-bottom: none; }
  .vb-stat:nth-child(n+4) { border-bottom: none; }
  .vb-stat { padding: 16px 18px; }
  .vb-stat-value { font-size: 28px; }
  .vb-legend { display: flex; }
  .vb-store-head { padding: 15px 20px; }
  .vb-store-title { font-size: 17px; }
  .vb-timeline-head, .vb-emp { grid-template-columns: 180px 1fr; min-width: 700px; }
  .vb-emp-info { padding: 13px 16px; }
  .vb-avatar { width: 32px; height: 32px; font-size: 11px; }
  .vb-emp-name { font-size: 12.5px; }
  .vb-emp-times { font-size: 10px; }
}

/* ============================================================ */
/* DESKTOP (>= 1024px) */
/* ============================================================ */
@media (min-width: 1024px) {
  .vb-topbar { padding: 14px 28px; }
  .vb-topbar-meta { display: inline-block; }
  .vb-topbar-divider { display: block; }
  .vb-container { padding: 24px 28px 60px; max-width: 1480px; margin: 0 auto; }
  .vb-page-head { padding-bottom: 16px; margin-bottom: 22px; }
  .vb-page-head h1 { font-size: 26px; }
  .vb-stats { grid-template-columns: repeat(5, 1fr); margin-bottom: 22px; }
  .vb-stat { padding: 17px 20px; border-right: 1px solid var(--border-soft);
    border-bottom: none; }
  .vb-stat:nth-child(5n) { border-right: none; }
  .vb-stat:nth-child(3n) { border-right: 1px solid var(--border-soft); }
  .vb-stat:last-child { border-right: none; }
  .vb-stat-value { font-size: 30px; }
  .vb-legend { margin-bottom: 22px; padding: 11px 20px; }
  .vb-store { margin-bottom: 20px; }
  .vb-store-head { padding: 16px 22px; }
  .vb-store-title { font-size: 18px; }
  .vb-store-meta strong { font-size: 14px; }
  .vb-store-scroll { overflow-x: visible; }
  .vb-timeline-head, .vb-emp { grid-template-columns: 240px 1fr; min-width: 0; }
  .vb-timeline-head-left { padding: 8px 22px; position: static; }
  .vb-emp-info { padding: 14px 18px 14px 22px; position: static; }
  .vb-emp:hover .vb-emp-info { background: transparent; }
  .vb-avatar { width: 34px; height: 34px; font-size: 12px; }
  .vb-emp-name { font-size: 13px; }
  .vb-emp-times { font-size: 10.5px; flex-wrap: nowrap; }
  .vb-bar-wrap { padding: 22px 0; }
  .vb-bar-track { height: 28px; }
  .vb-bar { font-size: 9.5px; padding: 0 9px; }
  .vb-foot { margin-top: 32px; padding-top: 22px; }
}

/* ============================================================ */
/* LARGE TV (>= 1600px) */
/* ============================================================ */
@media (min-width: 1600px) {
  html, body { font-size: 14px; }
  .vb-container { max-width: 1800px; padding: 32px 40px 70px; }
  .vb-page-head h1 { font-size: 32px; }
  .vb-page-date { font-size: 12px; }
  .vb-stat { padding: 20px 24px; }
  .vb-stat-value { font-size: 34px; }
  .vb-stat-label { font-size: 10.5px; }
  .vb-store-title { font-size: 20px; }
  .vb-store-meta strong { font-size: 16px; }
  .vb-timeline-head, .vb-emp { grid-template-columns: 280px 1fr; }
  .vb-avatar { width: 38px; height: 38px; font-size: 13px; }
  .vb-emp-name { font-size: 14px; }
  .vb-emp-times { font-size: 11.5px; }
  .vb-bar { font-size: 10.5px; }
  .vb-hour { font-size: 11px; }
}
</style>
"""


# ---------------------------------------------------------------------------
# Render: topbar
# ---------------------------------------------------------------------------

def render_topbar(user_name, user_role):
    initials = "".join([p[0] for p in user_name.split()[:2]]).upper() or "?"
    return f"""
<div class="vb-topbar">
  <div class="vb-brand">
    <div class="vb-logo">{LOGO_SMALL_SVG}</div>
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
# Render: stats
# ---------------------------------------------------------------------------

def render_stats(stats):
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
    <div class="vb-stat-detail"><span class="vb-stat-dot" style="background:var(--permission)"></span>permiso · vacaciones</div>
  </div>
</div>
"""


def render_legend():
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
# Timeline helpers
# ---------------------------------------------------------------------------

def compute_timeline_range(employees_by_store, default_start_hour=5, default_end_hour=22):
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
    start_h = max(5, (earliest // 60))
    end_h = min(23, ((latest + 59) // 60))
    if end_h - start_h < 8:
        end_h = start_h + 8
    return start_h, end_h


def render_hour_labels(start_h, end_h, now_minutes):
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
        pct_val = (now_minutes - start_h * 60) / (total_hours * 60) * 100
        now_tag = f'<div class="vb-now-tag" style="left: {pct_val:.2f}%;">AHORA · {fmt_time_12h(now_minutes)}</div>'
    return f'<div class="vb-hours" style="grid-template-columns: {grid_cols};">{"".join(cells)}{now_tag}</div>'


def pct(minutes, start_h, end_h):
    total = (end_h - start_h) * 60
    return (minutes - start_h * 60) / total * 100


# ---------------------------------------------------------------------------
# Employee color assignment (deterministic by name)
# ---------------------------------------------------------------------------

EMPLOYEE_COLORS = [
    ("#1B7340", "#D1FADF"),  # forest green
    ("#1D4ED8", "#DBEAFE"),  # royal blue
    ("#B5390C", "#FEE4D6"),  # terracotta
    ("#6D28D9", "#EDE9FE"),  # purple
    ("#0891B2", "#CFFAFE"),  # cyan
    ("#C9982A", "#FEF3C7"),  # gold
    ("#BE185D", "#FCE7F3"),  # magenta
    ("#047857", "#D1FAE5"),  # emerald
    ("#4338CA", "#E0E7FF"),  # indigo
    ("#9F1239", "#FECDD3"),  # rose
]


def color_for_name(name):
    """Return (foreground, background) tuple — same color every time for the same name."""
    h = sum(ord(c) for c in (name or "").upper())
    return EMPLOYEE_COLORS[h % len(EMPLOYEE_COLORS)]


# ---------------------------------------------------------------------------
# Render: employee row
# ---------------------------------------------------------------------------

def render_employee_row(emp, start_h, end_h, now_minutes):
    name = emp.get("name", "")
    initials = "".join([p[0] for p in name.split()[:2]]).upper() or "?"
    status = emp.get("status", "working")
    fg_color, bg_color = color_for_name(name)
    avatar_style = f"background:{bg_color};color:{fg_color};border-color:{bg_color};"

    # Support badge — when employee is working at a non-default store
    is_support = emp.get("is_support", False)
    support_badge = (
        '<span class="vb-support-badge">🔀 Apoyo</span>' if is_support else ""
    )

    total_hours = end_h - start_h
    half_step = f"calc((100% / {total_hours * 2}))"
    hour_step = f"calc((100% / {total_hours}))"

    now_line = ""
    if now_minutes is not None and start_h * 60 <= now_minutes <= end_h * 60:
        now_pct = pct(now_minutes, start_h, end_h)
        now_line = f'<div class="vb-now-line" style="left: {now_pct:.2f}%;"></div>'

    if status == "working":
        ss = parse_time(emp.get("shift_start"))
        se = parse_time(emp.get("shift_end"))
        ls = parse_time(emp.get("lunch_start"))
        le = parse_time(emp.get("lunch_end"))
        overtime_min = emp.get("overtime_minutes") or 0
        is_late = emp.get("is_late", False)
        actual_start = parse_time(emp.get("actual_start"))

        total_min = 0
        if ss is not None and se is not None:
            total_min = se - ss
            if ls is not None and le is not None:
                total_min -= (le - ls)
        worked_label = fmt_duration(total_min)
        extra_label = f" + {fmt_duration(overtime_min)} extra" if overtime_min else ""

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

        bars_html = []
        if ss is not None and se is not None:
            effective_start = actual_start if (is_late and actual_start) else ss
            if ls is not None and le is not None and ls > effective_start and le < se:
                left = pct(effective_start, start_h, end_h)
                width = pct(ls, start_h, end_h) - left
                if width > 0:
                    bars_html.append(
                        f'<div class="vb-bar working" style="left: {left:.2f}%; width: {width:.2f}%;">{fmt_time_12h(effective_start)}</div>'
                    )
                left = pct(ls, start_h, end_h)
                width = pct(le, start_h, end_h) - left
                # Adaptive label: short bars get shorter/no text
                if width >= 4.5:
                    lunch_label = "Almuerzo"
                elif width >= 2.5:
                    lunch_label = "Alm"
                else:
                    lunch_label = ""
                bars_html.append(
                    f'<div class="vb-bar lunch" style="left: {left:.2f}%; width: {width:.2f}%;">{lunch_label}</div>'
                )
                left = pct(le, start_h, end_h)
                width = pct(se, start_h, end_h) - left
                bars_html.append(
                    f'<div class="vb-bar working" style="left: {left:.2f}%; width: {width:.2f}%; justify-content: flex-end;">Sale {fmt_time_12h(se)}</div>'
                )
            else:
                left = pct(effective_start, start_h, end_h)
                width = pct(se, start_h, end_h) - left
                bars_html.append(
                    f'<div class="vb-bar working" style="left: {left:.2f}%; width: {width:.2f}%;">{fmt_time_12h(effective_start)} → {fmt_time_12h(se)}</div>'
                )
            if overtime_min:
                left = pct(se, start_h, end_h)
                width = pct(se + overtime_min, start_h, end_h) - left
                if width > 0:
                    bars_html.append(
                        f'<div class="vb-bar overtime" style="left: {left:.2f}%; width: {width:.2f}%;">+ Extra</div>'
                    )
            if is_late:
                bars_html.append('<div class="vb-late-flag">Tarde</div>')

        return f"""
<div class="vb-emp">
  <div class="vb-emp-info">
    <div class="vb-avatar" style="{avatar_style}">{initials}</div>
    <div class="vb-emp-meta">
      <div class="vb-emp-name">{name}{support_badge}</div>
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
    <div class="vb-avatar" style="{avatar_style}">{initials}</div>
    <div class="vb-emp-meta">
      <div class="vb-emp-name">{name}{support_badge}</div>
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


def render_store(title, marker, employees, start_h, end_h, now_minutes, date_label=""):
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

    date_html = f'<span class="vb-store-date">{date_label}</span>' if date_label else ''

    return f"""
<div class="vb-store">
  <div class="vb-store-head">
    <div class="vb-store-head-left">
      <span class="vb-store-marker">{marker}</span>
      <div class="vb-store-title">Tienda {title}</div>
      {date_html}
    </div>
    <div class="vb-store-meta">Horas programadas<strong>{fmt_duration(total_min)}</strong></div>
  </div>
  <div class="vb-store-scroll">
    <div class="vb-timeline-head">
      <div class="vb-timeline-head-left">Personal</div>
      {render_hour_labels(start_h, end_h, now_minutes)}
    </div>
    {rows_html}
  </div>
</div>
"""


# ---------------------------------------------------------------------------
# Render: full dashboard
# ---------------------------------------------------------------------------

def render_dashboard_body(data, user_name="Lic. Juan Orozco", user_role="Gerencia"):
    """Render only the HTML body (no CSS). For use with st.html() so Streamlit
    doesn't try to markdown-parse the content."""
    date_display = data.get("date_display", "")
    date_label = data.get("date_label", "")
    now_minutes = data.get("now_minutes")
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
            date_label=date_label,
        )
        for s in stores
    )

    page_head = (
        '<div class="vb-page-head"><div>'
        '<div class="vb-eyebrow">Vista diaria</div>'
        '<h1>Asistencia</h1>'
        f'<div class="vb-page-date">{date_display}</div>'
        '</div></div>'
    )

    foot = (
        '<div class="vb-foot">'
        '<div class="vb-foot-dot">· ✦ ·</div>'
        '<div class="vb-foot-text">Vintage Boutique</div>'
        '</div>'
    )

    return (
        '<div class="vb-app">'
        + render_topbar(user_name, user_role)
        + '<div class="vb-container">'
        + page_head
        + render_stats(stats)
        + render_legend()
        + stores_html
        + foot
        + '</div></div>'
    )


def render_dashboard(data, user_name="Lic. Juan Orozco", user_role="Gerencia"):
    """Full dashboard HTML including CSS (for standalone preview generation)."""
    return CSS + render_dashboard_body(data, user_name, user_role)
