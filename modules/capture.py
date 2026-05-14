"""
Daily attendance capture form for Marisol.

Key change: employees can be assigned to ANY store on a given day,
not just their default store. The "Tienda" selector at the top determines
the store for THIS day's shift. Each employee's row shows a small "APOYO"
badge if they're being scheduled outside their default store.

Schema:
  - employees.store_id     → default store ("tienda principal")
  - attendance.worked_store_id → store where they actually worked that day
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

STATUS_BADGE_COLOR = {
    "working":    ("#1B7340", "#D1FADF", "TRABAJANDO"),
    "day_off":    ("#6C7280", "#E8EAEE", "DÍA LIBRE"),
    "permission": ("#1D4ED8", "#DBEAFE", "PERMISO"),
    "vacation":   ("#0891B2", "#CFFAFE", "VACACIONES"),
    "sick":       ("#7C2D12", "#FECACA", "ENFERMO"),
}

STATUS_HINT = {
    "working":    "Si llegó tarde o salió antes, ajusta las horas abajo. Lo demás queda igual.",
    "day_off":    "Era su día de descanso programado (no le tocaba trabajar).",
    "permission": "Úsalo cuando: fue al doctor, asunto familiar, no se presentó, o cualquier ausencia justificada. Anota el motivo.",
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
            display: flex; align-items: center; gap: 8px;
        }
        .cap-guide ul { margin: 6px 0 4px 0; padding-left: 22px; }
        .cap-guide li { margin-bottom: 4px; }

        .emp-card-wrap { margin-bottom: 6px; }

        /* Group header inside employee list */
        .emp-group-header {
            margin: 24px 0 12px;
            padding: 8px 0;
            border-bottom: 1px solid #D8DCE2;
            display: flex;
            align-items: center;
            gap: 10px;
        }
        .emp-group-header .label {
            font-size: 11px;
            letter-spacing: 2px;
            text-transform: uppercase;
            color: #0B0F19;
            font-weight: 700;
        }
        .emp-group-header .count {
            font-size: 10px;
            color: #6C7280;
            font-family: 'Geist Mono', monospace;
        }
        .emp-group-header .pill {
            font-size: 9px;
            font-weight: 700;
            letter-spacing: 1.5px;
            padding: 2px 7px;
            border-radius: 3px;
            text-transform: uppercase;
        }
        .emp-group-header .pill.home {
            background: #D1FADF; color: #15803D;
        }
        .emp-group-header .pill.support {
            background: #FFEDD5; color: #9A3412;
        }

        /* Streamlit's radio horizontal — pills */
        div[role="radiogroup"] {
            gap: 6px !important;
            flex-wrap: wrap !important;
        }
        div[role="radiogroup"] label {
            background: #F6F7F9;
            border: 1px solid #D8DCE2;
            border-radius: 4px;
            padding: 6px 12px 6px 8px !important;
            font-size: 12.5px !important;
            font-weight: 500;
            transition: all 0.12s ease;
            cursor: pointer;
        }
        div[role="radiogroup"] label:hover {
            border-color: #0B0F19;
            background: #FFFFFF;
        }
        div[role="radiogroup"] label[data-checked="true"] {
            background: #0B0F19 !important;
            border-color: #0B0F19 !important;
            color: #FFFFFF !important;
        }
        div[role="radiogroup"] label[data-checked="true"] p {
            color: #FFFFFF !important;
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


def _render_emp_card(status_key, name, has_record, is_support):
    """Render an employee name + status badge in a card."""
    initials = "".join([p[0] for p in name.split()[:2]]).upper() or "?"
    fg, bg = color_for_name(name)

    support_badge = ""
    if is_support:
        support_badge = (
            '<span style="display:inline-block;padding:3px 8px;border-radius:3px;'
            'background:#FFEDD5;color:#9A3412;font-size:9.5px;font-weight:700;'
            'letter-spacing:1.5px;margin-left:8px;vertical-align:middle;">🔀 APOYO</span>'
        )

    if has_record:
        color, bg_badge, label = STATUS_BADGE_COLOR.get(status_key, STATUS_BADGE_COLOR["day_off"])
        status_badge = (
            f'<span style="display:inline-block;padding:3px 8px;border-radius:3px;'
            f'background:{bg_badge};color:{color};font-size:9.5px;font-weight:700;'
            f'letter-spacing:1.5px;margin-left:10px;vertical-align:middle;">✓ {label}</span>'
        )
        guide = 'modifica abajo si necesitas actualizar'
    else:
        status_badge = (
            '<span style="display:inline-block;padding:3px 8px;border-radius:3px;'
            'background:#FEE4E2;color:#B42318;font-size:9.5px;font-weight:700;'
            'letter-spacing:1.5px;margin-left:10px;vertical-align:middle;">SIN REGISTRO</span>'
        )
        guide = 'selecciona el estado del día y guarda'

    return (
        '<div style="background:#fff;border:1px solid #D8DCE2;border-radius:6px;'
        'padding:14px 18px;display:flex;align-items:center;gap:12px;">'
        f'<div style="width:38px;height:38px;border-radius:50%;background:{bg};'
        f'color:{fg};display:grid;place-items:center;font-weight:700;font-size:12.5px;'
        f'border:1px solid {bg};font-family:Geist Mono,monospace;flex-shrink:0;'
        f'letter-spacing:0.3px;">{initials}</div>'
        f'<div style="flex:1;"><div style="font-weight:600;font-size:14px;color:#0B0F19;'
        f'letter-spacing:-0.1px;">{name}{support_badge}{status_badge}</div>'
        f'<div style="font-size:11px;color:#6C7280;margin-top:2px;">{guide}</div></div>'
        '</div>'
    )


def _render_employee_form(emp, existing_rec, has_record, is_support,
                          selected_store_id, date, prev_status_idx):
    """Render the form for a single employee. Returns the record dict."""
    st.markdown('<div class="emp-card-wrap">', unsafe_allow_html=True)
    st.markdown(
        _render_emp_card(
            existing_rec.get("status", "") if has_record else "",
            emp["name"], has_record, is_support,
        ),
        unsafe_allow_html=True,
    )

    st.markdown(
        "<div style='margin: 12px 0 4px; font-size: 11px; letter-spacing: 1.5px; "
        "text-transform: uppercase; color: #6C7280; font-weight: 600;'>"
        "Estado del día</div>",
        unsafe_allow_html=True,
    )
    status_choice = st.radio(
        "Estado del día",
        STATUS_KEYS,
        format_func=lambda k: STATUS_LABEL[k],
        index=prev_status_idx,
        horizontal=True,
        label_visibility="collapsed",
        key=f"status_{emp['id']}",
    )

    st.markdown(
        f"<div style='margin:-4px 0 12px;font-size:11.5px;color:#3D4554;"
        f"font-style:italic;padding-left:4px;'>"
        f"<span style='color:#C9982A;'>ℹ</span> {STATUS_HINT[status_choice]}</div>",
        unsafe_allow_html=True,
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
        "worked_store_id": selected_store_id if status_choice == "working" else "",
    }

    if status_choice == "working":
        d_ss = dt.time(9, 0)
        d_se = dt.time(19, 0)
        d_ls = dt.time(13, 0)
        d_le = dt.time(14, 0)

        sc = st.columns(4)
        ss_t = sc[0].time_input(
            "🕘 Entrada",
            value=_parse_t(existing_rec.get("shift_start"), d_ss),
            key=f"ss_{emp['id']}", step=1800,
        )
        se_t = sc[1].time_input(
            "🕖 Salida",
            value=_parse_t(existing_rec.get("shift_end"), d_se),
            key=f"se_{emp['id']}", step=1800,
        )
        ls_t = sc[2].time_input(
            "🍽 Almuerzo desde",
            value=_parse_t(existing_rec.get("lunch_start"), d_ls),
            key=f"ls_{emp['id']}", step=1800,
        )
        le_t = sc[3].time_input(
            "🍽 Almuerzo hasta",
            value=_parse_t(existing_rec.get("lunch_end"), d_le),
            key=f"le_{emp['id']}", step=1800,
        )

        extra_cols = st.columns([1, 1, 2])
        ot = extra_cols[0].number_input(
            "⏰ Hora extra (min)", min_value=0, max_value=600, step=15,
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
            "📝 Notas (opcional)",
            value=existing_rec.get("notes", ""),
            key=f"notes_w_{emp['id']}",
            placeholder="Ej. Llegó tarde por tráfico · Salió temprano por cita",
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
            "day_off":    "Ej. Descanso semanal programado",
            "permission": "Ej. Fue al doctor · Cita médica · Asunto familiar · No se presentó",
            "vacation":   "Ej. Vacaciones programadas (inicio: X / fin: Y)",
            "sick":       "Ej. Gripe · Incapacidad por 3 días · Cita médica",
        }
        record["notes"] = st.text_input(
            "📝 Motivo / Nota",
            value=existing_rec.get("notes", ""),
            key=f"notes_a_{emp['id']}",
            placeholder=placeholder_map.get(status_choice, ""),
        )

    st.markdown("</div>", unsafe_allow_html=True)
    st.markdown(
        "<hr style='margin:18px 0 18px;border:none;border-top:1px solid #EBEEF2;'>",
        unsafe_allow_html=True,
    )
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
          <div class="ttl">💡 Guía rápida — Cómo registrar cada caso</div>
          <ul>
            <li><strong>Trabajando normal:</strong> selecciona <strong>✅ Trabajando</strong>, ajusta horas si es necesario.</li>
            <li><strong>Llegó tarde:</strong> mantén <strong>✅ Trabajando</strong> y marca <em>"Llegada tarde"</em> abajo.</li>
            <li><strong>Salió antes:</strong> mantén <strong>✅ Trabajando</strong> y cambia la hora de <em>Salida</em>.</li>
            <li><strong>No llegó / fue al doctor / asunto personal:</strong> selecciona <strong>📋 Permiso</strong> y escribe el motivo.</li>
            <li><strong>Enfermo / incapacidad:</strong> selecciona <strong>🤒 Enfermo</strong>.</li>
            <li><strong>Día libre / descanso programado:</strong> selecciona <strong>💤 Día libre</strong>.</li>
            <li><strong>Vacaciones:</strong> selecciona <strong>🏖️ Vacaciones</strong>.</li>
            <li><strong>Apoyo a otra tienda:</strong> elige la tienda donde trabajará arriba — el sistema detecta y marca como <em>APOYO</em> si no es su tienda habitual.</li>
          </ul>
          <div style="margin-top:8px;font-size:12px;color:#6C7280;">
            <strong>Para corregir un registro ya guardado:</strong> cambia los valores y vuelve a guardar.
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # Date + store selectors
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
        st.error(f"No se pudieron cargar empleados/tiendas: `{e}`")
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
            "Tienda donde trabajarán hoy",
            store_options,
            format_func=lambda x: store_labels[x],
            index=idx,
            help="Todos los empleados que registres aquí quedarán asignados a esta tienda "
                 "para este día. Si alguno es de la otra tienda, se mostrará como 'Apoyo'.",
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

    # ALL active employees — split into "home" and "support" relative to selected store
    if not employees:
        st.info(
            "No hay empleados activos en el sistema. "
            "Agrégalos desde Administración."
        )
        return

    home_emps = [e for e in employees if e["store_id"] == selected_store_id]
    support_emps = [e for e in employees if e["store_id"] != selected_store_id]
    # Sort each alphabetically
    home_emps.sort(key=lambda e: e["name"].lower())
    support_emps.sort(key=lambda e: e["name"].lower())

    # Summary header
    saved_count = sum(
        1 for emp in employees
        if emp["id"] in existing_by_emp
        and existing_by_emp[emp["id"]].get("worked_store_id") == selected_store_id
    )
    total_for_this_store = len(home_emps)

    st.markdown(
        f"<div style='margin:18px 0 4px;display:flex;justify-content:space-between;"
        f"align-items:baseline;flex-wrap:wrap;gap:8px;'>"
        f"<div style='font-size:11px;letter-spacing:2px;text-transform:uppercase;"
        f"color:#6C7280;font-weight:600;'>"
        f"{store_labels[selected_store_id]} · personal habitual: {total_for_this_store}</div>"
        f"<div style='font-size:11px;color:#1B7340;font-weight:600;'>"
        f"✓ {saved_count} ya registrados para esta tienda hoy</div>"
        f"</div>",
        unsafe_allow_html=True,
    )

    # ============== Group 1: Personal habitual de esta tienda ==============
    st.markdown(
        f'<div class="emp-group-header">'
        f'<span class="pill home">PERSONAL HABITUAL</span>'
        f'<span class="label">{store_labels[selected_store_id]}</span>'
        f'<span class="count">· {len(home_emps)} empleado(s)</span>'
        f'</div>',
        unsafe_allow_html=True,
    )

    pending = []

    for emp in home_emps:
        existing_rec = existing_by_emp.get(emp["id"], {})
        has_record = bool(existing_rec)
        prev_status = existing_rec.get("status", "working")
        status_idx = next(
            (i for i, k in enumerate(STATUS_KEYS) if k == prev_status), 0
        )
        record = _render_employee_form(
            emp, existing_rec, has_record,
            is_support=False,
            selected_store_id=selected_store_id,
            date=date,
            prev_status_idx=status_idx,
        )
        pending.append(record)

    # ============== Group 2: Personal de apoyo (otra tienda) ==============
    if support_emps:
        # Determine the OTHER store name
        other_store_label = next(
            (s["name"] for s in stores if s["id"] != selected_store_id), "Otra tienda"
        )
        st.markdown(
            f'<div class="emp-group-header">'
            f'<span class="pill support">APOYO</span>'
            f'<span class="label">Personal de {other_store_label}</span>'
            f'<span class="count">· {len(support_emps)} disponible(s)</span>'
            f'</div>',
            unsafe_allow_html=True,
        )

        st.caption(
            f"💡 Estos empleados son de {other_store_label}. "
            f"Si **algún** empleado de la otra tienda apoyó en {store_labels[selected_store_id]} hoy, "
            "selecciona 'Trabajando' y registra sus horarios. Si no apoyó, **déjalo en blanco** "
            "(no necesitas marcarle 'día libre' aquí — ese registro lo haces cuando captures su tienda)."
        )

        with st.expander(
            f"Mostrar {len(support_emps)} empleado(s) de {other_store_label}",
            expanded=False,
        ):
            for emp in support_emps:
                existing_rec = existing_by_emp.get(emp["id"], {})
                has_record = bool(existing_rec)
                worked_here = existing_rec.get("worked_store_id") == selected_store_id

                # Only show as "has_record" relative to THIS store's view
                # if their worked_store_id matches THIS store
                effective_has_record = has_record and worked_here

                prev_status = existing_rec.get("status", "working") if worked_here else "working"
                status_idx = next(
                    (i for i, k in enumerate(STATUS_KEYS) if k == prev_status), 0
                )

                record = _render_employee_form(
                    emp,
                    existing_rec if worked_here else {},
                    effective_has_record,
                    is_support=True,
                    selected_store_id=selected_store_id,
                    date=date,
                    prev_status_idx=status_idx,
                )
                pending.append(record)

    # Save
    st.markdown("---")
    save_cols = st.columns([3, 1])
    with save_cols[1]:
        if st.button(
            "💾 Guardar / Actualizar",
            use_container_width=True,
            type="primary",
        ):
            try:
                saved_n = 0
                for rec in pending:
                    # SKIP support employees that don't have a working status AND
                    # were never recorded at this store. We only persist explicit
                    # decisions to avoid wiping out their record in the other store.
                    existing = existing_by_emp.get(rec["employee_id"], {})
                    came_from_other_store = (
                        existing
                        and existing.get("worked_store_id")
                        and existing.get("worked_store_id") != selected_store_id
                    )
                    is_support_emp = any(
                        e["id"] == rec["employee_id"] and e["store_id"] != selected_store_id
                        for e in employees
                    )

                    # If support employee with no working status and no prior record at THIS store,
                    # skip — Marisol didn't actively schedule them here.
                    if (is_support_emp
                            and rec["status"] != "working"
                            and not (existing and existing.get("worked_store_id") == selected_store_id)):
                        continue

                    # If a support employee is being scheduled here as "working", ensure
                    # worked_store_id is set to the current selected store
                    if rec["status"] == "working":
                        rec["worked_store_id"] = selected_store_id
                    else:
                        # Non-working statuses: preserve worked_store_id from any existing
                        # record so we don't overwrite a store assignment with blank
                        rec["worked_store_id"] = (
                            existing.get("worked_store_id")
                            or selected_store_id
                        )

                    sheets.upsert_attendance(rec, updated_by=current_user["email"])
                    saved_n += 1

                st.success(
                    f"✓ Guardados {saved_n} registro(s) "
                    f"· {store_labels[selected_store_id]} · {date.isoformat()}"
                )
                st.balloons()
                sheets.get_attendance_for_date.clear()
            except Exception as e:
                st.error(f"Error al guardar: `{e}`")

    with save_cols[0]:
        st.caption(
            "Se guardarán los registros que tengan cambios. "
            "El personal de apoyo solo se registra si lo marcas como **Trabajando**."
        )
