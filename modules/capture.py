"""
Daily attendance capture form for Marisol.

UX principles:
  - Show visually if there's already a saved record for each employee
  - Make it obvious that re-saving overwrites previous values
  - Common case (8h with 1h lunch) preset by default
"""

from __future__ import annotations

import datetime as dt
from zoneinfo import ZoneInfo

import streamlit as st

from . import sheets


GT_TZ = ZoneInfo("America/Guatemala")


STATUS_OPTIONS = [
    ("working",    "Trabajando"),
    ("day_off",    "Día libre"),
    ("permission", "Permiso / Falta justificada"),
    ("vacation",   "Vacaciones"),
    ("sick",       "Incapacidad / Enfermedad"),
]
STATUS_LABEL = dict(STATUS_OPTIONS)

# Badge color for each saved status (shown next to employee name)
STATUS_BADGE_COLOR = {
    "working":    ("#1B7340", "#D1FADF", "TRABAJANDO"),
    "day_off":    ("#6C7280", "#E8EAEE", "DÍA LIBRE"),
    "permission": ("#1D4ED8", "#DBEAFE", "PERMISO"),
    "vacation":   ("#0891B2", "#CFFAFE", "VACACIONES"),
    "sick":       ("#7C2D12", "#FECACA", "INCAPACIDAD"),
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

        .cap-tip {
            background: #FEF7E6; border: 1px solid #F0D78A;
            border-left: 3px solid #C9982A;
            padding: 12px 16px; border-radius: 4px; margin-bottom: 20px;
            font-size: 12.5px; color: #5C4515; line-height: 1.5;
        }
        .cap-tip strong { color: #0B0F19; }

        .emp-card-wrap { margin-bottom: 10px; }
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


def _render_badge(status_key: str, name: str, has_record: bool):
    """Render an employee name + status badge."""
    initials = "".join([p[0] for p in name.split()[:2]]).upper() or "?"
    if has_record:
        color, bg, label = STATUS_BADGE_COLOR.get(status_key, STATUS_BADGE_COLOR["day_off"])
        badge_html = (
            f'<span style="display:inline-block;padding:3px 8px;border-radius:3px;'
            f'background:{bg};color:{color};font-size:9.5px;font-weight:700;'
            f'letter-spacing:1.5px;margin-left:10px;vertical-align:middle;">✓ {label}</span>'
        )
        guide = '<span style="font-size:10.5px;color:#6C7280;margin-left:10px;">' \
                'modifica abajo para actualizar</span>'
    else:
        badge_html = (
            '<span style="display:inline-block;padding:3px 8px;border-radius:3px;'
            'background:#FEE4E2;color:#B42318;font-size:9.5px;font-weight:700;'
            'letter-spacing:1.5px;margin-left:10px;vertical-align:middle;">SIN REGISTRO</span>'
        )
        guide = ''

    return (
        '<div style="background:#fff;border:1px solid #D8DCE2;border-radius:6px;'
        'padding:14px 18px;margin-bottom:0;display:flex;align-items:center;gap:12px;">'
        f'<div style="width:36px;height:36px;border-radius:50%;background:#F6F7F9;'
        f'color:#3D4554;display:grid;place-items:center;font-weight:600;font-size:12px;'
        f'border:1px solid #D8DCE2;font-family:Geist Mono,monospace;flex-shrink:0;">'
        f'{initials}</div>'
        f'<div style="flex:1;"><div style="font-weight:600;font-size:14px;color:#0B0F19;'
        f'letter-spacing:-0.1px;">{name}{badge_html}</div>'
        f'<div style="font-size:11px;color:#6C7280;margin-top:2px;">{guide}</div></div>'
        '</div>'
    )


def render(current_user: dict) -> None:
    _inject_css()

    # Header strip
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

    # Tip banner — explains the correction flow clearly
    st.markdown(
        """
        <div class="cap-tip">
        💡 <strong>¿Cómo corregir un registro?</strong> Si un empleado no llegó,
        se fue temprano, o cambió algo durante el día — solo selecciona la
        misma fecha y tienda, cambia el <strong>estado</strong> (ej. de
        <em>Trabajando</em> a <em>Permiso</em>), agrega una nota explicativa
        y guarda. Los datos del mismo empleado/fecha se sobrescriben automáticamente.
        </div>
        """,
        unsafe_allow_html=True,
    )

    # ── Date + store selectors ──────────────────────────────────────
    col1, col2, col3 = st.columns([1, 1, 1])

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

    try:
        stores = sheets.get_stores()
        employees = sheets.get_employees()
    except Exception as e:
        st.error(f"No se pudieron cargar empleados/tiendas desde Google Sheets: `{e}`")
        return

    if not stores:
        st.warning(
            "No hay tiendas configuradas todavía. Pídele a Pablo que ejecute la "
            "inicialización desde la pestaña **Administración**."
        )
        return

    with col2:
        store_options = [s["id"] for s in stores]
        store_labels = {s["id"]: s["name"] for s in stores}
        idx = 0
        if st.session_state.get("cap_store") in store_options:
            idx = store_options.index(st.session_state["cap_store"])
        selected_store_id = st.selectbox(
            "Tienda",
            store_options,
            format_func=lambda x: store_labels[x],
            index=idx,
        )
        st.session_state.cap_store = selected_store_id

    with col3:
        st.markdown("<div style='height:28px;'></div>", unsafe_allow_html=True)
        if st.button("↻ Recargar empleados", use_container_width=True):
            sheets.get_employees.clear()
            sheets.get_stores.clear()
            st.rerun()

    # Existing records for that date
    try:
        existing = sheets.get_attendance_for_date(date.isoformat())
    except Exception as e:
        st.error(f"Error leyendo asistencia: `{e}`")
        return
    existing_by_emp = {r["employee_id"]: r for r in existing}

    # Employees in selected store
    store_emps = [e for e in employees if e["store_id"] == selected_store_id]
    if not store_emps:
        st.info(
            f"No hay empleados activos en **{store_labels[selected_store_id]}**. "
            "Agrégalos desde Administración."
        )
        return

    # Count summary
    saved_count = sum(1 for emp in store_emps if emp["id"] in existing_by_emp)

    st.markdown(
        f"<div style='margin:18px 0 12px;display:flex;justify-content:space-between;"
        f"align-items:baseline;'>"
        f"<div style='font-size:11px;letter-spacing:2px;text-transform:uppercase;"
        f"color:#6C7280;font-weight:600;'>"
        f"{len(store_emps)} empleados · {store_labels[selected_store_id]}</div>"
        f"<div style='font-size:11px;color:#1B7340;font-weight:600;'>"
        f"✓ {saved_count} con registro &nbsp;·&nbsp; "
        f"<span style='color:#B42318;'>{len(store_emps) - saved_count} pendiente"
        f"{'s' if (len(store_emps) - saved_count) != 1 else ''}</span></div>"
        f"</div>",
        unsafe_allow_html=True,
    )

    # ── Per-employee form ──────────────────────────────────────────
    pending = []

    for emp in store_emps:
        existing_rec = existing_by_emp.get(emp["id"], {})
        has_record = bool(existing_rec)
        prev_status = existing_rec.get("status", "working")
        status_idx = next(
            (i for i, (k, _) in enumerate(STATUS_OPTIONS) if k == prev_status), 0
        )

        st.markdown('<div class="emp-card-wrap">', unsafe_allow_html=True)
        st.markdown(
            _render_badge(prev_status if has_record else "", emp["name"], has_record),
            unsafe_allow_html=True,
        )

        cols = st.columns([2, 5])
        with cols[0]:
            status_choice = st.selectbox(
                "Estado",
                [k for k, _ in STATUS_OPTIONS],
                format_func=lambda k: STATUS_LABEL[k],
                index=status_idx,
                key=f"status_{emp['id']}",
            )

        record = {
            "date": date.isoformat(),
            "employee_id": emp["id"],
            "status": status_choice,
            "shift_start": None,
            "shift_end": None,
            "lunch_start": None,
            "lunch_end": None,
            "overtime_minutes": 0,
            "is_late": False,
            "actual_start": None,
            "notes": "",
        }

        with cols[1]:
            if status_choice == "working":
                d_ss = dt.time(10, 0)
                d_se = dt.time(19, 0)
                d_ls = dt.time(13, 0)
                d_le = dt.time(14, 0)

                sc = st.columns(4)
                ss_t = sc[0].time_input(
                    "Entrada",
                    value=_parse_t(existing_rec.get("shift_start"), d_ss),
                    key=f"ss_{emp['id']}", step=1800,
                )
                se_t = sc[1].time_input(
                    "Salida",
                    value=_parse_t(existing_rec.get("shift_end"), d_se),
                    key=f"se_{emp['id']}", step=1800,
                )
                ls_t = sc[2].time_input(
                    "Almuerzo desde",
                    value=_parse_t(existing_rec.get("lunch_start"), d_ls),
                    key=f"ls_{emp['id']}", step=1800,
                )
                le_t = sc[3].time_input(
                    "Almuerzo hasta",
                    value=_parse_t(existing_rec.get("lunch_end"), d_le),
                    key=f"le_{emp['id']}", step=1800,
                )

                extra_cols = st.columns([1, 1, 2])
                ot = extra_cols[0].number_input(
                    "Hora extra (min)", min_value=0, max_value=600, step=15,
                    value=int(existing_rec.get("overtime_minutes") or 0),
                    key=f"ot_{emp['id']}",
                )
                is_late = extra_cols[1].checkbox(
                    "Llegada tarde",
                    value=bool(existing_rec.get("is_late", False)),
                    key=f"late_{emp['id']}",
                )
                actual_start_t = None
                if is_late:
                    actual_start_t = extra_cols[2].time_input(
                        "Hora real de llegada",
                        value=_parse_t(existing_rec.get("actual_start"), ss_t),
                        key=f"actstart_{emp['id']}", step=900,
                    )

                notes_val = st.text_input(
                    "Notas (opcional)",
                    value=existing_rec.get("notes", ""),
                    key=f"notes_w_{emp['id']}",
                    placeholder="Ej. Llegó tarde por tráfico",
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
                placeholder_map = {
                    "day_off": "Ej. Descanso semanal acordado",
                    "permission": "Ej. Fue al doctor · Cita médica · Asunto familiar",
                    "vacation": "Ej. Vacaciones programadas",
                    "sick": "Ej. Enfermedad respiratoria · Reposo médico 3 días",
                }
                record["notes"] = st.text_input(
                    "Nota / Motivo",
                    value=existing_rec.get("notes", ""),
                    key=f"notes_a_{emp['id']}",
                    placeholder=placeholder_map.get(status_choice, ""),
                )

        pending.append(record)
        st.markdown("</div>", unsafe_allow_html=True)
        st.markdown("<div style='height:8px;'></div>", unsafe_allow_html=True)

    # ── Save ────────────────────────────────────────────────────────
    st.markdown("---")
    save_cols = st.columns([3, 1])
    with save_cols[1]:
        if st.button(
            "💾 Guardar / Actualizar",
            use_container_width=True,
            type="primary",
        ):
            try:
                for rec in pending:
                    sheets.upsert_attendance(rec, updated_by=current_user["email"])
                st.success(
                    f"✓ Asistencia guardada para {len(pending)} empleados "
                    f"· {store_labels[selected_store_id]} · {date.isoformat()}"
                )
                st.balloons()
                # Force a refresh so badges show the updated state
                sheets.get_attendance_for_date.clear()
            except Exception as e:
                st.error(f"Error al guardar: `{e}`")

    with save_cols[0]:
        st.caption(
            "Se guardarán **todos** los registros mostrados arriba. "
            "Modificar y volver a guardar **sobrescribe** los datos del mismo empleado/fecha."
        )
