"""
Password gate — first security layer that runs BEFORE Google OAuth.

Reads the shared password from `secrets.toml`:
    [security]
    app_password = "Chester1*"

Once the user enters the correct password, the session is marked as
`password_passed` and won't ask again until they close the browser tab.

NEVER hardcode the password here — always read from st.secrets.
"""

from __future__ import annotations

import hashlib
import time

import streamlit as st


PASSWORD_SESSION_KEY = "_pwd_gate_passed"
ATTEMPTS_SESSION_KEY = "_pwd_gate_attempts"
LOCKOUT_UNTIL_KEY = "_pwd_gate_lockout_until"

MAX_ATTEMPTS = 5
LOCKOUT_SECONDS = 60  # 1 min lockout after 5 failed attempts


def _get_expected_password() -> str | None:
    """Read the expected password from secrets. Returns None if not configured."""
    try:
        return str(st.secrets["security"]["app_password"])
    except Exception:
        return None


def _constant_time_compare(a: str, b: str) -> bool:
    """Compare two strings in constant time to prevent timing attacks."""
    if not a or not b:
        return False
    return hashlib.sha256(a.encode()).hexdigest() == hashlib.sha256(b.encode()).hexdigest()


def is_passed() -> bool:
    """Has the user already entered the correct password in this session?"""
    return bool(st.session_state.get(PASSWORD_SESSION_KEY, False))


def render_gate() -> bool:
    """
    Render the password gate. Returns True if user has passed (now or before).
    Returns False if they still need to enter the password — caller should stop.
    """
    if is_passed():
        return True

    expected = _get_expected_password()
    if expected is None:
        # Misconfiguration: no password set in secrets — block everything
        st.markdown(
            """
            <div style="max-width:520px;margin:80px auto;padding:40px;background:#fff;
                 border:1px solid #FCA5A5;border-radius:6px;font-family:'Geist',sans-serif;">
              <div style="font-size:11px;letter-spacing:2.5px;text-transform:uppercase;
                   color:#B91C1C;font-weight:700;margin-bottom:14px;">
                ⛔  Configuración faltante
              </div>
              <h2 style="font-size:20px;font-weight:600;color:#0B0F19;margin-bottom:14px;">
                Falta configurar la contraseña de acceso
              </h2>
              <div style="font-size:13px;color:#3D4554;line-height:1.6;">
                Agrega en <code>secrets.toml</code>:<br><br>
                <code style="background:#F2F3F5;padding:8px 12px;display:block;
                       border-radius:4px;margin-top:6px;">[security]<br>
                app_password = "tu_contraseña_aquí"</code>
              </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        return False

    # Lockout check
    now = time.time()
    lockout_until = float(st.session_state.get(LOCKOUT_UNTIL_KEY, 0))
    is_locked = now < lockout_until

    # Render the gate
    st.markdown(
        """
        <style>
        @import url('https://fonts.googleapis.com/css2?family=Geist:wght@300;400;500;600;700&display=swap');
        html, body, [class*="css"], button, input, select, textarea {
            font-family: 'Geist', system-ui, sans-serif !important;
        }
        #MainMenu, footer, header { visibility: hidden; }
        section[data-testid="stSidebar"] { display: none !important; }
        .block-container { padding-top: 4rem !important; max-width: 480px !important; }

        .pwd-card {
            background: #FFFFFF;
            border: 1px solid #D8DCE2;
            border-radius: 8px;
            padding: 40px 36px;
            text-align: center;
        }
        .pwd-brand-mono {
            font-size: 10px;
            letter-spacing: 3px;
            text-transform: uppercase;
            color: #C9982A;
            font-weight: 700;
            margin-bottom: 8px;
        }
        .pwd-brand-name {
            font-size: 22px;
            font-weight: 600;
            color: #0B0F19;
            letter-spacing: -0.3px;
            margin-bottom: 6px;
        }
        .pwd-brand-sub {
            font-size: 12px;
            color: #6C7280;
            margin-bottom: 32px;
        }
        .pwd-lock-icon {
            font-size: 36px;
            margin-bottom: 18px;
        }
        .pwd-title {
            font-size: 16px;
            font-weight: 600;
            color: #0B0F19;
            margin-bottom: 8px;
        }
        .pwd-hint {
            font-size: 12px;
            color: #6C7280;
            margin-bottom: 24px;
            line-height: 1.6;
        }
        .pwd-warn {
            background: #FEF3C7;
            border-left: 3px solid #C9982A;
            padding: 10px 14px;
            border-radius: 4px;
            font-size: 12px;
            color: #92400E;
            text-align: left;
            margin-top: 14px;
            line-height: 1.5;
        }
        .pwd-error {
            background: #FEE2E2;
            border-left: 3px solid #DC2626;
            padding: 10px 14px;
            border-radius: 4px;
            font-size: 12px;
            color: #991B1B;
            text-align: left;
            margin-top: 14px;
            line-height: 1.5;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )

    st.markdown(
        """
        <div class="pwd-card">
          <div class="pwd-brand-mono">● VINTAGE BOUTIQUE</div>
          <div class="pwd-brand-name">Sistema Privado</div>
          <div class="pwd-brand-sub">Asistencia · Cierres · Inteligencia Ejecutiva</div>
          <div class="pwd-lock-icon">🔒</div>
          <div class="pwd-title">Acceso restringido</div>
          <div class="pwd-hint">
            Esta aplicación contiene información financiera y operativa confidencial.<br>
            Ingresa la contraseña para continuar.
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    if is_locked:
        remaining = int(lockout_until - now)
        st.markdown(
            f"""
            <div class="pwd-error">
              <strong>🚫 Bloqueado por múltiples intentos fallidos.</strong><br>
              Espera <strong>{remaining}</strong> segundo(s) antes de volver a intentar.
            </div>
            """,
            unsafe_allow_html=True,
        )
        # Force a re-render so the countdown ticks
        time.sleep(1)
        st.rerun()
        return False

    # Password input form
    with st.form("pwd_gate_form", clear_on_submit=False):
        pwd = st.text_input(
            "Contraseña",
            type="password",
            label_visibility="collapsed",
            placeholder="Ingresa la contraseña",
            key="_pwd_gate_input",
        )
        submit = st.form_submit_button("Continuar", use_container_width=True, type="primary")

    if submit:
        attempts = int(st.session_state.get(ATTEMPTS_SESSION_KEY, 0))
        if _constant_time_compare(pwd, expected):
            # Success
            st.session_state[PASSWORD_SESSION_KEY] = True
            st.session_state[ATTEMPTS_SESSION_KEY] = 0
            st.session_state[LOCKOUT_UNTIL_KEY] = 0
            st.rerun()
            return True
        else:
            attempts += 1
            st.session_state[ATTEMPTS_SESSION_KEY] = attempts
            if attempts >= MAX_ATTEMPTS:
                st.session_state[LOCKOUT_UNTIL_KEY] = now + LOCKOUT_SECONDS
                st.session_state[ATTEMPTS_SESSION_KEY] = 0
                st.markdown(
                    f"""
                    <div class="pwd-error">
                      <strong>🚫 Demasiados intentos fallidos.</strong><br>
                      Acceso bloqueado por {LOCKOUT_SECONDS} segundos.
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
                time.sleep(2)
                st.rerun()
            else:
                remaining_attempts = MAX_ATTEMPTS - attempts
                st.markdown(
                    f"""
                    <div class="pwd-error">
                      <strong>❌ Contraseña incorrecta.</strong><br>
                      Te quedan {remaining_attempts} intento(s) antes del bloqueo temporal.
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

    return False
