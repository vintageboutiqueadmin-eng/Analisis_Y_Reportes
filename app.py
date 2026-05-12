"""
Vintage Boutique — Sistema de Asistencia
========================================

Streamlit app with three role-based views:

    Pablo   (admin)   → Dashboard + Captura + Administración
    Marisol (manager) → Captura + Dashboard
    Juan    (viewer)  → Solo Dashboard

Auth is resolved against `[auth]` in `secrets.toml`.
Deploy as a private app in Streamlit Cloud so `st.user.email` is populated
automatically. For local development, a dev login screen lets you preview
any role.
"""

from __future__ import annotations

import streamlit as st

from modules import auth, dashboard, capture, admin

st.set_page_config(
    page_title="Vintage Boutique · Asistencia",
    page_icon="✦",
    layout="wide",
    initial_sidebar_state="auto",
)


def render_unauthorised(email: str) -> None:
    st.markdown(
        f"""
        <div style="max-width:520px;margin:80px auto;padding:40px;background:#fff;
             border:1px solid #D8DCE2;border-radius:6px;font-family:'Geist',sans-serif;
             text-align:center;">
          <div style="font-size:11px;letter-spacing:2.5px;text-transform:uppercase;
               color:#C2410C;font-weight:700;margin-bottom:14px;">
            ⛔  Acceso no autorizado
          </div>
          <h2 style="font-size:22px;font-weight:600;color:#0B0F19;margin-bottom:14px;">
            {email}
          </h2>
          <div style="font-size:13px;color:#3D4554;line-height:1.6;">
            Este correo no está registrado en el sistema. Si crees que debería tener
            acceso, contacta al administrador (Pablo Orozco) para que te agregue
            a la lista de usuarios autorizados.
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    col = st.columns([2, 1, 2])[1]
    if col.button("Cerrar sesión", use_container_width=True):
        auth.logout()


def render_role_nav(user: dict) -> str:
    """Top-bar nav with allowed pages. Returns the selected page key."""
    role = user["role"]
    pages = []
    if role == auth.ROLE_VIEWER:
        pages = [("dashboard", "Dashboard")]
    elif role == auth.ROLE_MANAGER:
        pages = [
            ("capture",   "Captura de Asistencia"),
            ("dashboard", "Dashboard"),
        ]
    elif role == auth.ROLE_ADMIN:
        pages = [
            ("dashboard", "Dashboard"),
            ("capture",   "Captura de Asistencia"),
            ("admin",     "Administración"),
        ]

    if not pages:
        return "dashboard"

    # Render as horizontal radio (sticky at top)
    st.markdown(
        """
        <style>
        section[data-testid="stSidebar"] { display: block; }
        </style>
        """,
        unsafe_allow_html=True,
    )

    with st.sidebar:
        st.markdown("**Navegación**")
        page_keys = [k for k, _ in pages]
        page_labels = {k: v for k, v in pages}
        current = st.session_state.get("page", page_keys[0])
        if current not in page_keys:
            current = page_keys[0]
        choice = st.radio(
            "Navegación",
            page_keys,
            format_func=lambda k: page_labels[k],
            index=page_keys.index(current),
            label_visibility="collapsed",
        )
        st.session_state.page = choice

        st.markdown("---")
        if st.button("Cerrar sesión", use_container_width=True):
            auth.logout()

    return choice


def main() -> None:
    user = auth.authenticate()

    # Not logged in at all → show dev login form (production users come pre-authed)
    if user is None:
        auth.render_dev_login()
        return

    # Logged in but no role configured
    if user["role"] is None:
        render_unauthorised(user["email"])
        return

    # Render the right page
    page = render_role_nav(user)
    if page == "dashboard":
        dashboard.render(user)
    elif page == "capture":
        capture.render(user)
    elif page == "admin":
        if user["role"] != auth.ROLE_ADMIN:
            st.error("No tienes permisos para acceder a esta sección.")
            return
        admin.render(user)
    else:
        dashboard.render(user)


if __name__ == "__main__":
    main()
