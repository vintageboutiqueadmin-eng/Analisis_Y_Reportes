"""
Admin tools — only Pablo can access.

Includes:
  - Initial workbook bootstrap (create tabs + seed default roster)
  - Employee management (add / deactivate)
  - Quick sheet diagnostics
"""

from __future__ import annotations

import streamlit as st

from . import sheets


def _inject_css():
    st.markdown(
        """
        <style>
        @import url('https://fonts.googleapis.com/css2?family=Geist:wght@300;400;500;600;700&display=swap');
        html, body, [class*="css"] { font-family: 'Geist', system-ui, sans-serif !important; }
        #MainMenu, footer { visibility: hidden; }
        .block-container { padding-top: 1.5rem !important; max-width: 1100px !important; }
        .admin-header {
            background: #0B0F19; color: #F9FAFB; padding: 16px 24px;
            border-radius: 6px; margin-bottom: 22px;
            display: flex; justify-content: space-between; align-items: center;
        }
        .admin-header .ttl { font-size: 18px; font-weight: 600; letter-spacing: -0.2px; }
        .admin-header .sub { font-size: 10px; letter-spacing: 2.5px; text-transform: uppercase;
                              color: #C9982A; font-weight: 600; margin-bottom: 2px; }
        </style>
        """,
        unsafe_allow_html=True,
    )


def render(current_user: dict) -> None:
    _inject_css()
    st.markdown(
        f"""
        <div class="admin-header">
          <div>
            <div class="sub">● Vintage Boutique · Administración</div>
            <div class="ttl">Configuración del sistema</div>
          </div>
          <div style="text-align:right;font-size:11px;color:#9CA3AF;">
            <div style="color:#F9FAFB;font-weight:500;">{current_user['name']}</div>
            <div>{current_user['email']}</div>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    tab1, tab2, tab3 = st.tabs(["⚙️ Inicialización", "👥 Empleados", "🔍 Diagnóstico"])

    # ── Tab 1: Bootstrap ──────────────────────────────────────────────────
    with tab1:
        st.subheader("Inicialización del libro de Google Sheets")
        st.markdown(
            "Crea las tres pestañas necesarias (`stores`, `employees`, `attendance`) "
            "y siembra el roster inicial. **Esta operación es segura de repetir** — "
            "no duplica datos existentes."
        )
        col1, col2 = st.columns(2)
        with col1:
            if st.button("Crear estructura del libro", use_container_width=True):
                try:
                    result = sheets.ensure_workbook_structure()
                    if result["created"]:
                        st.success(f"✓ Pestañas creadas: {', '.join(result['created'])}")
                    else:
                        st.info("✓ Las pestañas ya existían y están correctas.")
                except Exception as e:
                    st.error(f"Error: `{e}`")
        with col2:
            if st.button("Sembrar tiendas + empleados demo", use_container_width=True):
                try:
                    sheets.seed_default_data()
                    st.success(
                        "✓ Tiendas (7ma y 6ta ave) y empleados demo (Jonathan, "
                        "Daisy, Alejandra Mota, Sonia, Ismael, Isabel) listos."
                    )
                except Exception as e:
                    st.error(f"Error: `{e}`")

    # ── Tab 2: Employees ──────────────────────────────────────────────────
    with tab2:
        st.subheader("Gestión de empleados")
        try:
            stores = sheets.get_stores()
            employees = sheets.get_employees()
        except Exception as e:
            st.error(f"No se pudo leer del sheet: `{e}`")
            return

        if not stores:
            st.warning("Primero crea las tiendas desde la pestaña *Inicialización*.")
            return

        st.markdown("##### Agregar empleado nuevo")
        with st.form("add_emp"):
            c1, c2, c3 = st.columns([2, 2, 1])
            new_name = c1.text_input("Nombre completo")
            new_store = c2.selectbox(
                "Tienda",
                [s["id"] for s in stores],
                format_func=lambda x: next(s["name"] for s in stores if s["id"] == x),
            )
            c3.markdown("<div style='height:28px;'></div>", unsafe_allow_html=True)
            submitted = c3.form_submit_button("Agregar", use_container_width=True)
            if submitted:
                if not new_name.strip():
                    st.error("El nombre no puede estar vacío.")
                else:
                    try:
                        sheets.add_employee(new_name.strip(), new_store)
                        st.success(f"✓ Agregado: {new_name.strip()}")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Error: `{e}`")

        st.markdown("##### Empleados actuales")
        if not employees:
            st.info("Sin empleados todavía.")
        else:
            for emp in employees:
                store_name = next(
                    (s["name"] for s in stores if s["id"] == emp["store_id"]),
                    emp["store_id"],
                )
                cols = st.columns([1, 4, 3, 2])
                cols[0].markdown(f"<div style='padding:8px 0;font-family:monospace;'>"
                                 f"#{emp['id']}</div>", unsafe_allow_html=True)
                cols[1].markdown(f"<div style='padding:8px 0;font-weight:600;'>"
                                 f"{emp['name']}</div>", unsafe_allow_html=True)
                cols[2].markdown(f"<div style='padding:8px 0;color:#6C7280;'>"
                                 f"{store_name}</div>", unsafe_allow_html=True)
                if cols[3].button("Desactivar", key=f"deact_{emp['id']}",
                                  use_container_width=True):
                    try:
                        sheets.set_employee_active(emp["id"], False)
                        st.success(f"✓ {emp['name']} desactivado")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Error: `{e}`")

    # ── Tab 3: Diagnóstico ────────────────────────────────────────────────
    with tab3:
        st.subheader("Diagnóstico de conexión")
        try:
            ss = sheets.get_spreadsheet()
            tabs = [w.title for w in ss.worksheets()]
            st.markdown(f"**Sheet:** `{ss.title}`")
            st.markdown(f"**URL:** [{ss.url}]({ss.url})")
            st.markdown("**Pestañas detectadas:**")
            for t in tabs:
                st.markdown(f"- `{t}`")
        except Exception as e:
            st.error(f"No se pudo conectar al Google Sheet: `{e}`")
            st.markdown(
                "**Verifica:**\n"
                "1. La sección `[gcp_service_account]` en `secrets.toml`\n"
                "2. `[sheets] spreadsheet_id`\n"
                "3. Que la cuenta de servicio tenga acceso de **Editor** al sheet\n"
            )

        st.markdown("---")
        st.markdown("**Configuración de roles** (`secrets.toml` → `[auth]`)")
        try:
            auth = st.secrets.get("auth", {})
            st.code(
                f"admins   = {list(auth.get('admins', []))}\n"
                f"managers = {list(auth.get('managers', []))}\n"
                f"viewers  = {list(auth.get('viewers', []))}",
                language="toml",
            )
        except Exception:
            st.warning("No se pudo leer la sección [auth] de secrets.")
