"""
Reporte de Cierres de Caja — Fase 1: Subida y almacenamiento.

3 secciones:
  1. PDFs Cierre de Caja        → file_uploader (múltiples PDFs)
  2. Foto NEONET / Credomatic  → camera_input + file_uploader
  3. Boletas de Banco           → camera_input + file_uploader

Features:
  - Detección automática de PDFs duplicados (mismo número de cierre POS/AAAA/MM/DD/NNNN)
  - Almacenamiento en Google Drive organizado por fecha
  - Historial: lista de cierres ya procesados, con acceso rápido
  - Fase 2 (próxima): botón "Analizar y conciliar" con Claude
"""

from __future__ import annotations

import datetime as dt
import io
import re
from zoneinfo import ZoneInfo

import streamlit as st

from . import drive_storage


GT_TZ = ZoneInfo("America/Guatemala")


def _today_gt() -> dt.date:
    return dt.datetime.now(GT_TZ).date()


# ---------------------------------------------------------------------------
# Page CSS
# ---------------------------------------------------------------------------

_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Geist:wght@300;400;500;600;700&family=Geist+Mono:wght@400;500;600&display=swap');
html, body, [class*="css"], button, input, select, textarea {
    font-family: 'Geist', system-ui, sans-serif !important;
}
#MainMenu, footer { visibility: hidden; }
.block-container { padding-top: 1.5rem !important; max-width: 1100px !important; }

.cc-header {
    background: #0B0F19; color: #F9FAFB; padding: 16px 24px;
    border-radius: 6px; margin-bottom: 18px;
    display: flex; justify-content: space-between; align-items: center;
}
.cc-header .ttl { font-size: 18px; font-weight: 600; letter-spacing: -0.2px; }
.cc-header .sub {
    font-size: 10px; letter-spacing: 2.5px; text-transform: uppercase;
    color: #C9982A; font-weight: 600; margin-bottom: 2px;
}

.cc-section {
    background: #FFFFFF; border: 1px solid #D8DCE2; border-radius: 6px;
    padding: 20px 22px; margin-bottom: 20px;
}
.cc-section-head { display: flex; align-items: center; gap: 12px; margin-bottom: 14px; }
.cc-section-number {
    width: 32px; height: 32px; border-radius: 50%; background: #0B0F19;
    color: #C9982A; display: grid; place-items: center; font-weight: 700;
    font-size: 14px; font-family: 'Geist Mono', monospace; flex-shrink: 0;
}
.cc-section-title {
    font-size: 16px; font-weight: 600; color: #0B0F19;
    letter-spacing: -0.2px; line-height: 1.2;
}
.cc-section-desc {
    font-size: 12px; color: #6C7280; margin-top: 2px;
}

.cc-counter {
    display: inline-block; padding: 3px 9px; border-radius: 3px;
    background: #F6F7F9; color: #0B0F19; font-size: 11px;
    font-weight: 700; letter-spacing: 1px; margin-left: auto;
    font-family: 'Geist Mono', monospace;
}

