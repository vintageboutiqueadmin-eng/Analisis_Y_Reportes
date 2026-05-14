"""
Daily attendance capture form for Marisol.

UI:
  - Single flat list of all active employees, alphabetical
  - Each row is a collapsible st.expander
  - Collapsed rows already saved show: name + status badge + horario resumido + tienda(s)
  - Unsaved rows are auto-expanded
  - When status="working", a toggle "🔀 Trabajo dividido en 2 tiendas" reveals
    a second segment with its own store + entrada/salida
  - Lunch is single (lives within one of the segments — Marisol's call)
"""

from __future__ import annotations

import datetime as dt
from zoneinfo import ZoneInfo

import streamlit as st

from . import sheets
from .dashboard_html import color_for_name


GT_TZ = ZoneInfo("America/Guatemala")


STATUS_OPTIONS = [
    ("working",    "✅  Trabajando"),
    ("day_off",    "💤  Día libre"),
    ("permission", "📋  Permiso / No llegó"),
    ("vacation",   "🏖️  Vacaciones"),
    ("sick",       "🤒  Enfermo"),
]
STATUS_LABEL = dict(STATUS_OPTIONS)
STATUS_KEYS = [k for k, _ in STATUS_OPTIONS]

STATUS_BADGE = {
    "working":    ("#1B7340", "#D1FADF", "TRABAJANDO"),
    "day_off":    ("#6C7280", "#E8EAEE", "DÍA LIBRE"),
    "permission": ("#1D4ED8", "#DBEAFE", "PERMISO"),
    "vacation":   ("#0891B2", "#CFFAFE", "VACACIONES"),
    "sick":       ("#7C2D12", "#FECACA", "ENFERMO"),
}

STATUS_HINT = {
    "working":    "Si llegó tarde o salió antes, ajusta las horas abajo.",
    "day_off":    "Era su día de descanso programado (no le tocaba trabajar).",
    "permission": "Úsalo cuando: fue al doctor, asunto familiar, no se presentó, o cualquier ausencia justificada.",
    "vacation":   "Vacaciones acordadas previamente.",
    "sick":       "Llamó por enfermedad o tiene incapacidad médica.",
}


def _today_gt():
    return dt.datetime.now(GT_TZ).date()


