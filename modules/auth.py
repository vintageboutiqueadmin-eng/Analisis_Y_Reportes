"""
Authentication & role assignment.

Production: uses st.user.email (Streamlit Cloud private app).
Local dev / fallback: shows a styled login screen with role selector.
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


def _get_streamlit_user_email():
    """Try to read the email from Streamlit's native auth (cloud private apps)."""
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


def render_dev_login():
    """Executive-styled login screen."""
    # Inject styles + render the splash hero
    st.markdown(
        f"""
        <style>
        @import url('https://fonts.googleapis.com/css2?family=Geist:wght@300;400;500;600;700&family=Geist+Mono:wght@400;500;600&display=swap');

        #MainMenu, header, footer {{ visibility: hidden; }}
        .stApp {{
            background: linear-gradient(180deg, #F2F3F5 0%, #E8EAEE 100%);
            font-family: 'Geist', system-ui, sans-serif;
        }}
        .block-container {{
            padding-top: 4vh !important;
            padding-bottom: 2vh !important;
            max-width: 520px !important;
        }}

        .vb-login-hero {{
            text-align: center;
            margin-bottom: 28px;
        }}
        .vb-login-logo {{
            width: 100px; height: 100px;
            margin: 0 auto 22px;
            display: block;
            filter: drop-shadow(0 8px 24px rgba(11,15,25,0.18));
        }}
        .vb-login-logo svg {{ width: 100%; height: 100%; }}
        .vb-login-title {{
            font-size: 26px;
            font-weight: 600;
            letter-spacing: -0.6px;
            color: #0B0F19;
            margin-bottom: 4px;
            line-height: 1.1;
        }}
        .vb-login-sub {{
            font-size: 10.5px;
            font-weight: 600;
            letter-spacing: 3px;
            text-transform: uppercase;
            color: #6C7280;
            margin-bottom: 18px;
        }}
        .vb-login-divider {{
            display: flex;
            align-items: center;
            justify-content: center;
            margin: 22px auto 26px;
            gap: 10px;
        }}
        .vb-login-divider::before,
        .vb-login-divider::after {{
            content: '';
            width: 30px;
            height: 1px;
            background: #C9982A;
            opacity: 0.5;
        }}
        .vb-login-divider span {{
            color: #C9982A;
            font-size: 10px;
            letter-spacing: 3px;
        }}
        .vb-login-card {{
            background: #FFFFFF;
            border: 1px solid #D8DCE2;
            border-radius: 8px;
            padding: 26px 26px 22px;
            box-shadow: 0 4px 24px rgba(11,15,25,0.06);
        }}
        .vb-login-card-eyebrow {{
            font-size: 9.5px;
            font-weight: 700;
            letter-spacing: 2.5px;
            text-transform: uppercase;
            color: #6C7280;
            margin-bottom: 6px;
            display: flex;
            align-items: center;
            gap: 9px;
        }}
        .vb-login-card-eyebrow::before {{
            content: '';
            width: 12px; height: 1px;
            background: #C9982A;
        }}
        .vb-login-card-title {{
            font-size: 16px;
            font-weight: 600;
            color: #0B0F19;
            margin-bottom: 4px;
            letter-spacing: -0.2px;
        }}
        .vb-login-card-desc {{
            font-size: 12px;
            color: #3D4554;
            line-height: 1.55;
            margin-bottom: 16px;
        }}
        .vb-login-card-desc strong {{ color: #0B0F19; }}
        .vb-login-footer {{
            text-align: center;
            margin-top: 28px;
            font-size: 9.5px;
            letter-spacing: 3px;
            color: #9CA3AF;
            font-weight: 600;
            text-transform: uppercase;
        }}
        .vb-login-footer-dot {{
            color: #C9982A;
            margin: 0 8px;
        }}

        /* Streamlit native widgets */
        div[data-baseweb="select"] > div {{
            border-radius: 4px !important;
            border-color: #D8DCE2 !important;
            background: #FFFFFF !important;
            font-family: 'Geist', sans-serif !important;
            font-size: 13px !important;
        }}
        .stButton button {{
            background: #0B0F19 !important;
            color: #FFFFFF !important;
            border: none !important;
            border-radius: 4px !important;
            font-family: 'Geist', sans-serif !important;
            font-weight: 600 !important;
            letter-spacing: 0.3px !important;
            font-size: 13px !important;
            padding: 12px 20px !important;
            transition: all 0.15s ease !important;
        }}
        .stButton button:hover {{
            background: #1F2937 !important;
            transform: translateY(-1px);
            box-shadow: 0 4px 12px rgba(11,15,25,0.18) !important;
        }}
        </style>

        <div class="vb-login-hero">
          <div class="vb-login-logo">{LOGO_LARGE_SVG}</div>
          <div class="vb-login-title">Vintage Boutique</div>
          <div class="vb-login-sub">Sistema de Asistencia</div>
        </div>

        <div class="vb-login-divider"><span>✦</span></div>
        """,
        unsafe_allow_html=True,
    )

    # Build the list of all configured emails
    all_emails = []
    for role in (ROLE_ADMIN, ROLE_MANAGER, ROLE_VIEWER):
        section = {"admin": "admins", "manager": "managers", "viewer": "viewers"}[role]
        for e in _get_secret_list("auth", section):
            all_emails.append((e, role))

    if not all_emails:
        st.error(
            "No hay correos configurados en los secrets de Streamlit. "
            "Configura `[auth] admins / managers / viewers`."
        )
        return

    st.markdown(
        """
        <div class="vb-login-card">
          <div class="vb-login-card-eyebrow">Acceso al panel</div>
          <div class="vb-login-card-title">Selecciona tu usuario</div>
          <div class="vb-login-card-desc">
            Identifícate para acceder al sistema. En producción el acceso es
            <strong>automático vía Google</strong> al desplegar como app privada
            en Streamlit Cloud.
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    options = ["— elegir usuario —"] + [
        f"{get_display_name(e)} · {ROLE_LABELS[r]}" for e, r in all_emails
    ]
    choice = st.selectbox(
        "Iniciar sesión como:",
        options,
        label_visibility="collapsed",
    )

    if choice and choice != "— elegir usuario —":
        idx = options.index(choice) - 1
        selected_email, _ = all_emails[idx]
        st.caption(f"📧 {selected_email}")
        if st.button("Entrar al sistema  →", use_container_width=True, type="primary"):
            st.session_state.dev_email = selected_email
            st.rerun()

    st.markdown(
        """
        <div class="vb-login-footer">
          Antigua Guatemala
          <span class="vb-login-footer-dot">·</span>
          MMXXVI
        </div>
        """,
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