.cc-file-card {
    background: #FAFBFC; border: 1px solid #E8EBF0; border-radius: 4px;
    padding: 10px 14px; margin-bottom: 6px;
    display: flex; align-items: center; gap: 12px;
}
.cc-file-icon { font-size: 18px; flex-shrink: 0; }
.cc-file-info { flex: 1; min-width: 0; }
.cc-file-name {
    font-size: 12.5px; font-weight: 500; color: #0B0F19;
    white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
}
.cc-file-meta { font-size: 10.5px; color: #6C7280; margin-top: 1px; }

.cc-dup-warning {
    background: #FFF7ED; border: 1px solid #FDBA74;
    border-left: 3px solid #EA580C; border-radius: 4px;
    padding: 14px 16px; margin: 10px 0;
}
.cc-dup-title {
    font-size: 12px; font-weight: 700; color: #9A3412;
    text-transform: uppercase; letter-spacing: 1.5px; margin-bottom: 8px;
}
.cc-dup-body { font-size: 12.5px; color: #5C2A0E; line-height: 1.5; }

.cc-empty {
    text-align: center; padding: 24px; color: #9CA3AF;
    font-size: 12px; font-style: italic;
}

.cc-history-card {
    background: #FFFFFF; border: 1px solid #D8DCE2; border-radius: 6px;
    padding: 14px 18px; margin-bottom: 8px;
    display: flex; align-items: center; justify-content: space-between;
}
.cc-history-date {
    font-size: 14px; font-weight: 600; color: #0B0F19;
    font-family: 'Geist Mono', monospace;
}
.cc-history-status {
    font-size: 10px; letter-spacing: 1.5px; text-transform: uppercase;
    font-weight: 700; padding: 3px 9px; border-radius: 3px;
}
.cc-history-status.analyzed { background: #D1FADF; color: #1B7340; }
.cc-history-status.pending { background: #FEF3C7; color: #92400E; }
</style>
"""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

POS_REF_PATTERN = re.compile(r"POS/\d{4}/\d{2}/\d{2}/(\d{4,})")


def _extract_pos_ref(pdf_bytes: bytes) -> str | None:
    """Extract the POS/YYYY/MM/DD/NNNN reference from a PDF's first page."""
    try:
        from pypdf import PdfReader
        reader = PdfReader(io.BytesIO(pdf_bytes))
        if not reader.pages:
            return None
        text = reader.pages[0].extract_text() or ""
        m = POS_REF_PATTERN.search(text)
        return m.group(0) if m else None
    except Exception:
        return None


def _extract_pos_date(pdf_bytes: bytes) -> dt.date | None:
    """Extract the date from the POS reference (POS/2026/05/12/7488 → 2026-05-12)."""
    ref = _extract_pos_ref(pdf_bytes)
    if not ref:
        return None
    try:
        parts = ref.split("/")
        return dt.date(int(parts[1]), int(parts[2]), int(parts[3]))
    except Exception:
        return None


def _fmt_size(n_bytes) -> str:
    try:
        n = int(n_bytes)
    except (ValueError, TypeError):
        return ""
    for unit in ["B", "KB", "MB"]:
        if n < 1024:
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} GB"


def _fmt_drive_date(s: str) -> str:
    """Format a Drive ISO timestamp like '2026-05-13T09:48:00Z' → '13 May 09:48'."""
    try:
        d = dt.datetime.fromisoformat(s.replace("Z", "+00:00")).astimezone(GT_TZ)
        return d.strftime("%d %b %H:%M")
    except Exception:
        return s


def _file_icon(mime: str) -> str:
    if "pdf" in mime:
        return "📄"
    if "image" in mime:
        return "🖼️"
    return "📎"


# ---------------------------------------------------------------------------
# Section renderers
# ---------------------------------------------------------------------------

def _render_existing_files(folder_id: str) -> None:
    """List files currently in a Drive folder, with delete button."""
    try:
        files = drive_storage.list_folder(folder_id)
    except Exception as e:
        st.error(f"No se pudo listar archivos: `{e}`")
        return

    if not files:
        st.markdown(
            '<div class="cc-empty">Sin archivos. Sube algunos arriba.</div>',
            unsafe_allow_html=True,
        )
        return

    for f in files:
        cols = st.columns([10, 1])
        with cols[0]:
            st.markdown(
                f'<div class="cc-file-card">'
                f'<div class="cc-file-icon">{_file_icon(f.get("mimeType", ""))}</div>'
                f'<div class="cc-file-info">'
                f'<div class="cc-file-name">{f["name"]}</div>'
                f'<div class="cc-file-meta">'
                f'{_fmt_drive_date(f.get("modifiedTime",""))} · '
                f'{_fmt_size(f.get("size",0))}'
                f'</div></div></div>',
                unsafe_allow_html=True,
            )
        with cols[1]:
            if st.button("🗑", key=f"del_{f['id']}", help="Eliminar archivo"):
                try:
                    drive_storage.delete_file(f["id"])
                    st.success(f"Eliminado: {f['name']}")
                    st.rerun()
                except Exception as e:
                    st.error(f"Error: `{e}`")


def _detect_pdf_duplicates(uploads: list) -> dict[str, list]:
    """
    Group uploaded PDFs by their POS reference number.
    Returns dict {ref: [upload, ...]} only for duplicates (>=2 with same ref).
    """
    grouped = {}
    for up in uploads:
        try:
            up.seek(0)
            data = up.read()
            up.seek(0)
            ref = _extract_pos_ref(data) or f"(sin referencia detectada: {up.name})"
            grouped.setdefault(ref, []).append((up, data))
        except Exception:
            grouped.setdefault(f"(error leyendo: {up.name})", []).append((up, b""))
    return {k: v for k, v in grouped.items() if len(v) >= 2}


def _render_section_1_pdfs(folder_ids: dict) -> None:
    """Section 1: PDFs upload + duplicate detection."""
    st.markdown(
        '<div class="cc-section-head">'
        '<div class="cc-section-number">1</div>'
        '<div><div class="cc-section-title">PDFs Cierre de Caja</div>'
        '<div class="cc-section-desc">Reportes del POS exportados directamente del sistema.</div>'
        '</div></div>',
        unsafe_allow_html=True,
    )

    uploaded = st.file_uploader(
        "Arrastra los PDFs o haz click para seleccionarlos",
        type=["pdf"],
        accept_multiple_files=True,
        key="upload_pdfs",
        label_visibility="collapsed",
    )

    if uploaded:
        # Detect duplicates BEFORE uploading
        duplicates = _detect_pdf_duplicates(uploaded)

        if duplicates:
            st.markdown(
                '<div class="cc-dup-warning">'
                '<div class="cc-dup-title">⚠ Detectamos archivos duplicados</div>'
                '<div class="cc-dup-body">'
                'Varios PDFs corresponden al mismo cierre. Elige qué hacer con ellos antes de subir.'
                '</div></div>',
                unsafe_allow_html=True,
            )

            # Build a map: upload object -> 'keep'/'skip'
            decisions = {}
            for ref, items in duplicates.items():
                st.markdown(f"**Cierre duplicado: `{ref}`** ({len(items)} archivos)")
                # Sort items: prefer the one with latest filename timestamp
                items_sorted = sorted(items, key=lambda x: x[0].name, reverse=True)
                names = [u.name for u, _ in items_sorted]
                choice = st.radio(
                    f"Para `{ref}`, ¿qué archivo conservar?",
                    options=names + ["⚠ Cancelar — no subir ninguno de este cierre"],
                    index=0,
                    key=f"dup_choice_{ref}",
                )
                for u, _ in items_sorted:
                    decisions[u.name] = (
                        "keep" if u.name == choice else "skip"
                    )

            # Files without duplicates → auto-keep
            all_dup_names = {u.name for items in duplicates.values() for u, _ in items}
            for up in uploaded:
                if up.name not in all_dup_names:
                    decisions[up.name] = "keep"

            keep_count = sum(1 for v in decisions.values() if v == "keep")
            st.info(f"Se subirán **{keep_count} de {len(uploaded)}** archivos.")

        else:
            decisions = {up.name: "keep" for up in uploaded}

        col1, col2 = st.columns([3, 1])
        with col2:
            if st.button("⬆ Subir a Drive", use_container_width=True,
                         type="primary", key="upload_pdfs_btn"):
                try:
                    n = 0
                    detected_dates = set()
                    for up in uploaded:
                        if decisions.get(up.name) != "keep":
                            continue
                        up.seek(0)
                        data = up.read()
                        # Try to detect the date inside the PDF to warn if it doesn't match
                        pdf_date = _extract_pos_date(data)
                        if pdf_date:
                            detected_dates.add(pdf_date)
                        drive_storage.upload_file(
                            folder_ids["pdfs"], up.name, data, "application/pdf",
                        )
                        n += 1
                    st.success(f"✓ {n} PDFs subidos a Google Drive")
                    if len(detected_dates) > 1:
                        st.warning(
                            f"⚠ Los PDFs subidos contienen **fechas diferentes**: "
                            f"{', '.join(d.isoformat() for d in sorted(detected_dates))}. "
                            f"Verifica que correspondan al día que seleccionaste."
                        )
                    st.rerun()
                except Exception as e:
                    st.error(f"Error al subir: `{e}`")
        with col1:
            st.caption(
                "Cada PDF se identifica por su número de cierre (POS/AAAA/MM/DD/NNNN). "
                "Si subes dos PDFs con el mismo número, te avisaremos."
            )

    # Existing files
    st.markdown(
        '<div style="margin-top:18px;font-size:11px;letter-spacing:2px;'
        'text-transform:uppercase;color:#6C7280;font-weight:600;">'
        'Archivos ya subidos</div>',
        unsafe_allow_html=True,
    )
    _render_existing_files(folder_ids["pdfs"])


def _render_section_2_neonet(folder_ids: dict) -> None:
    """Section 2: NEONET/Credomatic photos."""
    st.markdown(
        '<div class="cc-section-head">'
        '<div class="cc-section-number">2</div>'
        '<div><div class="cc-section-title">Foto NEONET / Credomatic</div>'
        '<div class="cc-section-desc">Tickets resumen de transacciones de tarjeta del POS.</div>'
        '</div></div>',
        unsafe_allow_html=True,
    )

    st.caption(
        "📱 En el celular: el botón abre tu cámara o galería. "
        "💻 En computadora: te deja seleccionar archivos del disco."
    )

    uploaded = st.file_uploader(
        "Subir o tomar foto(s) de NEONET / Credomatic",
        type=["jpg", "jpeg", "png", "heic", "heif"],
        accept_multiple_files=True,
        key="upload_neonet",
        label_visibility="collapsed",
    )
    if uploaded:
        col1, col2 = st.columns([3, 1])
        with col2:
            if st.button("⬆ Subir a Drive", use_container_width=True,
                         type="primary", key="upload_neonet_btn"):
                try:
                    for up in uploaded:
                        up.seek(0)
                        data = up.read()
                        mime = up.type or "image/jpeg"
                        # If the file came from camera with a generic name, rename with timestamp
                        name = up.name
                        if name.lower() in ("image.jpg", "image.jpeg", "image.png", "photo.jpg"):
                            ts = dt.datetime.now(GT_TZ).strftime("%Y%m%d_%H%M%S")
                            ext = name.rsplit(".", 1)[-1].lower()
                            name = f"neonet_{ts}.{ext}"
                        drive_storage.upload_file(
                            folder_ids["neonet"], name, data, mime,
                        )
                    st.success(f"✓ {len(uploaded)} foto(s) subida(s)")
                    st.rerun()
                except Exception as e:
                    st.error(f"Error: `{e}`")
        with col1:
            st.caption(f"Listo para subir: **{len(uploaded)} archivo(s)**")

    st.markdown(
        '<div style="margin-top:18px;font-size:11px;letter-spacing:2px;'
        'text-transform:uppercase;color:#6C7280;font-weight:600;">'
        'Fotos ya subidas</div>',
        unsafe_allow_html=True,
    )
    _render_existing_files(folder_ids["neonet"])


def _render_section_3_boletas(folder_ids: dict) -> None:
    """Section 3: Bank deposit slips."""
    st.markdown(
        '<div class="cc-section-head">'
        '<div class="cc-section-number">3</div>'
        '<div><div class="cc-section-title">Boletas de Banco / Depósitos</div>'
        '<div class="cc-section-desc">Comprobantes físicos de los depósitos hechos al banco.</div>'
        '</div></div>',
        unsafe_allow_html=True,
    )

    st.caption(
        "📱 En el celular: el botón abre tu cámara o galería. "
        "💻 En computadora: te deja seleccionar archivos del disco."
    )

    uploaded = st.file_uploader(
        "Subir o tomar foto(s) de boletas de banco",
        type=["jpg", "jpeg", "png", "heic", "heif"],
        accept_multiple_files=True,
        key="upload_boletas",
        label_visibility="collapsed",
    )
    if uploaded:
        col1, col2 = st.columns([3, 1])
        with col2:
            if st.button("⬆ Subir a Drive", use_container_width=True,
                         type="primary", key="upload_boletas_btn"):
                try:
                    for up in uploaded:
                        up.seek(0)
                        data = up.read()
                        mime = up.type or "image/jpeg"
                        name = up.name
                        if name.lower() in ("image.jpg", "image.jpeg", "image.png", "photo.jpg"):
                            ts = dt.datetime.now(GT_TZ).strftime("%Y%m%d_%H%M%S")
                            ext = name.rsplit(".", 1)[-1].lower()
                            name = f"boleta_{ts}.{ext}"
                        drive_storage.upload_file(
                            folder_ids["boletas"], name, data, mime,
                        )
                    st.success(f"✓ {len(uploaded)} foto(s) subida(s)")
                    st.rerun()
                except Exception as e:
                    st.error(f"Error: `{e}`")
        with col1:
            st.caption(f"Listo para subir: **{len(uploaded)} archivo(s)**")

    st.markdown(
        '<div style="margin-top:18px;font-size:11px;letter-spacing:2px;'
        'text-transform:uppercase;color:#6C7280;font-weight:600;">'
        'Fotos ya subidas</div>',
        unsafe_allow_html=True,
    )
    _render_existing_files(folder_ids["boletas"])


# ---------------------------------------------------------------------------
# History view
# ---------------------------------------------------------------------------

def _render_history():
    """Show list of previously processed dates."""
    try:
        dates = drive_storage.list_processed_dates()
    except Exception as e:
        st.warning(f"No se pudo cargar el historial: `{e}`")
        return

    if not dates:
        st.markdown(
            '<div class="cc-empty">Aún no hay cierres procesados. '
            'Sube archivos arriba para crear el primero.</div>',
            unsafe_allow_html=True,
        )
        return

    for date_str in dates[:20]:  # last 20
        try:
            d = dt.date.fromisoformat(date_str)
            human = d.strftime("%A %d de %B, %Y").capitalize()
        except Exception:
            human = date_str

        col1, col2, col3 = st.columns([3, 2, 1])
        col1.markdown(
            f'<div style="padding:8px 0;font-weight:600;font-size:13px;'
            f'font-family:Geist Mono,monospace;">{date_str}</div>'
            f'<div style="font-size:11px;color:#6C7280;">{human}</div>',
            unsafe_allow_html=True,
        )
        col2.markdown("<div style='height:6px;'></div>", unsafe_allow_html=True)
        col2.caption("Análisis disponible próximamente (Fase 2)")
        if col3.button("Ver", key=f"hist_{date_str}", use_container_width=True):
            try:
                st.session_state.cc_date = dt.date.fromisoformat(date_str)
                st.rerun()
            except Exception:
                pass


# ---------------------------------------------------------------------------
# Main render
# ---------------------------------------------------------------------------

def render(current_user: dict) -> None:
    st.markdown(_CSS, unsafe_allow_html=True)

    st.markdown(
        f"""
        <div class="cc-header">
          <div>
            <div class="sub">● Vintage Boutique · Reportes</div>
            <div class="ttl">Reporte de Cierres de Caja</div>
          </div>
          <div style="text-align:right;font-size:11px;color:#9CA3AF;">
            <div style="color:#F9FAFB;font-weight:500;">{current_user['name']}</div>
            <div>{current_user['email']}</div>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # Verify Drive config exists
    try:
        _ = st.secrets["drive"]["root_folder_id"]
    except Exception:
        st.error(
            "⚠ **Falta configurar Google Drive.**\n\n"
            "Pablo debe seguir estos pasos:\n"
            "1. Crear una carpeta en Google Drive (ej. 'Vintage Boutique - Reportes')\n"
            "2. Compartirla con la cuenta de servicio "
            "`vintage-boutique-bot@asistencia-y-reportes.iam.gserviceaccount.com` "
            "como **Editor**\n"
            "3. Copiar el ID de la carpeta de la URL "
            "(`drive.google.com/drive/folders/AQUI_VA_EL_ID`)\n"
            "4. Agregar al final del archivo Secrets en Streamlit Cloud:\n"
            "```toml\n[drive]\nroot_folder_id = \"AQUI_VA_EL_ID\"\n```"
        )
        return

    # Tab nav
    tab_subir, tab_historial = st.tabs(["📥 Subir archivos del día", "📚 Historial"])

    with tab_subir:
        # Date picker
        col1, col2, col3 = st.columns([2, 2, 1])
        with col1:
            selected_date = st.date_input(
                "📅 Fecha del cierre",
                value=st.session_state.get("cc_date", _today_gt()),
                format="DD/MM/YYYY",
                key="cc_date_picker",
            )
            st.session_state.cc_date = selected_date

        with col2:
            today = _today_gt()
            helper = ""
            if selected_date == today:
                helper = "Hoy"
            elif selected_date == today - dt.timedelta(days=1):
                helper = "Ayer"
            elif selected_date == today - dt.timedelta(days=3):
                helper = "Viernes pasado (cierre del fin de semana)"
            st.markdown("<div style='height:28px;'></div>", unsafe_allow_html=True)
            if helper:
                st.caption(f"📌 {helper}")

        with col3:
            st.markdown("<div style='height:28px;'></div>", unsafe_allow_html=True)
            if st.button("↻ Recargar", use_container_width=True):
                st.rerun()

        # Ensure folders exist for this date
        try:
            folder_ids = drive_storage.ensure_day_structure(selected_date)
        except Exception as e:
            st.error(
                f"No se pudo acceder a Google Drive: `{e}`\n\n"
                "Verifica que la cuenta de servicio tenga acceso a la carpeta raíz."
            )
            return

        st.markdown("---")

        # 3 sections
        st.markdown('<div class="cc-section">', unsafe_allow_html=True)
        _render_section_1_pdfs(folder_ids)
        st.markdown('</div>', unsafe_allow_html=True)

        st.markdown('<div class="cc-section">', unsafe_allow_html=True)
        _render_section_2_neonet(folder_ids)
        st.markdown('</div>', unsafe_allow_html=True)

        st.markdown('<div class="cc-section">', unsafe_allow_html=True)
        _render_section_3_boletas(folder_ids)
        st.markdown('</div>', unsafe_allow_html=True)

        # Future analyze button
        st.markdown("---")
        st.info(
            "🔬 **Próximamente (Fase 2):** Botón para analizar y conciliar "
            "automáticamente los PDFs con las fotos NEONET y boletas, usando "
            "inteligencia artificial."
        )

    with tab_historial:
        st.markdown("##### Cierres procesados anteriormente")
        st.caption(
            "Selecciona una fecha para ver los archivos subidos en ese cierre."
        )
        st.markdown("<div style='height:8px;'></div>", unsafe_allow_html=True)
        _render_history()