def _inject_css():
    st.markdown(
        """
        <style>
        @import url('https://fonts.googleapis.com/css2?family=Geist:wght@300;400;500;600;700&display=swap');
        html, body, [class*="css"], button, input, select, textarea {
            font-family: 'Geist', system-ui, sans-serif !important;
        }
        #MainMenu, footer { visibility: hidden; }
        .block-container { padding-top: 1.5rem !important; max-width: 1100px !important; }

        .cap-header {
            background: #0B0F19; color: #F9FAFB; padding: 16px 24px;
            border-radius: 6px; margin-bottom: 16px;
            display: flex; justify-content: space-between; align-items: center;
        }
        .cap-header .ttl { font-size: 18px; font-weight: 600; letter-spacing: -0.2px; }
        .cap-header .sub {
            font-size: 10px; letter-spacing: 2.5px; text-transform: uppercase;
            color: #C9982A; font-weight: 600; margin-bottom: 2px;
        }

        .cap-guide {
            background: #FFFFFF; border: 1px solid #D8DCE2;
            border-left: 3px solid #C9982A;
            padding: 16px 20px; border-radius: 4px; margin-bottom: 20px;
            font-size: 13px; color: #3D4554; line-height: 1.7;
        }
        .cap-guide strong { color: #0B0F19; }
        .cap-guide .ttl {
            font-size: 11px; letter-spacing: 2px; text-transform: uppercase;
            color: #0B0F19; font-weight: 700; margin-bottom: 10px;
        }
        .cap-guide ul { margin: 6px 0 4px 0; padding-left: 22px; }
        .cap-guide li { margin-bottom: 4px; }

        /* Streamlit expander header — flat, executive look */
        details[data-testid="stExpander"] {
            border: 1px solid #D8DCE2 !important;
            border-radius: 6px !important;
            background: #FFFFFF !important;
            margin-bottom: 8px !important;
        }
        details[data-testid="stExpander"] summary {
            padding: 12px 16px !important;
        }
        details[data-testid="stExpander"] summary:hover {
            background: #FAFBFC !important;
        }

        /* Radio horizontal pills */
        div[role="radiogroup"] { gap: 6px !important; flex-wrap: wrap !important; }
        div[role="radiogroup"] label {
            background: #F6F7F9; border: 1px solid #D8DCE2;
            border-radius: 4px; padding: 6px 12px 6px 8px !important;
            font-size: 12.5px !important; font-weight: 500;
            transition: all 0.12s ease; cursor: pointer;
        }
        div[role="radiogroup"] label:hover { border-color: #0B0F19; background: #FFFFFF; }
        div[role="radiogroup"] label[data-checked="true"] {
            background: #0B0F19 !important; border-color: #0B0F19 !important; color: #FFFFFF !important;
        }
        div[role="radiogroup"] label[data-checked="true"] p { color: #FFFFFF !important; }

        /* Segment box (for split shifts) */
        .seg-box {
            background: #FAFBFC; border: 1px solid #E8EBF0;
            border-radius: 6px; padding: 14px 16px; margin: 8px 0;
        }
        .seg-label {
            font-size: 10px; letter-spacing: 2px; text-transform: uppercase;
            color: #0B0F19; font-weight: 700; margin-bottom: 8px;
            display: flex; align-items: center; gap: 8px;
        }
        .seg-label .pill {
            background: #C9982A; color: #FFFFFF;
            padding: 2px 7px; border-radius: 3px; font-size: 9px;
            letter-spacing: 1.5px;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


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


def _format_date_helper(d):
    today = _today_gt()
    if d == today:
        return "(Hoy)"
    if d == today + dt.timedelta(days=1):
        return "(Mañana)"
    if d == today - dt.timedelta(days=1):
        return "(Ayer)"
    return ""


def _fmt_time(s):
    """Format '09:00' -> '9:00'"""
    if not s:
        return ""
    try:
        h, m = s.split(":")
        return f"{int(h)}:{m}"
    except Exception:
        return s


def _build_expander_summary(emp, rec, has_record, store_labels):
    """Build the expander title showing: name + status + horario resumido + tienda(s)."""
    name = emp["name"]
    home_store = store_labels.get(emp["store_id"], "?")

    if not has_record:
        return f"⭕  {name}  ·  SIN REGISTRO  ·  habitual: {home_store}"

    status = rec.get("status", "working")
    _color, _bg, label = STATUS_BADGE.get(status, STATUS_BADGE["day_off"])

    if status != "working":
        return f"●  {name}  ·  {label}  ·  habitual: {home_store}"

    # Working — show schedule + store(s)
    shift_split = bool(rec.get("shift_split"))
    s1_start = _fmt_time(rec.get("shift_start") or "")
    s1_end = _fmt_time(rec.get("shift_end") or "")
    s1_store = store_labels.get(rec.get("worked_store_id") or emp["store_id"], "?")
    # Short store labels
    s1_store_short = s1_store.replace("Tienda ", "").replace("Avenida", "Ave")

    if shift_split:
        s2_start = _fmt_time(rec.get("segment2_start") or "")
        s2_end = _fmt_time(rec.get("segment2_end") or "")
        s2_store = store_labels.get(rec.get("segment2_store_id") or "", "?")
        s2_store_short = s2_store.replace("Tienda ", "").replace("Avenida", "Ave")
        return (
            f"✅  {name}  ·  {s1_start}–{s1_end} ({s1_store_short})  "
            f"→  {s2_start}–{s2_end} ({s2_store_short})"
        )

    return f"✅  {name}  ·  {s1_start}–{s1_end} ({s1_store_short})"


def _render_emp_row(emp, rec, has_record, store_options, store_labels,
                    date, is_late_default, idx):
    """Render one employee inside an expander. Returns the record dict."""
    eid = emp["id"]
    initials = "".join([p[0] for p in emp["name"].split()[:2]]).upper() or "?"
    fg, bg = color_for_name(emp["name"])
    home_store_name = store_labels.get(emp["store_id"], "?")

    prev_status = rec.get("status", "working") if has_record else "working"

    # Header inside expander — avatar + name + home store + "Apoyo" badge live preview
    # Determine support state for live badge
    current_worked = st.session_state.get(f"store_{eid}", rec.get("worked_store_id") or emp["store_id"])
    if current_worked not in store_options:
        current_worked = emp["store_id"]
    is_support = (
        prev_status == "working"
        and current_worked != emp["store_id"]
    )
    support_html = (
        '<span style="display:inline-block;margin-left:8px;padding:2px 7px;'
        'background:#FFEDD5;color:#9A3412;font-size:9.5px;font-weight:700;'
        'letter-spacing:1.5px;border-radius:2px;text-transform:uppercase;">🔀 Apoyo</span>'
        if is_support else ""
    )

    st.markdown(
        f'<div style="display:flex;align-items:center;gap:12px;margin-bottom:10px;">'
        f'<div style="width:36px;height:36px;border-radius:50%;background:{bg};'
        f'color:{fg};display:grid;place-items:center;font-weight:700;font-size:12px;'
        f'font-family:Geist Mono,monospace;flex-shrink:0;">{initials}</div>'
        f'<div><div style="font-weight:600;font-size:14px;color:#0B0F19;">'
        f'{emp["name"]}{support_html}</div>'
        f'<div style="font-size:11px;color:#6C7280;">'
        f'Tienda habitual: <strong>{home_store_name}</strong></div></div>'
        f'</div>',
        unsafe_allow_html=True,
    )

    # Status pills
    st.markdown(
        "<div style='font-size:11px;letter-spacing:1.5px;text-transform:uppercase;"
        "color:#6C7280;font-weight:600;margin-bottom:4px;'>"
        "Estado del día</div>",
        unsafe_allow_html=True,
    )
    status_idx = next((i for i, k in enumerate(STATUS_KEYS) if k == prev_status), 0)
    status_choice = st.radio(
        "Estado",
        STATUS_KEYS,
        format_func=lambda k: STATUS_LABEL[k],
        index=status_idx,
        horizontal=True,
        label_visibility="collapsed",
        key=f"status_{eid}",
    )

    st.markdown(
        f"<div style='margin:4px 0 14px;font-size:11.5px;color:#3D4554;"
        f"font-style:italic;padding-left:4px;'>"
        f"<span style='color:#C9982A;'>ℹ</span> {STATUS_HINT[status_choice]}</div>",
        unsafe_allow_html=True,
    )

    record = {
        "date": date.isoformat(),
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

    if status_choice != "working":
        placeholder_map = {
            "day_off":    "Ej. Descanso semanal programado",
            "permission": "Ej. Fue al doctor · Asunto familiar · No se presentó",
            "vacation":   "Ej. Vacaciones programadas",
            "sick":       "Ej. Gripe · Incapacidad por 3 días",
        }
        record["notes"] = st.text_input(
            "📝 Motivo / Nota",
            value=rec.get("notes", ""),
            key=f"notes_a_{eid}",
            placeholder=placeholder_map.get(status_choice, ""),
        )
        # Preserve existing worked_store_id for historical traceability
        record["worked_store_id"] = rec.get("worked_store_id", "") or ""
        return record

    # ====== STATUS = WORKING ======

    # Split-shift toggle
    split_default = bool(rec.get("shift_split"))
    shift_split = st.toggle(
        "🔀  Trabajo dividido en 2 tiendas",
        value=split_default,
        key=f"split_{eid}",
        help="Activa esto si el empleado trabajará una parte del día en una tienda "
             "y otra parte en la otra. Ej. 9:00–14:00 en 7ma y 14:00–19:00 en 6ta.",
    )
    record["shift_split"] = shift_split

    # Defaults for time inputs
    default_store = (rec.get("worked_store_id") or emp["store_id"])
    if default_store not in store_options:
        default_store = emp["store_id"]
    s1_store_idx = store_options.index(default_store)

    d_ss = dt.time(9, 0)
    d_se = dt.time(19, 0)
    d_ls = dt.time(13, 0)
    d_le = dt.time(14, 0)

    if shift_split:
        # ===== Segment 1 =====
        st.markdown(
            '<div class="seg-box">'
            '<div class="seg-label"><span class="pill">TRAMO 1</span>'
            'Primera parte del día</div></div>',
            unsafe_allow_html=True,
        )
        c1 = st.columns([2, 1, 1])
        chosen_store_1 = c1[0].selectbox(
            "🏪 Tienda — Tramo 1",
            store_options,
            format_func=lambda x: store_labels[x],
            index=s1_store_idx,
            key=f"store_{eid}",
        )
        ss_t = c1[1].time_input(
            "🕘 Entrada",
            value=_parse_t(rec.get("shift_start"), d_ss),
            key=f"ss_{eid}", step=1800,
        )
        se_t = c1[2].time_input(
            "🕖 Salida",
            value=_parse_t(rec.get("shift_end"), d_se),
            key=f"se_{eid}", step=1800,
        )

        # ===== Segment 2 =====
        st.markdown(
            '<div class="seg-box">'
            '<div class="seg-label"><span class="pill">TRAMO 2</span>'
            'Segunda parte del día</div></div>',
            unsafe_allow_html=True,
        )
        # Default for segment 2: the OTHER store
        other_store = next((s for s in store_options if s != chosen_store_1), store_options[0])
        prev_seg2_store = rec.get("segment2_store_id") or other_store
        if prev_seg2_store not in store_options:
            prev_seg2_store = other_store
        s2_store_idx = store_options.index(prev_seg2_store)

        c2 = st.columns([2, 1, 1])
        chosen_store_2 = c2[0].selectbox(
            "🏪 Tienda — Tramo 2",
            store_options,
            format_func=lambda x: store_labels[x],
            index=s2_store_idx,
            key=f"store2_{eid}",
        )
        s2_start_t = c2[1].time_input(
            "🕘 Entrada — Tramo 2",
            value=_parse_t(rec.get("segment2_start"), dt.time(14, 0)),
            key=f"s2s_{eid}", step=1800,
        )
        s2_end_t = c2[2].time_input(
            "🕖 Salida — Tramo 2",
            value=_parse_t(rec.get("segment2_end"), d_se),
            key=f"s2e_{eid}", step=1800,
        )

        record["worked_store_id"] = chosen_store_1
        record["segment2_store_id"] = chosen_store_2
        record["segment2_start"] = _time_or_none(s2_start_t)
        record["segment2_end"] = _time_or_none(s2_end_t)
    else:
        # ===== Single-shift =====
        c = st.columns([2, 1, 1])
        chosen_store = c[0].selectbox(
            "🏪 Tienda donde trabajará hoy",
            store_options,
            format_func=lambda x: store_labels[x],
            index=s1_store_idx,
            key=f"store_{eid}",
        )
        ss_t = c[1].time_input(
            "🕘 Entrada",
            value=_parse_t(rec.get("shift_start"), d_ss),
            key=f"ss_{eid}", step=1800,
        )
        se_t = c[2].time_input(
            "🕖 Salida",
            value=_parse_t(rec.get("shift_end"), d_se),
            key=f"se_{eid}", step=1800,
        )
        record["worked_store_id"] = chosen_store

    # Common: lunch + extras (apply for both single and split)
    cL = st.columns(2)
    ls_t = cL[0].time_input(
        "🍽 Almuerzo desde",
        value=_parse_t(rec.get("lunch_start"), d_ls),
        key=f"ls_{eid}", step=1800,
    )
    le_t = cL[1].time_input(
        "🍽 Almuerzo hasta",
        value=_parse_t(rec.get("lunch_end"), d_le),
        key=f"le_{eid}", step=1800,
    )
    if shift_split:
        st.caption(
            "ℹ️ El almuerzo cae dentro de uno de los tramos. La hora exacta lo determina."
        )

    cX = st.columns([1, 1, 2])
    ot = cX[0].number_input(
        "⏰ Hora extra (min)", min_value=0, max_value=600, step=15,
        value=int(rec.get("overtime_minutes") or 0),
        key=f"ot_{eid}",
    )
    is_late = cX[1].checkbox(
        "Llegada tarde",
        value=bool(rec.get("is_late", False)),
        key=f"late_{eid}",
    )
    actual_start_t = None
    if is_late:
        actual_start_t = cX[2].time_input(
            "Hora real de llegada",
            value=_parse_t(rec.get("actual_start"), ss_t),
            key=f"actstart_{eid}", step=900,
        )

    notes_val = st.text_input(
        "📝 Notas (opcional)",
        value=rec.get("notes", ""),
        key=f"notes_w_{eid}",
        placeholder="Ej. Llegó tarde por tráfico · Cambio de turno por enfermedad de Daisy",
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
    return record


def render(current_user: dict) -> None:
    _inject_css()

    st.markdown(
        f"""
        <div class="cap-header">
          <div>
            <div class="sub">● Vintage Boutique · Captura de Asistencia</div>
            <div class="ttl">Registro Diario</div>
          </div>
          <div style="text-align:right;font-size:11px;color:#9CA3AF;">
            <div style="color:#F9FAFB;font-weight:500;">{current_user['name']}</div>
            <div>{current_user['email']}</div>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.markdown(
        """
        <div class="cap-guide">
          <div class="ttl">💡 Guía rápida</div>
          <ul>
            <li><strong>Trabajando normal:</strong> elige <strong>✅ Trabajando</strong>, la tienda donde trabaja hoy, y los horarios.</li>
            <li><strong>Trabaja en 2 tiendas el mismo día:</strong> activa el toggle <strong>🔀 Trabajo dividido en 2 tiendas</strong>. Marisol llena los dos tramos.</li>
            <li><strong>Apoyo a otra tienda:</strong> simplemente cambia el dropdown <em>"Tienda"</em>. El sistema lo marca como 🔀 Apoyo automáticamente.</li>
            <li><strong>Día libre · Permiso · Vacaciones · Enfermo:</strong> selecciona el estado y escribe el motivo. No requiere tienda ni horarios.</li>
            <li><strong>Filas verdes (con registro):</strong> ya guardadas. Click para expandir si quieres modificar.</li>
            <li><strong>Filas grises (sin registro):</strong> auto-expandidas, te están esperando.</li>
          </ul>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # Date + reload
    col1, col2 = st.columns([1, 1])
    with col1:
        date = st.date_input(
            "Fecha",
            value=st.session_state.get("cap_date", _today_gt()),
            format="DD/MM/YYYY",
        )
        st.session_state.cap_date = date
        helper = _format_date_helper(date)
        if helper:
            st.caption(f"📅 {helper}")
    with col2:
        st.markdown("<div style='height:28px;'></div>", unsafe_allow_html=True)
        if st.button("↻ Recargar empleados", use_container_width=True):
            sheets.get_employees.clear()
            sheets.get_stores.clear()
            st.rerun()

    try:
        stores = sheets.get_stores()
        employees = sheets.get_employees()
    except Exception as e:
        st.error(f"No se pudieron cargar empleados/tiendas: `{e}`")
        return

    if not stores:
        st.warning(
            "No hay tiendas configuradas todavía. Pídele a Pablo que ejecute la "
            "inicialización desde la pestaña **Administración**."
        )
        return

    if not employees:
        st.info("No hay empleados activos. Agrégalos desde Administración.")
        return

    store_options = [s["id"] for s in stores]
    store_labels = {s["id"]: s["name"] for s in stores}

    try:
        existing = sheets.get_attendance_for_date(date.isoformat())
    except Exception as e:
        st.error(f"Error leyendo asistencia: `{e}`")
        return
    existing_by_emp = {r["employee_id"]: r for r in existing}

    employees_sorted = sorted(employees, key=lambda e: e["name"].lower())

    # Summary header
    total = len(employees_sorted)
    saved = sum(1 for e in employees_sorted if e["id"] in existing_by_emp)
    pending_count = total - saved
    st.markdown(
        f"<div style='margin:18px 0 10px;display:flex;justify-content:space-between;"
        f"align-items:baseline;flex-wrap:wrap;gap:8px;'>"
        f"<div style='font-size:11px;letter-spacing:2px;text-transform:uppercase;"
        f"color:#6C7280;font-weight:600;'>"
        f"Personal · {total} empleado(s) activo(s)</div>"
        f"<div style='font-size:11px;font-weight:600;'>"
        f"<span style='color:#1B7340;'>✓ {saved} registrados</span>"
        f"<span style='color:#9CA3AF;margin:0 8px;'>·</span>"
        f"<span style='color:#B42318;'>● {pending_count} pendiente(s)</span>"
        f"</div></div>",
        unsafe_allow_html=True,
    )

    pending = []

    for idx, emp in enumerate(employees_sorted):
        rec = existing_by_emp.get(emp["id"], {})
        has_record = bool(rec)

        # Build expander title
        title = _build_expander_summary(emp, rec, has_record, store_labels)

        # Auto-expand if no record yet
        expanded = not has_record

        with st.expander(title, expanded=expanded):
            record = _render_emp_row(
                emp, rec, has_record, store_options, store_labels,
                date, rec.get("is_late", False), idx,
            )
            pending.append(record)

    # Save
    st.markdown("---")
    save_cols = st.columns([3, 1])
    with save_cols[1]:
        if st.button(
            "💾 Guardar / Actualizar todos",
            use_container_width=True,
            type="primary",
        ):
            try:
                saved_n = 0
                for r in pending:
                    sheets.upsert_attendance(r, updated_by=current_user["email"])
                    saved_n += 1
                st.success(f"✓ Guardados {saved_n} registro(s) · {date.isoformat()}")
                st.balloons()
                sheets.get_attendance_for_date.clear()
            except Exception as e:
                st.error(f"Error al guardar: `{e}`")
    with save_cols[0]:
        st.caption(
            "Al guardar, se actualizan todos los empleados a la vez. "
            "Cambios reflejados al instante en el dashboard del Lic."
        )
