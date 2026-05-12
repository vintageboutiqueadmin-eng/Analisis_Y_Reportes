"""
Daily attendance capture form.

For each employee in the selected store, Marisol marks their status and times.
Saves one row per (date, employee_id) to the `attendance` sheet.
"""

from __future__ import annotations

import datetime as dt
import streamlit as st

from . import sheets

STATUS_OPTIONS = [
    ("working",    "Trabajando"),
    ("day_off",    "Día libre"),
    ("permission", "Permiso / Falta justificada"),
    ("vacation",   "Vacaciones"),
    ("sick",       "Incapacidad / Enfermedad"),
]
STATUS_LABEL = dict(STATUS_OPTIONS)


def _inject_css():
    st.markdown(
        """
        <style>
        @import url('https://fonts.googleapis.com/css2?family=Geist:wght@300;400;500;600;700&display=swap');
        html, body, [class*="css"], button, input, select, textarea { font-family: 'Geist', system-ui, sans-serif !important; }
        #MainMenu, footer { visibility: hidden; }
        .block-container { padding-top: 1.5rem !important; max-width: 1100px !important; }

        /* Header strip */
        .cap-header {
            background: #0B0F19; color: #F9FAFB; padding: 16px 24px;
            border-radius: 6px; margin-bottom: 22px;
            display: flex; justify-content: space-between; align-items: center;
        }
        .cap-header .ttl { font-size: 18px; font-weight: 600; letter-spacing: -0.2px; }
        .cap-header .sub { font-size: 10px; letter-spacing: 2.5px; text-transform: uppercase;
                           color: #C9982A; font-weight: 600; margin-bottom: 2px; }

        /* Employee card */
        .emp-card {
            background: #fff; border: 1px solid #D8DCE2; border-radius: 6px;
            padding: 16px 20px; margin-bottom: 12px;
        }
        .emp-card-name {
            font-size: 15px; font-weight: 600; color: #0B0F19; margin-bottom: 2px;
            letter-spacing: -0.2px;
        }
        .emp-card-sub {
            font-size: 11px; color: #6C7280; text-transform: uppercase;
            letter-spacing: 1.5px; font-weight: 600;
        }
        .stat-badge {
            display: inline-block; padding: 3px 9px; border-radius: 3px;
            font-size: 10px; font-weight: 700; text-transform: uppercase;
            letter-spacing: 1px;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def _time_or_none(t):
    """Streamlit time_input returns datetime.time. Format as HH:MM or None."""
    if t is None:
        return None
    if isinstance(t, dt.time):
        return t.strftime("%H:%M")
    return str(t)


def _default_shift(now: dt.time | None = None):
    return dt.time(10, 0), dt.time(19, 0), dt.time(13, 0), dt.time(14, 0)


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

    # ── Date + store selectors ────────────────────────────────────────────
    col1, col2, col3 = st.columns([1, 1, 1])

    with col1:
        date = st.date_input(
            "Fecha",
            value=st.session_state.get("cap_date", dt.date.today()),
            format="DD/MM/YYYY",
        )
        st.session_state.cap_date = date

    # Load stores
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
        selected_store_id = st.selectbox(
            "Tienda",
            store_options,
            format_func=lambda x: store_labels[x],
            index=store_options.index(st.session_state.get("cap_store", store_options[0]))
                if st.session_state.get("cap_store") in store_options else 0,
        )
        st.session_state.cap_store = selected_store_id

    with col3:
        st.markdown("<div style='height:28px;'></div>", unsafe_allow_html=True)
        if st.button("↻ Recargar lista de empleados", use_container_width=True):
            sheets.get_employees.clear()
            sheets.get_stores.clear()
            st.rerun()

    # ── Existing records for that date/store ──────────────────────────────
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

    st.markdown(
        f"<div style='margin:18px 0 8px;font-size:11px;letter-spacing:2px;"
        f"text-transform:uppercase;color:#6C7280;font-weight:600;'>"
        f"{len(store_emps)} empleado{'s' if len(store_emps) != 1 else ''} "
        f"· {store_labels[selected_store_id]}</div>",
        unsafe_allow_html=True,
    )

    # ── Per-employee form ─────────────────────────────────────────────────
    pending: list[dict] = []

    for emp in store_emps:
        existing_rec = existing_by_emp.get(emp["id"], {})
        prev_status = existing_rec.get("status", "working")
        status_idx = next(
            (i for i, (k, _) in enumerate(STATUS_OPTIONS) if k == prev_status), 0
        )

        with st.container():
            st.markdown(
                f"""
                <div class="emp-card">
                  <div style="display:flex;justify-content:space-between;align-items:baseline;
                       margin-bottom:14px;">
                    <div>
                      <div class="emp-card-name">{emp['name']}</div>
                      <div class="emp-card-sub">ID #{emp['id']}</div>
                    </div>
                  </div>
                </div>
                """,
                unsafe_allow_html=True,
            )

            cols = st.columns([2, 5])
            with cols[0]:
                status_choice = st.selectbox(
                    f"Estado",
                    [k for k, _ in STATUS_OPTIONS],
                    format_func=lambda k: STATUS_LABEL[k],
                    index=status_idx,
                    key=f"status_{emp['id']}",
                )

            record: dict = {
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
                    def _parse_t(s, fallback):
                        if not s: return fallback
                        try:
                            h, m = str(s).split(":")
                            return dt.time(int(h), int(m))
                        except Exception:
                            return fallback

                    d_ss, d_se, d_ls, d_le = _default_shift()
                    sc = st.columns(4)
                    ss_t = sc[0].time_input(
                        "Entrada", value=_parse_t(existing_rec.get("shift_start"), d_ss),
                        key=f"ss_{emp['id']}", step=1800,
                    )
                    se_t = sc[1].time_input(
                        "Salida", value=_parse_t(existing_rec.get("shift_end"), d_se),
                        key=f"se_{emp['id']}", step=1800,
                    )
                    ls_t = sc[2].time_input(
                        "Almuerzo desde", value=_parse_t(existing_rec.get("lunch_start"), d_ls),
                        key=f"ls_{emp['id']}", step=1800,
                    )
                    le_t = sc[3].time_input(
                        "Almuerzo hasta", value=_parse_t(existing_rec.get("lunch_end"), d_le),
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

                    record.update({
                        "shift_start": _time_or_none(ss_t),
                        "shift_end": _time_or_none(se_t),
                        "lunch_start": _time_or_none(ls_t),
                        "lunch_end": _time_or_none(le_t),
                        "overtime_minutes": int(ot),
                        "is_late": bool(is_late),
                        "actual_start": _time_or_none(actual_start_t) if is_late else None,
                    })
                else:
                    record["notes"] = st.text_input(
                        "Notas (opcional)",
                        value=existing_rec.get("notes", ""),
                        key=f"notes_{emp['id']}",
                        placeholder="Ej. Cita médica programada con anticipación",
                    )

            pending.append(record)
            st.markdown("<div style='height:8px;'></div>", unsafe_allow_html=True)

    # ── Save ──────────────────────────────────────────────────────────────
    st.markdown("---")
    save_cols = st.columns([3, 1])
    with save_cols[1]:
        if st.button("💾 Guardar asistencia", use_container_width=True, type="primary"):
            try:
                for rec in pending:
                    sheets.upsert_attendance(rec, updated_by=current_user["email"])
                st.success(
                    f"✓ Asistencia guardada para {len(pending)} empleados "
                    f"· {store_labels[selected_store_id]} · {date.isoformat()}"
                )
                st.balloons()
            except Exception as e:
                st.error(f"Error al guardar: `{e}`")

    with save_cols[0]:
        st.caption(
            "Se guardarán **todos** los registros mostrados arriba. "
            "Si modificas y vuelves a guardar, los datos del mismo empleado/fecha se sobrescriben."
        )
