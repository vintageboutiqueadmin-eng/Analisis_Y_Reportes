"""
Authentication & role assignment.

Production: uses st.user.email (Streamlit Cloud private app).
Local dev / fallback: shows an executive-styled login screen with role selector.
"""

from __future__ import annotations
import streamlit as st

from .dashboard_html import LOGO_LARGE_SVG

ROLE_ADMIN = "admin"
ROLE_MANAGER = "manager"
ROLE_VIEWER = "viewer"

ROLE_LABELS = {
    ROLE_ADMIN: "Administración",
    ROLE_MANAGER: "Gerencia de Tiendas",
    ROLE_VIEWER: "Gerencia",
}


# ---------------------------------------------------------------------------
# Email / role resolution
# ---------------------------------------------------------------------------

def _get_streamlit_user_email():
    try:
        user = getattr(st, "user", None)
        if user is None:
            return None
        if hasattr(user, "is_logged_in") and not user.is_logged_in:
            return None
        email = getattr(user, "email", None)
        if email:
            return email
    except Exception:
        return None
    return None


def _get_secret_list(section, key):
    try:
        return [e.strip().lower() for e in st.secrets[section][key]]
    except Exception:
        return []


def get_role_for_email(email):
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


def get_display_name(email):
    names = st.secrets.get("display_names", {})
    if email and email.lower() in {k.lower() for k in names.keys()}:
        for k, v in names.items():
            if k.lower() == email.lower():
                return v
    local = email.split("@")[0] if email else ""
    return local.replace(".", " ").replace("_", " ").title() or "Usuario"


def authenticate():
    email = _get_streamlit_user_email()
    if email:
        role = get_role_for_email(email)
        if role:
            return {"email": email, "name": get_display_name(email), "role": role}
        return {"email": email, "name": get_display_name(email), "role": None}

    if "dev_email" in st.session_state and st.session_state.dev_email:
        email = st.session_state.dev_email
        role = get_role_for_email(email)
        return {"email": email, "name": get_display_name(email), "role": role}

    return None


# ---------------------------------------------------------------------------
# Login screen styles — kept as plain string (no f-string) so curly braces
# don't need escaping. CSS is injected separately from HTML to avoid
# Streamlit's markdown parser misinterpreting div blocks.
# ---------------------------------------------------------------------------

_LOGIN_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Geist:wght@300;400;500;600;700&display=swap');

#MainMenu, header, footer { visibility: hidden; }

.stApp {
    background: linear-gradient(180deg, #F2F3F5 0%, #E8EAEE 100%);
    font-family: 'Geist', system-ui, sans-serif;
}
.block-container {
    padding-top: 6vh !important;
    padding-bottom: 4vh !important;
    max-width: 480px !important;
}

.vb-login-hero {
    text-align: center;
    margin-bottom: 8px;
}
.vb-login-logo {
    width: 110px;
    height: 110px;
    margin: 0 auto 24px;
    display: block;
    filter: drop-shadow(0 10px 28px rgba(11,15,25,0.20));
}
.vb-login-logo svg { width: 100%; height: 100%; display: block; }
.vb-login-title {
    font-size: 28px;
    font-weight: 600;
    letter-spacing: -0.6px;
    color: #0B0F19;
    line-height: 1.1;
    margin-bottom: 0;
}

.vb-login-divider {
    display: flex;
    align-items: center;
    justify-content: center;
    margin: 28px auto;
    gap: 12px;
}
.vb-login-divider::before,
.vb-login-divider::after {
    content: '';
    width: 36px;
    height: 1px;
    background: #C9982A;
    opacity: 0.5;
}
.vb-login-star {
    color: #C9982A;
    font-size: 11px;
    letter-spacing: 3px;
}

.vb-login-footer {
    text-align: center;
    margin-top: 38px;
    font-size: 10px;
    letter-spacing: 3px;
    color: #9CA3AF;
    font-weight: 600;
    text-transform: uppercase;
}
.vb-login-footer-dot { color: #C9982A; margin: 0 9px; }

/* Streamlit widgets restyle */
div[data-baseweb="select"] > div {
    border-radius: 4px !important;
    border-color: #D8DCE2 !important;
    background: #FFFFFF !important;
    font-family: 'Geist', sans-serif !important;
    font-size: 13.5px !important;
    min-height: 46px !important;
}
.stButton button {
    background: #0B0F19 !important;
    color: #FFFFFF !important;
    border: none !important;
    border-radius: 4px !important;
    font-family: 'Geist', sans-serif !important;
    font-weight: 600 !important;
    letter-spacing: 0.3px !important;
    font-size: 13px !important;
    padding: 13px 20px !important;
    transition: all 0.15s ease !important;
}
.stButton button:hover {
    background: #1F2937 !important;
    transform: translateY(-1px);
    box-shadow: 0 4px 12px rgba(11,15,25,0.18) !important;
}
.stCaption {
    text-align: center !important;
    font-size: 11px !important;
    color: #6C7280 !important;
    letter-spacing: 0.3px !important;
}
</style>
"""


def render_dev_login():
    """Executive-styled login screen — CSS, HTML, widgets injected separately."""

    # 1) Styles
    st.markdown(_LOGIN_CSS, unsafe_allow_html=True)

    # 2) Hero (logo + title only — single line to avoid markdown parsing issues)
    hero_html = (
        '<div class="vb-login-hero">'
        f'<div class="vb-login-logo">{LOGO_LARGE_SVG}</div>'
        '<div class="vb-login-title">Vintage Boutique</div>'
        '</div>'
    )
    st.markdown(hero_html, unsafe_allow_html=True)

    # 3) Divider
    st.markdown(
        '<div class="vb-login-divider"><span class="vb-login-star">✦</span></div>',
        unsafe_allow_html=True,
    )

    # 4) Build authorized users list
    all_emails = []
    for role in (ROLE_ADMIN, ROLE_MANAGER, ROLE_VIEWER):
        section = {"admin": "admins", "manager": "managers", "viewer": "viewers"}[role]
        for e in _get_secret_list("auth", section):
            all_emails.append((e, role))

    if not all_emails:
        st.error("No hay usuarios configurados en los secrets de Streamlit.")
        return

    # 5) Selectbox — plain native widget, no surrounding HTML
    options = ["— elegir usuario —"] + [
        f"{get_display_name(e)}  ·  {ROLE_LABELS[r]}" for e, r in all_emails
    ]
    choice = st.selectbox(
        "Selecciona tu usuario",
        options,
        label_visibility="collapsed",
    )

    # 6) Button + email caption
    if choice and choice != "— elegir usuario —":
        idx = options.index(choice) - 1
        selected_email, _ = all_emails[idx]
        st.caption(selected_email)
        if st.button("Entrar al sistema  →", use_container_width=True, type="primary"):
            st.session_state.dev_email = selected_email
            st.rerun()
    else:
        st.caption("· · ·")
        st.button("Entrar al sistema  →", use_container_width=True, disabled=True)

    # 7) Footer
    st.markdown(
        '<div class="vb-login-footer">Sistema de Asistencia'
        '<span class="vb-login-footer-dot">·</span>MMXXVI</div>',
        unsafe_allow_html=True,
    )


def logout():
    st.session_state.pop("dev_email", None)
    try:
        if hasattr(st, "logout"):
            st.logout()
    except Exception:
        pass
    st.rerun()
