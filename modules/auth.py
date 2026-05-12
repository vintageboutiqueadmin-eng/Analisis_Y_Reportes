"""
Authentication & role assignment.

Two modes:
  1. Production (Streamlit Cloud private app): uses st.user.email automatically.
  2. Local dev: shows a role selector to test all views without OAuth.

Roles:
  - admin   → Pablo  (full access: dashboard + captura + administración)
  - manager → Marisol (captura de asistencia + dashboard)
  - viewer  → Lic. Juan (solo dashboard)

Configure emails in .streamlit/secrets.toml under [auth].
"""

from __future__ import annotations
import streamlit as st

ROLE_ADMIN = "admin"
ROLE_MANAGER = "manager"
ROLE_VIEWER = "viewer"

ROLE_LABELS = {
    ROLE_ADMIN: "Administración",
    ROLE_MANAGER: "Gerencia de Tiendas",
    ROLE_VIEWER: "Gerencia",
}


def _get_streamlit_user_email() -> str | None:
    """Try to read the email from Streamlit's native auth (cloud private apps)."""
    try:
        user = getattr(st, "user", None)
        if user is None:
            return None
        # Newer Streamlit
        if hasattr(user, "is_logged_in") and not user.is_logged_in:
            return None
        email = getattr(user, "email", None)
        if email:
            return email
    except Exception:
        return None
    return None


def _get_secret_list(section: str, key: str) -> list[str]:
    try:
        return [e.strip().lower() for e in st.secrets[section][key]]
    except Exception:
        return []


def get_role_for_email(email: str | None) -> str | None:
    if not email:
        return None
    e = email.strip().lower()
    if e in _get_secret_list("auth", "admins"):
        return ROLE_ADMIN
    if e in _get_secret_list("auth", "managers"):
        return ROLE_MANAGER
    if e in _get_secret_list("auth", "viewers"):
        return ROLE_VIEWER
    return None


def get_display_name(email: str) -> str:
    """Try to find a display name for a known email, else show the email."""
    names = st.secrets.get("display_names", {})
    if email and email.lower() in {k.lower() for k in names.keys()}:
        for k, v in names.items():
            if k.lower() == email.lower():
                return v
    # Fallback: capitalise local part
    local = email.split("@")[0] if email else ""
    return local.replace(".", " ").replace("_", " ").title() or "Usuario"


def authenticate() -> dict | None:
    """
    Returns a dict with {email, name, role} for the logged-in user, or None.

    Order of resolution:
      1. Streamlit Cloud `st.user`  (production)
      2. Session-state override (set by the dev login form)
    """
    # 1. Streamlit native auth
    email = _get_streamlit_user_email()
    if email:
        role = get_role_for_email(email)
        if role:
            return {"email": email, "name": get_display_name(email), "role": role}
        # User is logged in to Streamlit but not authorised
        return {"email": email, "name": get_display_name(email), "role": None}

    # 2. Local dev fallback
    if "dev_email" in st.session_state and st.session_state.dev_email:
        email = st.session_state.dev_email
        role = get_role_for_email(email)
        return {"email": email, "name": get_display_name(email), "role": role}

    return None


def render_dev_login() -> None:
    """Local-dev login screen. Lets you pick any configured user to test their view."""
    st.markdown(
        """
        <div style="max-width:520px;margin:80px auto;padding:36px 36px;
             background:#fff;border:1px solid #D8DCE2;border-radius:6px;
             font-family:'Geist',system-ui,sans-serif;">
          <div style="font-size:11px;text-transform:uppercase;letter-spacing:2.5px;
               color:#6C7280;font-weight:600;margin-bottom:14px;">
            <span style="color:#C9982A;">●</span> &nbsp; Modo Desarrollo
          </div>
          <h2 style="font-size:24px;font-weight:600;letter-spacing:-0.4px;
              color:#0B0F19;margin-bottom:8px;">Vintage Boutique</h2>
          <div style="font-size:13px;color:#3D4554;margin-bottom:24px;">
            Selecciona un usuario configurado para previsualizar su vista.<br>
            <strong>En producción</strong> el acceso es vía email autorizado en
            Streamlit Cloud (privado).
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # Build the list of all configured emails
    all_emails: list[tuple[str, str]] = []  # (email, role)
    for role in (ROLE_ADMIN, ROLE_MANAGER, ROLE_VIEWER):
        section = {"admin": "admins", "manager": "managers", "viewer": "viewers"}[role]
        for e in _get_secret_list("auth", section):
            all_emails.append((e, role))

    if not all_emails:
        st.error(
            "No hay correos configurados en `.streamlit/secrets.toml`. "
            "Agrega al menos uno bajo `[auth] admins / managers / viewers`."
        )
        return

    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        options = ["— elegir —"] + [
            f"{get_display_name(e)} ({ROLE_LABELS[r]}) · {e}" for e, r in all_emails
        ]
        choice = st.selectbox("Iniciar sesión como:", options, label_visibility="collapsed")
        if choice and choice != "— elegir —":
            idx = options.index(choice) - 1
            selected_email, _ = all_emails[idx]
            if st.button("Entrar", use_container_width=True, type="primary"):
                st.session_state.dev_email = selected_email
                st.rerun()


def logout() -> None:
    st.session_state.pop("dev_email", None)
    try:
        if hasattr(st, "logout"):
            st.logout()
    except Exception:
        pass
    st.rerun()
