"""
Reporte de Cierres de Caja.

Flow:
  1. Lic uploads PDFs of cash closings + photos of NEONET/Credomatic + photos of bank deposit slips
  2. All files stay in st.session_state (not persisted)
  3. Click "Analizar con IA" -> Claude Opus 4.7 reads everything via vision API
  4. Renders reconciliation summary with green/yellow/red cards
  5. User downloads the final PDF report
"""

from __future__ import annotations

import base64
import datetime as dt
import io
import json
import re
from zoneinfo import ZoneInfo

import streamlit as st

from . import cash_history


GT_TZ = ZoneInfo("America/Guatemala")


# ---------------------------------------------------------------------------
# Session-state helpers — files live here, not on disk
# ---------------------------------------------------------------------------

def _bucket(key: str) -> list:
    """Get (and lazily init) a list of saved files in session state."""
    if key not in st.session_state:
        st.session_state[key] = []
    return st.session_state[key]


def _add_files(bucket_key: str, uploads, rename_prefix: str | None = None) -> int:
    """Persist uploaded files to session_state. Returns count added."""
    if not uploads:
        return 0
    bucket = _bucket(bucket_key)
    existing_names = {f["name"] for f in bucket}
    added = 0
    for up in uploads:
        up.seek(0)
        data = up.read()
        up.seek(0)
        name = up.name
        # Auto-rename generic camera names
        if rename_prefix and name.lower() in (
            "image.jpg", "image.jpeg", "image.png", "photo.jpg", "photo.jpeg",
        ):
            ts = dt.datetime.now(GT_TZ).strftime("%Y%m%d_%H%M%S_%f")[:-3]
            ext = name.rsplit(".", 1)[-1].lower()
            name = f"{rename_prefix}_{ts}.{ext}"
        # Avoid exact duplicates
        if name in existing_names:
            continue
        bucket.append({
            "name": name,
            "data": data,
            "mime": up.type or "application/octet-stream",
            "size": len(data),
        })
        existing_names.add(name)
        added += 1
    return added


def _clear_bucket(bucket_key: str):
    st.session_state[bucket_key] = []


def _remove_from_bucket(bucket_key: str, idx: int):
    bucket = _bucket(bucket_key)
    if 0 <= idx < len(bucket):
        bucket.pop(idx)


# ---------------------------------------------------------------------------
# CSS
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
    padding: 20px 22px; margin-bottom: 18px;
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
    text-align: center; padding: 18px; color: #9CA3AF;
    font-size: 12px; font-style: italic;
}

.cc-analyze-cta {
    background: linear-gradient(135deg, #0B0F19 0%, #1F2937 100%);
    color: #FFFFFF; padding: 22px 26px; border-radius: 8px;
    margin: 22px 0; text-align: center;
}
.cc-analyze-cta h3 {
    font-size: 18px; font-weight: 600; letter-spacing: -0.3px;
    margin-bottom: 6px; color: #FFF;
}
.cc-analyze-cta p {
    font-size: 12.5px; color: #9CA3AF; margin-bottom: 14px; line-height: 1.5;
}
.cc-analyze-cta .cta-gold {
    color: #E8C063; font-weight: 600;
}

/* ===== Report cards ===== */
.cc-report { background: #FFFFFF; border: 1px solid #D8DCE2;
  border-radius: 6px; padding: 26px; margin-top: 22px; }
.cc-report-header {
  padding-bottom: 16px; margin-bottom: 18px;
  border-bottom: 1px solid #D8DCE2;
}
.cc-report-eyebrow {
  font-size: 10px; letter-spacing: 2.5px; text-transform: uppercase;
  color: #6C7280; font-weight: 600; margin-bottom: 8px;
  display: flex; align-items: center; gap: 9px;
}
.cc-report-eyebrow::before {
  content: ''; width: 14px; height: 1px; background: #C9982A;
}
.cc-report-title {
  font-size: 22px; font-weight: 600; letter-spacing: -0.5px;
  color: #0B0F19; line-height: 1.2;
}
.cc-report-date {
  font-size: 12px; color: #3D4554; font-weight: 500;
  font-family: 'Geist Mono', monospace; margin-top: 6px;
}

.cc-overall {
  padding: 18px 22px; border-radius: 6px; margin-bottom: 18px;
}
.cc-overall.green {
  background: #ECFDF5; border: 1px solid #6EE7B7;
  border-left: 4px solid #059669;
}
.cc-overall.yellow {
  background: #FFFBEB; border: 1px solid #FCD34D;
  border-left: 4px solid #D97706;
}
.cc-overall.red {
  background: #FEF2F2; border: 1px solid #FCA5A5;
  border-left: 4px solid #DC2626;
}
.cc-overall-title {
  font-size: 14px; font-weight: 700; letter-spacing: 1px;
  text-transform: uppercase; margin-bottom: 6px;
}
.cc-overall.green .cc-overall-title { color: #065F46; }
.cc-overall.yellow .cc-overall-title { color: #92400E; }
.cc-overall.red .cc-overall-title { color: #991B1B; }
.cc-overall-body { font-size: 13px; line-height: 1.55; }
.cc-overall.green .cc-overall-body { color: #064E3B; }
.cc-overall.yellow .cc-overall-body { color: #78350F; }
.cc-overall.red .cc-overall-body { color: #7F1D1D; }

.cc-finding {
  padding: 14px 16px; border-radius: 4px; margin-bottom: 8px;
  border-left: 3px solid;
}
.cc-finding.ok { background: #F0FDF4; border-color: #16A34A; }
.cc-finding.warn { background: #FFFBEB; border-color: #D97706; }
.cc-finding.alert { background: #FEF2F2; border-color: #DC2626; }
.cc-finding-title {
  font-size: 12.5px; font-weight: 600; margin-bottom: 4px;
}
.cc-finding.ok .cc-finding-title { color: #15803D; }
.cc-finding.warn .cc-finding-title { color: #B45309; }
.cc-finding.alert .cc-finding-title { color: #B91C1C; }
.cc-finding-body { font-size: 12px; color: #3D4554; line-height: 1.5; }

.cc-table {
  width: 100%; border-collapse: collapse; margin: 14px 0;
  font-family: 'Geist Mono', monospace; font-size: 11.5px;
}
.cc-table th {
  background: #F6F7F9; color: #0B0F19; padding: 9px 12px;
  text-align: left; border-bottom: 1px solid #D8DCE2;
  font-size: 9.5px; text-transform: uppercase; letter-spacing: 1.5px;
  font-weight: 600;
}
.cc-table td {
  padding: 9px 12px; border-bottom: 1px solid #E8EBF0;
  color: #0B0F19;
}
.cc-table td.amount { text-align: right; font-weight: 500; }
.cc-table tr:last-child td { border-bottom: none; }
.cc-table tr.total td { background: #FAFBFC; font-weight: 700; }

.cc-section-label {
  font-size: 11px; letter-spacing: 2px; text-transform: uppercase;
  color: #0B0F19; font-weight: 700; margin: 22px 0 10px;
  padding-bottom: 6px; border-bottom: 1px solid #E8EBF0;
}
</style>
"""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

POS_REF_PATTERN = re.compile(r"POS/\d{4}/\d{2}/\d{2}/(\d{4,})")


def _today_gt() -> dt.date:
    return dt.datetime.now(GT_TZ).date()


def _extract_pos_ref(pdf_bytes: bytes) -> str | None:
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
    ref = _extract_pos_ref(pdf_bytes)
    if not ref:
        return None
    try:
        parts = ref.split("/")
        return dt.date(int(parts[1]), int(parts[2]), int(parts[3]))
    except Exception:
        return None


def _fmt_size(n_bytes: int) -> str:
    n = float(n_bytes or 0)
    for unit in ["B", "KB", "MB"]:
        if n < 1024:
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} GB"


def _file_icon(mime: str) -> str:
    if "pdf" in mime:
        return "📄"
    if "image" in mime:
        return "🖼️"
    return "📎"


# ---------------------------------------------------------------------------
# Section renderers
# ---------------------------------------------------------------------------

def _render_file_list(bucket_key: str):
    """List files saved in session_state with remove buttons."""
    bucket = _bucket(bucket_key)
    if not bucket:
        st.markdown(
            '<div class="cc-empty">No hay archivos cargados aún.</div>',
            unsafe_allow_html=True,
        )
        return

    for i, f in enumerate(bucket):
        cols = st.columns([10, 1])
        with cols[0]:
            st.markdown(
                f'<div class="cc-file-card">'
                f'<div class="cc-file-icon">{_file_icon(f["mime"])}</div>'
                f'<div class="cc-file-info">'
                f'<div class="cc-file-name">{f["name"]}</div>'
                f'<div class="cc-file-meta">{_fmt_size(f["size"])} · {f["mime"]}</div>'
                f'</div></div>',
                unsafe_allow_html=True,
            )
        with cols[1]:
            if st.button("🗑", key=f"rm_{bucket_key}_{i}", help="Quitar archivo"):
                _remove_from_bucket(bucket_key, i)
                st.rerun()


def _detect_pdf_duplicates(bucket_key: str) -> dict[str, list[int]]:
    """Find PDFs in the bucket that share the same POS reference."""
    bucket = _bucket(bucket_key)
    grouped = {}
    for i, f in enumerate(bucket):
        if "pdf" not in f["mime"]:
            continue
        ref = _extract_pos_ref(f["data"]) or "(sin referencia)"
        grouped.setdefault(ref, []).append(i)
    return {k: v for k, v in grouped.items() if len(v) >= 2}


def _render_section_pdfs():
    st.markdown(
        '<div class="cc-section-head">'
        '<div class="cc-section-number">1</div>'
        '<div><div class="cc-section-title">PDFs Cierre de Caja</div>'
        '<div class="cc-section-desc">Reportes del POS exportados directamente.</div>'
        '</div></div>',
        unsafe_allow_html=True,
    )

    uploaded = st.file_uploader(
        "Arrastra o selecciona los PDFs",
        type=["pdf"],
        accept_multiple_files=True,
        key="cc_upload_pdfs",
        label_visibility="collapsed",
    )

    # Auto-add files when uploaded (no separate button needed)
    if uploaded:
        # Use a fingerprint based on names + sizes to detect new uploads
        fingerprint = tuple(sorted((u.name, u.size) for u in uploaded))
        last_fp = st.session_state.get("cc_pdfs_fp")
        if fingerprint != last_fp:
            _add_files("cc_pdfs", uploaded)
            st.session_state["cc_pdfs_fp"] = fingerprint
            st.rerun()

    # Show duplicates warning
    dups = _detect_pdf_duplicates("cc_pdfs")
    if dups:
        st.markdown(
            '<div class="cc-dup-warning">'
            '<div class="cc-dup-title">⚠ Detectamos duplicados</div>'
            '<div class="cc-dup-body">'
            'Hay varios PDFs con el mismo número de cierre. Quita los duplicados '
            'antes de analizar para no contar montos dos veces.'
            '</div></div>',
            unsafe_allow_html=True,
        )
        bucket = _bucket("cc_pdfs")
        for ref, indices in dups.items():
            st.markdown(f"**Cierre duplicado: `{ref}`** — {len(indices)} archivos:")
            for idx in indices:
                f = bucket[idx]
                st.markdown(f"&nbsp;&nbsp;• `{f['name']}` ({_fmt_size(f['size'])})")

    st.markdown(
        '<div style="margin-top:14px;font-size:11px;letter-spacing:2px;'
        'text-transform:uppercase;color:#6C7280;font-weight:600;">'
        'PDFs cargados</div>',
        unsafe_allow_html=True,
    )
    _render_file_list("cc_pdfs")


def _render_section_photos(bucket_key: str, section_number: int,
                            title: str, desc: str, rename_prefix: str):
    st.markdown(
        f'<div class="cc-section-head">'
        f'<div class="cc-section-number">{section_number}</div>'
        f'<div><div class="cc-section-title">{title}</div>'
        f'<div class="cc-section-desc">{desc}</div>'
        f'</div></div>',
        unsafe_allow_html=True,
    )

    st.caption(
        "📱 En el celular: el botón abre tu cámara o galería. "
        "💻 En computadora: te deja seleccionar archivos del disco."
    )

    uploaded = st.file_uploader(
        f"Subir foto(s) — {title}",
        type=["jpg", "jpeg", "png", "webp", "pdf"],
        accept_multiple_files=True,
        key=f"cc_upload_{bucket_key}",
        label_visibility="collapsed",
    )

    # Auto-add on upload
    if uploaded:
        fp_key = f"{bucket_key}_fp"
        fingerprint = tuple(sorted((u.name, u.size) for u in uploaded))
        last_fp = st.session_state.get(fp_key)
        if fingerprint != last_fp:
            _add_files(bucket_key, uploaded, rename_prefix=rename_prefix)
            st.session_state[fp_key] = fingerprint
            st.rerun()

    st.markdown(
        '<div style="margin-top:14px;font-size:11px;letter-spacing:2px;'
        'text-transform:uppercase;color:#6C7280;font-weight:600;">'
        'Fotos cargadas</div>',
        unsafe_allow_html=True,
    )
    _render_file_list(bucket_key)


# ---------------------------------------------------------------------------
# Analysis with Claude
# ---------------------------------------------------------------------------

ANALYSIS_PROMPT = """Eres un experto en conciliación contable de tiendas minoristas. Te entregaré tres tipos de documentos del cierre de caja de Vintage Boutique (Antigua Guatemala), además de:
- Un **catálogo de documentos ya procesados** en cierres anteriores (para detectar duplicados)
- Una **bandeja de pendientes** (boletas / depósitos sin pareja de cierres anteriores que podrían cuadrar con los archivos de hoy)

## Tipos de documentos que recibes

1. **PDFs de cierre de caja del POS** — uno por cada cajero. Cada uno contiene:
   - Número de referencia POS/AAAA/MM/DD/NNNN (identificador único del PDF)
   - Tienda (6ta Avenida o 7ma Avenida)
   - Cajero (nombre)
   - Fecha del cierre (la fecha embebida en el número POS)
   - Totales por forma de pago: Tarjeta CREDOMATIC, Tarjeta VISANET, Efectivo
   - Total de depósito bancario realizado
   - Detalle de transacciones individuales con tarjeta (con nombre del cliente y monto)

2. **Fotos de tickets NEONET y/o Credomatic** — resúmenes físicos de las transacciones de tarjeta del POS.
   - NEONET maneja VISA / MASTERCARD / etc.
   - Credomatic es procesador separado.
   - Cada ticket tiene: fecha, hora, lote (ej. "Lote 000969"), terminal, lista de transacciones y total.
   - **Identificador único del ticket**: combinación `procesador + lote` (ej. "NEONET-000969" o "CREDOMATIC-000865").

3. **Fotos de boletas de depósito bancario** — comprobantes del banco donde se depositó el efectivo.
   - **Identificador único de la boleta**: el campo `J No. XXXXXXXX` (número grande en rojo arriba) o `No. Comprobante: XXXXXXXX`. SON EL MISMO NÚMERO.
   - Si la boleta dice "REIMPRESION" arriba, igual usas el número J/Comprobante que muestra.

## Reglas críticas de la conciliación

**⚠️ REGLA #0 — ANTI-ALUCINACIÓN (la más importante).** Solo trabaja con datos que LITERALMENTE puedes leer en los documentos que te entregamos. PROHIBIDO inventar:
   - Números de boleta (`J No.`) que no aparezcan claramente impresos en alguna foto/PDF de boleta.
   - Números POS/AAAA/MM/DD/NNNN que no estén en algún PDF.
   - Lotes de NEONET/Credomatic que no estén en algún ticket.
   - Si no puedes leer un campo con claridad, repórtalo en `findings` como warning. NUNCA inventes el dato. Mejor reportar "no se pudo leer el J No. de una boleta" que asumir uno.
   - Cada documento que listes en `orphan_slips`, `matched`, etc. DEBE corresponder a un archivo REAL que recibiste.

**⚠️ REGLA #0.5 — UNA BOLETA SE USA UNA SOLA VEZ.** Cada `J No.` único puede aparecer SOLO UNA VEZ en `matched` (haciendo pareja con UN solo `pos_ref`). Si la misma boleta parece cuadrar con dos depósitos diferentes, escoge la mejor coincidencia (más exacta por monto) y deja el otro depósito en `missing_slips`. Lo mismo aplica a PDFs (un POS ref no puede aparecer dos veces) y tickets (un lote no puede aparecer dos veces).

**⚠️ REGLA #1 — IGNORA COMPLETAMENTE LAS FECHAS PARA HACER MATCHING.** El depósito de un cierre puede hacerse al día siguiente, dos días después, o el lunes para cierres del fin de semana. **Lo único que importa es que los montos cuadren. Tolerancia de Q 1.00.**

**🚨 ANTES DE PONER UN DEPÓSITO EN `missing_slips`, ES OBLIGATORIO HACER ESTE CHECK:**
   - Recorre TODAS las boletas de HOY que aún no estén en `matched`.
   - ¿Hay alguna cuyo monto = monto del depósito (±Q 1.00)? → Si SÍ → es un MATCH. Va en `matched`. NO en `missing_slips`.
   - SOLO si NO encuentras boleta del mismo monto, va en `missing_slips`.

**🚨 ANTES DE PONER UNA BOLETA EN `orphan_slips`, ES OBLIGATORIO HACER ESTE CHECK:**
   - Recorre TODOS los depósitos extraídos de PDFs de HOY que aún no estén en `matched`.
   - ¿Hay alguno cuyo monto = monto de la boleta (±Q 1.00)? → Si SÍ → es un MATCH. Va en `matched`. NO en `orphan_slips`.
   - SOLO si NO encuentras depósito del mismo monto, va en `orphan_slips`.

**EJEMPLO PRÁCTICO:**
   - PDF dice: "Depósito Q 173.50" para Diana, POS/2026/05/22/7540 (cierre del 22/05)
   - Recibes boleta J No. 50613861 · Q 173.50 (fecha 23/05)
   - SON MATCH. La boleta del 23 cuadra con el depósito del 22 por monto. Va en `matched`, NO digas que "falta boleta" Y "boleta huérfana" del mismo monto al mismo tiempo. ESO ES UN ERROR GRAVE.

**⚠️ REGLA #1.5 — UN PDF PUEDE TENER MÚLTIPLES DEPÓSITOS PARCIALES.** Esto es importante:
   - Un cierre de cajero puede tener UN solo depósito grande (caso típico: una sola boleta cuadra), o **MÚLTIPLES depósitos parciales** (el cajero hizo varios viajes al banco, o partió el monto en varias boletas).
   - El PDF muestra cada depósito como una línea separada en la sección "Depósito" — por ejemplo:
     ```
     POS/.../7541  DEP GYT VINTAGE   Q 1,824.00
     POS/.../7541  DEP GYT VINTAGE   Q 900.00
     Subtotal Depósito: Q 2,724.00
     ```
   - Trata **CADA línea de depósito como un depósito independiente** que debe matchearse contra UNA boleta individual.
   - En el ejemplo anterior: busca una boleta de Q 1,824 Y una boleta de Q 900. Si encuentras ambas, ambas van en `matched`. NO sumes los depósitos y busques una sola boleta de Q 2,724.
   - El campo `deposito` del `cashier_breakdown` puede ser el subtotal (Q 2,724 en el ejemplo), pero en `bank_reconciliation.matched` listas cada depósito individual con su boleta correspondiente.

**⚠️ REGLA #0.5 — UNA BOLETA SE USA UNA SOLA VEZ.** Cada `J No.` único puede aparecer SOLO UNA VEZ en `matched` (haciendo pareja con UN solo `pos_ref`). Si la misma boleta parece cuadrar con dos depósitos diferentes, escoge la mejor coincidencia (más exacta por monto) y deja el otro depósito en `missing_slips`. Lo mismo aplica a PDFs (un POS ref no puede aparecer dos veces) y tickets (un lote no puede aparecer dos veces).

**REGLA #2 — Detección de duplicados contra historial.** Te paso un catálogo con los IDs de documentos ya procesados (pos_refs, bank_slip_numbers, neonet_lotes). Si en los archivos de HOY encuentras:
   - Un PDF cuyo POS ref ya está en el catálogo → es duplicado del cierre anterior. **EXCLÚYELO totalmente del cálculo de totales** (no sumes sus montos) y repórtalo como finding rojo indicando en cuál cierre histórico está.
   - Una boleta cuyo J No. ya está en el catálogo → mismo trato: excluir del cálculo, reportar.
   - Un ticket NEONET/Credomatic cuyo lote ya está en el catálogo → mismo trato: excluir del cálculo, reportar.

**REGLA #3 — Matching con la bandeja de pendientes.** Te paso una lista de pendientes acumulados de análisis anteriores. Cada pendiente tiene: tipo (`boleta_huerfana`, `deposito_sin_boleta`, o `diferencia_interna_cierre`), monto, ID del cierre histórico de origen, y datos adicionales.
   - Para cada **boleta huérfana** en pendientes: trata de hacer match con depósitos sin boleta de los PDFs de HOY. Si cuadran por monto (±Q 1.00), se resuelve.
   - Para cada **depósito sin boleta** en pendientes: trata de hacer match con boletas que recibes HOY. Si cuadran, se resuelve.
   - Para cada **diferencia interna**: si recibes una boleta cuyo monto es igual a esa diferencia, también puede resolverse.
   - Reporta cada match resuelto en el campo `resolved_pending` del JSON.

**REGLA #4 — Detección de duplicados internos del upload actual.** Si dos PDFs del MISMO upload tienen el mismo POS ref, o dos boletas tienen el mismo J No., o dos tickets tienen el mismo procesador+lote, trátalo igual: solo cuenta una vez, reporta el duplicado.

**REGLA #5 — Diferencias internas de PDF deben reportarse SIEMPRE.** Si un PDF muestra "Diferencia: Q X.XX" donde X > 0 (efectivo cobrado ≠ depósito realizado), reporta `diferencia_interna: X.XX` en el `cashier_breakdown` correspondiente. Estas diferencias representan dinero que el cajero debe reponer.

**REGLA #5.5 — REPOSICIÓN DE UN FALTANTE (no es un error).** Caso común y recurrente: un cajero queda corto en su cierre (REGLA #5, `diferencia_interna` > 0) y deposita ESE faltante por separado, casi siempre al día siguiente. Por eso es NORMAL y esperado ver, en el mismo upload, una boleta de banco cuyo monto = una diferencia interna y que no cuadra con ningún depósito de venta del POS.
   - Reporta la diferencia interna normalmente en el `cashier_breakdown` (REGLA #5) **Y** la boleta normalmente en `orphan_slips` (REGLA #1).
   - NO fuerces el match tú, NO muevas la boleta a `matched`, NO borres ninguno de los dos y NO inventes boletas (REGLA #0 y #0.5 siguen aplicando). El sistema concilia la reposición automáticamente después de tu análisis cuando el monto coincide de forma inequívoca.

**REGLA #5.6 — VARIOS CIERRES DEL MISMO CAJERO EL MISMO DÍA (cajas múltiples / RESCATE).** A veces Odoo abre varias cajas para el MISMO cajero el MISMO día (p.ej. la caja se traba y se genera un cierre marcado "(RESCATE DE POS/...)"). En ese caso cada cierre es una sesión de la MISMA persona, con el MISMO efectivo físico repartido entre sesiones:
   - Reporta CADA sesión por separado en `cashier_breakdown` con su `efectivo`, su `deposito` y su `diferencia_interna` = efectivo − depósito. **Incluye el signo**: si en una sesión depositó MÁS de lo que cobró (sobrante), su `diferencia_interna` es NEGATIVA (p.ej. −106.00). Si cobró más de lo que depositó (faltante), es positiva.
   - NO sumes ni netees las sesiones tú mismo, NO borres ni fusiones cierres. El sistema neta automáticamente todas las sesiones del mismo cajero + tienda + día (la fecha la toma del número POS) después de tu análisis: si los faltantes de unas sesiones se compensan con el sobrante de otra, no queda nada por reponer.

**REGLA #6 — TOTALES MANUALES DE TICKETS DE TARJETAS.** Si en el contexto que te paso encuentras un campo `manual_credomatic_total` o `manual_visanet_total` con un valor > 0, ese es el total real del ticket físico (escrito a mano por el Lic. porque el papel estaba ilegible). En ese caso:
   - Usa ese valor como `ticket_total` en `card_reconciliation`.
   - NO intentes leer el total del ticket de la imagen (el papel térmico está borroso).
   - Concilia el `pos_total` contra ese `ticket_total` manual.
   - En `note` indica: "Total del ticket ingresado manualmente por usuario debido a papel ilegible".

## Tu análisis debe producir

A) **Totales** (excluyendo duplicados, contando una sola vez):
   - CREDOMATIC, VISANET/NEONET, Efectivo, Depósitos bancarios, Total ventas

B) **Conciliación de tarjetas**: suma del PDF vs total del ticket físico (CREDOMATIC contra ticket Credomatic, VISANET contra ticket NEONET).

C) **Conciliación bancaria**: cada depósito del PDF contra cada boleta de banco recibida (por monto). Tres listas:
   - `matched`: depósitos del PDF que cuadran con boletas
   - `missing_slips`: depósitos del PDF sin boleta correspondiente (van a la bandeja de pendientes)
   - `orphan_slips`: boletas de banco sin depósito correspondiente en los PDFs de hoy (van a la bandeja)

D) **Detección de inconsistencias internas en PDFs**: diferencias internas, líneas contradictorias.

E) **Detección de duplicados** (cross-historical + interno).

F) **Resolución de pendientes**: qué pendientes anteriores se cuadraron con los archivos de hoy.

G) **Clientes VIP**: transacciones con clientes nombrados (no "CONSUMIDOR FINAL") por Q 200 o más.

H) **Fecha del cierre**: extrae la fecha de los PDFs del POS (todos deberían ser de la misma fecha o muy cercanos). Si los PDFs tienen fechas distintas, usa la más frecuente y repórtalo como warning.

## Devuelve JSON estructurado (sin texto fuera):

```json
{
  "report_date": "YYYY-MM-DD",
  "overall_status": "ok" | "warning" | "error",
  "overall_summary": "Resumen ejecutivo en 2-3 líneas, en español.",
  "totals_from_pdfs": {
    "credomatic": 0.00,
    "visanet": 0.00,
    "efectivo": 0.00,
    "depositos_bancarios": 0.00,
    "total_ventas": 0.00
  },
  "cashier_breakdown": [
    {
      "store": "6ta Avenida" | "7ma Avenida",
      "cashier": "Nombre del cajero",
      "pos_ref": "POS/2026/05/12/7488",
      "credomatic": 0.00,
      "visanet": 0.00,
      "efectivo": 0.00,
      "deposito": 0.00,
      "diferencia_interna": 0.00,
      "notes": ""
    }
  ],
  "card_reconciliation": {
    "credomatic": {
      "pos_total": 0.00,
      "ticket_total": 0.00,
      "ticket_lote": "000865",
      "difference": 0.00,
      "status": "ok" | "warning" | "error",
      "note": ""
    },
    "visanet_neonet": {
      "pos_total": 0.00,
      "ticket_total": 0.00,
      "ticket_lote": "000969",
      "difference": 0.00,
      "status": "ok" | "warning" | "error",
      "note": ""
    }
  },
  "bank_reconciliation": {
    "pos_deposits_total": 0.00,
    "bank_slips_total": 0.00,
    "difference": 0.00,
    "matched": [
      {"pos_ref": "...", "pos_amount": 0.00, "slip_number": "...", "slip_amount": 0.00, "slip_date": "..."}
    ],
    "missing_slips": [
      {"pos_ref": "...", "amount": 0.00, "cashier": "..."}
    ],
    "orphan_slips": [
      {"slip_number": "...", "amount": 0.00, "date": "..."}
    ]
  },
  "vip_clients": [
    {
      "name": "Nombre del cliente",
      "amount": 0.00,
      "cashier": "...",
      "store": "6ta Avenida" | "7ma Avenida",
      "payment_method": "CREDOMATIC" | "VISANET" | "Efectivo",
      "pos_ref": "POS/2026/05/12/7488"
    }
  ],
  "duplicates_detected": {
    "pdfs": [
      {"pos_ref": "...", "filename": "...", "previously_in_report_id": "..." or null,
       "reason": "ya existe en historial" | "duplicado interno del upload actual"}
    ],
    "bank_slips": [
      {"slip_number": "...", "filename": "...", "previously_in_report_id": "..." or null,
       "reason": "..."}
    ],
    "neonet_tickets": [
      {"procesador": "NEONET" | "CREDOMATIC", "lote": "...", "filename": "...",
       "previously_in_report_id": "..." or null, "reason": "..."}
    ]
  },
  "resolved_pending": [
    {
      "pending_type": "boleta_huerfana" | "deposito_sin_boleta",
      "pending_id": "ID del pendiente original",
      "original_report_id": "...",
      "amount": 0.00,
      "matched_with": "POS/2026/05/12/7488" | "slip_number XXX",
      "note": "Boleta huérfana del 10/05 cuadró con depósito sin boleta del cierre actual"
    }
  ],
  "findings": [
    {
      "severity": "ok" | "warn" | "alert",
      "title": "Título corto",
      "detail": "Descripción detallada del hallazgo."
    }
  ]
}
```

**Sé extremadamente cuidadoso con los montos.** Estos son datos contables reales. Si tienes la menor duda sobre algún número, refleja la duda en el campo `note` o como una alerta en `findings`. Mejor ser conservador y reportar dudas que asumir.

Trabaja en GTQ (Quetzales guatemaltecos). Usa punto decimal."""


def _to_base64(data: bytes) -> str:
    return base64.standard_b64encode(data).decode("utf-8")


# Anthropic API limit: when multiple images are in the same request, each image
# must have no dimension > 2000px. We resize to 1800 as a safety margin.
MAX_IMAGE_DIMENSION = 1800


def _resize_image_if_needed(data: bytes, mime: str, filename: str) -> tuple[bytes, str]:
    """
    If `data` is an image (JPEG/PNG/WEBP/HEIC) and either dimension exceeds
    MAX_IMAGE_DIMENSION, resize it preserving aspect ratio. Returns (new_bytes,
    new_mime). For PDFs and non-images, returns the data unchanged.

    This is critical: Anthropic's API rejects requests where any image dimension
    is > 2000px when sending multiple images. Phone photos are often 4000+px.
    """
    # Don't touch PDFs
    if not data:
        return data, mime
    fn_lower = (filename or "").lower()
    mime_lower = (mime or "").lower()
    if "pdf" in mime_lower or fn_lower.endswith(".pdf"):
        return data, mime

    # Only resize images
    is_image = (
        mime_lower.startswith("image/")
        or any(fn_lower.endswith(ext) for ext in (".jpg", ".jpeg", ".png", ".webp", ".heic", ".gif"))
    )
    if not is_image:
        return data, mime

    try:
        from PIL import Image
        import io

        # HEIC support requires pillow-heif. If not available, fall through.
        try:
            from pillow_heif import register_heif_opener
            register_heif_opener()
        except Exception:
            pass

        img = Image.open(io.BytesIO(data))

        # Convert to RGB if needed (for JPEG output compatibility)
        # but keep mode if already manageable
        orig_mode = img.mode

        # If neither dimension exceeds the limit, return original
        if img.width <= MAX_IMAGE_DIMENSION and img.height <= MAX_IMAGE_DIMENSION:
            # Still convert HEIC to JPEG for API compatibility
            if mime_lower == "image/heic" or fn_lower.endswith(".heic"):
                if img.mode in ("RGBA", "LA", "P"):
                    img = img.convert("RGB")
                out = io.BytesIO()
                img.save(out, format="JPEG", quality=92)
                return out.getvalue(), "image/jpeg"
            return data, mime

        # Compute new size preserving aspect ratio
        ratio = MAX_IMAGE_DIMENSION / max(img.width, img.height)
        new_w = int(img.width * ratio)
        new_h = int(img.height * ratio)
        img = img.resize((new_w, new_h), Image.LANCZOS)

        # Save: prefer original format if it's a common one; otherwise JPEG
        out = io.BytesIO()
        if mime_lower in ("image/png",) or fn_lower.endswith(".png"):
            # PNG keeps quality but bigger files; convert RGBA→RGB if needed for JPEG path
            img.save(out, format="PNG", optimize=True)
            return out.getvalue(), "image/png"
        elif mime_lower == "image/webp" or fn_lower.endswith(".webp"):
            img.save(out, format="WEBP", quality=92)
            return out.getvalue(), "image/webp"
        else:
            # Default: JPEG (handles JPG/HEIC/anything else)
            if img.mode in ("RGBA", "LA", "P"):
                img = img.convert("RGB")
            img.save(out, format="JPEG", quality=92)
            return out.getvalue(), "image/jpeg"
    except Exception:
        # If resizing fails for any reason, fall back to original — better to
        # let API reject than crash the upload flow
        return data, mime


def _build_anthropic_content(pdfs: list, neonet: list, boletas: list,
                              catalog: dict, pending: list,
                              manual_credomatic: float = 0.0,
                              manual_visanet: float = 0.0) -> list:
    """Build the content blocks for the Anthropic API call."""
    blocks = []

    # Manual ticket totals override (when papel térmico is illegible)
    if manual_credomatic > 0 or manual_visanet > 0:
        manual_text = (
            "=== TOTALES MANUALES DE TICKETS (sobreescriben lectura visual) ===\n"
            "El usuario indicó manualmente los siguientes totales porque el papel "
            "térmico está parcialmente ilegible. USA ESTOS VALORES en `card_reconciliation.ticket_total`, "
            "NO intentes leerlos de la imagen del ticket.\n\n"
        )
        if manual_credomatic > 0:
            manual_text += f"  manual_credomatic_total = Q {manual_credomatic:.2f}\n"
        if manual_visanet > 0:
            manual_text += f"  manual_visanet_total = Q {manual_visanet:.2f}\n"
        manual_text += (
            "\nEn el `card_reconciliation.note` del lado correspondiente, indica: "
            "'Total del ticket ingresado manualmente por usuario debido a papel ilegible.'\n"
        )
        blocks.append({"type": "text", "text": manual_text})

    # Catalog of already-processed IDs (for duplicate detection)
    catalog_text = (
        "=== CATÁLOGO DE DOCUMENTOS YA PROCESADOS EN CIERRES ANTERIORES ===\n"
        "Si encuentras alguno de estos IDs en los archivos de HOY, márcalo como duplicado "
        "histórico, EXCLÚYELO del cálculo de totales, y reporta el report_id donde ya existía.\n\n"
        f"PDFs ya procesados (pos_ref → report_id):\n"
    )
    if catalog.get("pos_refs"):
        for ref, rid in catalog["pos_refs"].items():
            catalog_text += f"  - {ref} → {rid}\n"
    else:
        catalog_text += "  (ninguno todavía)\n"

    catalog_text += "\nBoletas de banco ya procesadas (J No. → report_id):\n"
    if catalog.get("bank_slips"):
        for sn, rid in catalog["bank_slips"].items():
            catalog_text += f"  - {sn} → {rid}\n"
    else:
        catalog_text += "  (ninguna todavía)\n"

    catalog_text += "\nTickets NEONET/Credomatic ya procesados (procesador-lote → report_id):\n"
    if catalog.get("tickets"):
        for key, rid in catalog["tickets"].items():
            catalog_text += f"  - {key} → {rid}\n"
    else:
        catalog_text += "  (ninguno todavía)\n"

    blocks.append({"type": "text", "text": catalog_text})

    # Pending tray
    pending_text = (
        "\n=== BANDEJA DE PENDIENTES (de cierres anteriores) ===\n"
        "Estos son depósitos sin boleta y boletas huérfanas de cierres anteriores. "
        "Intenta hacer match con los archivos de HOY (por monto, tolerancia Q 1.00). "
        "Cada match resuelto va en el campo `resolved_pending` del JSON.\n\n"
    )
    if pending:
        for p in pending:
            details = p.get("details", {})
            if p["type"] == "deposito_sin_boleta":
                pending_text += (
                    f"  - PENDIENTE id={p['id']} type=deposito_sin_boleta "
                    f"amount=Q{p['amount']:.2f} "
                    f"origin_report_id={p['origin_report_id']} "
                    f"pos_ref={details.get('pos_ref', '?')} "
                    f"cashier={details.get('cashier', '?')}\n"
                )
            elif p["type"] == "boleta_huerfana":
                pending_text += (
                    f"  - PENDIENTE id={p['id']} type=boleta_huerfana "
                    f"amount=Q{p['amount']:.2f} "
                    f"origin_report_id={p['origin_report_id']} "
                    f"slip_number={details.get('slip_number', '?')} "
                    f"slip_date={details.get('date', '?')}\n"
                )
    else:
        pending_text += "  (sin pendientes)\n"

    blocks.append({"type": "text", "text": pending_text})

    # Section 1: PDFs
    if pdfs:
        blocks.append({
            "type": "text",
            "text": f"\n=== SECCIÓN 1: PDFs DE CIERRE DE CAJA ({len(pdfs)} archivos) ==="
        })
        for f in pdfs:
            blocks.append({
                "type": "text",
                "text": f"--- Archivo: {f['name']} ---",
            })
            blocks.append({
                "type": "document",
                "source": {
                    "type": "base64",
                    "media_type": "application/pdf",
                    "data": _to_base64(f["data"]),
                },
            })

    # Section 2: NEONET / Credomatic photos (or PDFs)
    if neonet:
        blocks.append({
            "type": "text",
            "text": f"\n=== SECCIÓN 2: TICKETS NEONET / CREDOMATIC ({len(neonet)} archivos) ==="
        })
        for f in neonet:
            blocks.append({
                "type": "text",
                "text": f"--- Archivo: {f['name']} ---",
            })
            if "pdf" in (f["mime"] or "").lower() or f["name"].lower().endswith(".pdf"):
                blocks.append({
                    "type": "document",
                    "source": {
                        "type": "base64",
                        "media_type": "application/pdf",
                        "data": _to_base64(f["data"]),
                    },
                })
            else:
                resized_data, resized_mime = _resize_image_if_needed(
                    f["data"], f["mime"], f["name"]
                )
                blocks.append({
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": resized_mime if resized_mime in (
                            "image/jpeg", "image/png", "image/gif", "image/webp"
                        ) else "image/jpeg",
                        "data": _to_base64(resized_data),
                    },
                })

    # Section 3: Bank slips (photos or PDFs)
    if boletas:
        blocks.append({
            "type": "text",
            "text": f"\n=== SECCIÓN 3: BOLETAS DE BANCO ({len(boletas)} archivos) ==="
        })
        for f in boletas:
            blocks.append({
                "type": "text",
                "text": f"--- Boleta: {f['name']} ---",
            })
            if "pdf" in (f["mime"] or "").lower() or f["name"].lower().endswith(".pdf"):
                blocks.append({
                    "type": "document",
                    "source": {
                        "type": "base64",
                        "media_type": "application/pdf",
                        "data": _to_base64(f["data"]),
                    },
                })
            else:
                resized_data, resized_mime = _resize_image_if_needed(
                    f["data"], f["mime"], f["name"]
                )
                blocks.append({
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": resized_mime if resized_mime in (
                            "image/jpeg", "image/png", "image/gif", "image/webp"
                        ) else "image/jpeg",
                        "data": _to_base64(resized_data),
                    },
                })

    blocks.append({
        "type": "text",
        "text": "\n\nAnaliza todos los documentos anteriores siguiendo las reglas críticas y "
                "devuelve SOLO el JSON estructurado (sin texto adicional, sin markdown)."
    })
    return blocks


def _call_claude(pdfs: list, neonet: list, boletas: list,
                 catalog: dict, pending: list,
                 manual_credomatic: float = 0.0,
                 manual_visanet: float = 0.0) -> dict:
    """Call Claude Opus 4.7 with all uploaded files + historical context."""
    import anthropic

    api_key = st.secrets["anthropic"]["api_key"]
    client = anthropic.Anthropic(api_key=api_key)

    content = _build_anthropic_content(
        pdfs, neonet, boletas, catalog, pending,
        manual_credomatic=manual_credomatic,
        manual_visanet=manual_visanet,
    )

    # 16000 tokens covers ~12-15 cashier closings plus all the bank reconciliation
    # detail, VIP lists, and findings. The Opus 4.7 model supports much more,
    # so this is a safe ceiling for typical multi-day closings.
    response = client.messages.create(
        model="claude-opus-4-7",
        max_tokens=16000,
        system=ANALYSIS_PROMPT,
        messages=[{"role": "user", "content": content}],
    )

    text = ""
    for block in response.content:
        if block.type == "text":
            text += block.text

    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)

    # Detect truncation: if Claude stopped because of max_tokens, the response
    # will be cut mid-JSON. Anthropic flags this via stop_reason.
    stop_reason = getattr(response, "stop_reason", None)
    was_truncated = (stop_reason == "max_tokens")

    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as e:
        if was_truncated:
            # The response was cut off — give a user-friendly error
            n_pdfs = len(pdfs)
            n_neonet = len(neonet)
            n_boletas = len(boletas)
            raise RuntimeError(
                f"El análisis es muy grande para procesarse de una sola vez "
                f"({n_pdfs} PDFs, {n_neonet} NEONET, {n_boletas} boletas). "
                f"La respuesta de la IA quedó cortada al llegar al límite máximo "
                f"de tokens.\n\n"
                f"💡 **Recomendación:** Sube los cierres en grupos más pequeños — "
                f"por ejemplo, un día a la vez (viernes, sábado, domingo por "
                f"separado). Cada análisis se guarda en el historial y los "
                f"pendientes se acumulan correctamente entre análisis."
            )
        # Otherwise, normal parse error
        raise RuntimeError(
            f"Claude devolvió un JSON inválido. Detalle: {e}\n\n"
            f"Respuesta cruda (primeros 500 chars): {text[:500]}"
        )

    # SAFETY NET: post-process to catch any missing/orphan that should have matched
    parsed = _autoresolve_missed_matches(parsed)
    # SAFETY NET: pair same-upload reposiciones (orphan slip ↔ internal difference)
    parsed = _autoresolve_reposiciones(parsed)
    return parsed


def _autoresolve_missed_matches(analysis: dict, tolerance: float = 1.0) -> dict:
    """
    Deterministic safety net that runs AFTER Claude's analysis.

    Scans bank_reconciliation.missing_slips and bank_reconciliation.orphan_slips,
    and matches them by amount (ignoring dates). Each successful match is moved
    to bank_reconciliation.matched.

    This protects against Claude failing to apply REGLA #1 (amount-only matching
    across dates), which is a recurring failure mode in our data.

    Returns the (possibly modified) analysis dict.
    """
    bank = analysis.get("bank_reconciliation") or {}
    missing = list(bank.get("missing_slips") or [])
    orphans = list(bank.get("orphan_slips") or [])
    matched = list(bank.get("matched") or [])

    if not missing or not orphans:
        return analysis

    # Build sets of slip_numbers and pos_refs already in matched so we don't double-match
    used_slips = {(m.get("slip_number") or "").strip() for m in matched}
    used_pos = {(m.get("pos_ref") or "").strip() for m in matched}

    new_missing = []
    used_orphan_indices = set()
    rescue_count = 0
    rescue_log = []

    for miss in missing:
        miss_amt = float(miss.get("amount") or 0)
        miss_pos = (miss.get("pos_ref") or "").strip()
        if miss_pos in used_pos:
            # Already matched somehow; skip
            continue

        # Find an orphan with matching amount, not yet used
        best_idx = None
        best_diff = tolerance + 0.001
        for idx, orph in enumerate(orphans):
            if idx in used_orphan_indices:
                continue
            orph_sn = (orph.get("slip_number") or "").strip()
            if orph_sn in used_slips:
                continue
            orph_amt = float(orph.get("amount") or 0)
            diff = abs(miss_amt - orph_amt)
            if diff <= tolerance and diff < best_diff:
                best_idx = idx
                best_diff = diff

        if best_idx is not None:
            orph = orphans[best_idx]
            orph_sn = (orph.get("slip_number") or "").strip()
            orph_amt = float(orph.get("amount") or 0)

            # Add to matched
            matched.append({
                "pos_ref": miss_pos,
                "pos_amount": miss_amt,
                "slip_number": orph_sn,
                "slip_amount": orph_amt,
                "cashier": miss.get("cashier", ""),
                "rescued_by_autoresolver": True,
            })
            used_orphan_indices.add(best_idx)
            used_slips.add(orph_sn)
            used_pos.add(miss_pos)
            rescue_count += 1
            rescue_log.append(
                f"{miss_pos} ({miss.get('cashier', '?')}) Q {miss_amt:.2f} "
                f"↔ boleta {orph_sn} Q {orph_amt:.2f}"
            )
        else:
            new_missing.append(miss)

    new_orphans = [
        o for i, o in enumerate(orphans) if i not in used_orphan_indices
    ]

    # If we rescued anything, update the analysis
    if rescue_count > 0:
        bank["matched"] = matched
        bank["missing_slips"] = new_missing
        bank["orphan_slips"] = new_orphans
        analysis["bank_reconciliation"] = bank

        # Add an informational finding
        findings = analysis.get("findings") or []
        findings.append({
            "severity": "info",
            "title": f"Conciliación automática post-análisis: {rescue_count} match(es) recuperados",
            "detail": (
                f"El sistema detectó {rescue_count} match(es) por monto que la IA no "
                f"había cuadrado automáticamente (regla de match por monto ignorando "
                f"fechas). Estos depósitos y boletas se reclasificaron como `matched`:\n"
                + "\n".join(f"  • {log}" for log in rescue_log)
            ),
        })
        analysis["findings"] = findings

        # Upgrade status from warning to ok if the only issue was these mismatches
        # (keep current status if there are still other issues)

    return analysis


def _autoresolve_reposiciones(analysis: dict, tolerance: float = 1.0) -> dict:
    """
    Deterministic safety net (runs AFTER Claude) for the 'reposición' case.

    A cashier short at close has `diferencia_interna` > 0 (efectivo cobrado >
    depósito → debe reponer). If they deposit that exact amount separately in the
    SAME upload, the deposit shows up as an orphan bank slip (no matching POS
    deposit). The slip and the difference are the SAME money.

    When an orphan slip's amount EXACTLY equals an internal difference's amount AND
    that amount is unambiguous within this upload (exactly one orphan and one
    difference of that amount), they are paired here: the orphan is dropped from
    orphan_slips and the diferencia_interna is zeroed, so the upload nets out
    instead of spawning two pendings that are really one Q-for-Q reposición.

    A bank slip carries no cashier, so amount is the only join key — hence the
    unique-amount requirement. Ambiguous amounts (several orphans/differences of
    the same value) are left untouched and handled later in the tray
    (cash_history.autoresolve_reposicion_pairs / link_reposicion), where a human
    confirms which slip repays which cashier.

    Returns the (possibly modified) analysis dict.
    """
    bank = analysis.get("bank_reconciliation") or {}
    orphans = list(bank.get("orphan_slips") or [])
    breakdown = analysis.get("cashier_breakdown") or []

    def _f(v):
        try:
            return round(float(v if v not in (None, "") else 0), 2)
        except Exception:
            return 0.0

    diff_entries = [c for c in breakdown if _f(c.get("diferencia_interna")) > 0]
    if not orphans or not diff_entries:
        return analysis

    from collections import defaultdict
    orph_by_amt = defaultdict(list)
    for o in orphans:
        orph_by_amt[_f(o.get("amount"))].append(o)
    diff_by_amt = defaultdict(list)
    for c in diff_entries:
        diff_by_amt[_f(c.get("diferencia_interna"))].append(c)

    removed_slips = set()
    paired_log = []

    for amt, o_list in orph_by_amt.items():
        if amt <= 0:
            continue
        d_list = diff_by_amt.get(amt, [])
        # Only auto-pair when unambiguous: exactly one of each at this amount.
        if len(o_list) == 1 and len(d_list) == 1:
            orph, diff = o_list[0], d_list[0]
            slip = (orph.get("slip_number") or "").strip()
            diff["diferencia_interna"] = 0
            prev = diff.get("notes", "")
            add = (
                f"[Repuesta en el mismo cierre vía depósito bancario — "
                f"boleta J No. {slip} (Q {amt:.2f})]"
            )
            diff["notes"] = (prev + " " + add).strip() if prev else add
            removed_slips.add(slip)
            paired_log.append(
                f"{diff.get('cashier', '?')} ({diff.get('pos_ref', '?')}) "
                f"Q {amt:.2f} ↔ boleta {slip}"
            )

    if not paired_log:
        return analysis

    bank["orphan_slips"] = [
        o for o in orphans
        if (o.get("slip_number") or "").strip() not in removed_slips
    ]
    analysis["bank_reconciliation"] = bank

    findings = analysis.get("findings") or []
    findings.append({
        "severity": "info",
        "title": f"Reposición detectada en el mismo cierre: {len(paired_log)} caso(s)",
        "detail": (
            "Un faltante de cierre fue repuesto con un depósito bancario en el "
            "mismo análisis. La boleta y el faltante se saldaron entre sí (no van "
            "a la bandeja de pendientes):\n"
            + "\n".join(f"  • {x}" for x in paired_log)
        ),
    })
    analysis["findings"] = findings
    return analysis


# ---------------------------------------------------------------------------
# Lightweight single-document extractors (for inline pending resolution)
# ---------------------------------------------------------------------------

EXTRACT_SLIP_PROMPT = """Eres un asistente que extrae datos de UNA boleta de depósito bancario (Banco G&T Continental u otro). La boleta puede ser foto o PDF.

Extrae:
- slip_number: el campo "J No. XXXXXXXX" (número rojo grande arriba) o "No. Comprobante: XXXXXXXX". SON EL MISMO NÚMERO.
- amount: el "TOTAL DEPOSITO" o monto total depositado, como número decimal en GTQ.
- date: la fecha de la boleta (formato YYYY-MM-DD si es posible).
- is_reprint: true si la boleta dice "REIMPRESION" arriba.

Devuelve SOLO un JSON con esta forma exacta, sin texto adicional ni markdown:
{
  "slip_number": "50613432",
  "amount": 1979.50,
  "date": "2026-05-13",
  "is_reprint": false,
  "confidence": "high" | "medium" | "low",
  "notes": ""
}

Si no puedes leer un campo, ponlo en blanco/null y baja la confidence."""


EXTRACT_PDF_PROMPT = """Eres un asistente que extrae datos de UN PDF de cierre de caja del POS de una tienda minorista.

Extrae:
- pos_ref: el número POS/AAAA/MM/DD/NNNN
- store: la tienda ("6ta Avenida" o "7ma Avenida")
- cashier: el nombre del cajero
- credomatic: total de tarjeta CREDOMATIC
- visanet: total de tarjeta VISANET
- efectivo: total de efectivo cobrado
- deposito: total depositado al banco según el PDF

Devuelve SOLO un JSON con esta forma exacta, sin texto adicional ni markdown:
{
  "pos_ref": "POS/2026/05/12/7488",
  "store": "6ta Avenida",
  "cashier": "SextaAlejandra",
  "credomatic": 1605.00,
  "visanet": 0.00,
  "efectivo": 1697.00,
  "deposito": 1697.00,
  "confidence": "high" | "medium" | "low",
  "notes": ""
}"""


EXTRACT_AUTO_PROMPT = """Eres un asistente que recibe UN documento (foto o PDF) y debe identificar automáticamente qué tipo de documento es y extraer los datos relevantes para conciliación contable de Vintage Boutique (Antigua Guatemala).

## Tipos de documentos posibles

### 1. **comprobante_bancario** — cualquier comprobante de transacción en una cuenta del banco
Esto incluye CUALQUIER documento bancario que evidencie que entró o salió dinero de una cuenta de Vintage. Acepta múltiples bancos y formatos:

- **Boleta de depósito tradicional** (Banco G&T Continental u otro):
  - Número grande "J No. XXXXXXXX" en rojo arriba (o "No. Comprobante: XXXXXXXX")
  - Muestra "TOTAL DEPOSITO: QXXX.XX"
  - Puede decir "REIMPRESION Autoriz."
  - Cuenta de Vintage Internacional

- **Nota de crédito / débito electrónica** (Banco Industrial BI-banking, otros bancos):
  - Tiene un "No." de documento (ej. "No. 19180431")
  - Indica "NOTA DE CRÉDITO" o "NOTA DE DÉBITO"
  - Muestra "CRÉDITO POR" o "DÉBITO POR" con monto "GTQ.XXX.XX"
  - Tiene descripción de la transacción
  - Aparece "BANCO INDUSTRIAL, S.A." u otro banco emisor
  - Cuenta de Vintage Internacional

- **Transferencia electrónica / SPEI / ACH** (cualquier banco):
  - Comprobante de transferencia recibida o enviada
  - Tiene un número de referencia o folio
  - Muestra monto y descripción

- **Comprobante de pago electrónico** (cualquier formato bancario):
  - Cualquier otro tipo de documento emitido por un banco que confirme un movimiento en cuenta

Para cualquier comprobante bancario, extrae:
- `slip_number`: el identificador único del documento (J No., No. de Comprobante, No. de Documento, número de referencia, folio — lo que sea el ID único del documento bancario). Es OBLIGATORIO encontrar algún ID — busca en todo el documento.
- `amount`: el monto principal de la transacción. Para notas de crédito = monto acreditado. Para boletas = TOTAL DEPOSITO. Para transferencias = monto transferido. Si hay varios montos, usa el TOTAL principal.
- `date`: fecha de la transacción (YYYY-MM-DD si es posible). Para notas BI usa el campo "FECHA". Para boletas G&T usa la fecha en el encabezado. Para otros, la fecha más relevante de la transacción.
- `bank`: nombre del banco emisor (ej. "G&T Continental", "Banco Industrial", "Banrural"). Si no se identifica, deja "".
- `transaction_type`: tipo específico (ej. "deposito", "nota_credito", "nota_debito", "transferencia"). Si no se identifica claramente, deja "deposito".
- `description`: cualquier descripción/concepto que aparezca en el documento (ej. "CHAQUETAS", "DEPOSITO MONETARIO"). Opcional.

### 2. **pdf_cierre** — PDF de cierre de caja del POS de la tienda
Características:
- Tiene "POS/AAAA/MM/DD/NNNN" en el encabezado
- Lista cierres por forma de pago: CREDOMATIC, VISANET, Efectivo
- Indica caja, cajero, fecha de apertura/cierre

Para pdf_cierre, extrae:
- `pos_ref`: el "POS/AAAA/MM/DD/NNNN"
- `cashier`: nombre del cajero
- `store`: "6ta Avenida" o "7ma Avenida"
- `amount`: el TOTAL DEPOSITO BANCARIO del cierre (no las ventas totales)
- `date`: la fecha del cierre

### 3. **otro** — cualquier otra cosa que no sea ninguno de los anteriores
Solo úsalo si verdaderamente no es ni un comprobante bancario ni un cierre del POS.

## Formato de respuesta

Devuelve SOLO un JSON con esta forma exacta, sin texto adicional ni markdown:
{
  "document_type": "comprobante_bancario" | "pdf_cierre" | "otro",
  "slip_number": "...",       // ID único del documento bancario o vacío si pdf_cierre
  "pos_ref": "...",           // solo si pdf_cierre
  "cashier": "...",           // solo si pdf_cierre
  "store": "...",             // solo si pdf_cierre
  "bank": "...",              // solo si comprobante_bancario
  "transaction_type": "...",  // solo si comprobante_bancario
  "description": "...",       // solo si comprobante_bancario
  "amount": 0.00,
  "date": "YYYY-MM-DD",
  "confidence": "high" | "medium" | "low",
  "notes": ""
}

**REGLAS IMPORTANTES:**
- Si no puedes leer un campo con claridad, ponlo como "" (string vacío) o null. Baja la confidence a "low" si dudas.
- NUNCA inventes números. Si no ves claramente un ID o monto, déjalo vacío.
- Si el documento es claramente un comprobante de un movimiento bancario (entrada o salida de dinero a/de una cuenta), siempre clasifícalo como `comprobante_bancario`, sin importar el banco o el formato exacto."""


def extract_auto(file_bytes: bytes, mime: str, filename: str) -> dict:
    """Auto-detect document type (any bank receipt vs pdf_cierre) and extract data."""
    import anthropic
    api_key = st.secrets["anthropic"]["api_key"]
    client = anthropic.Anthropic(api_key=api_key)

    content_blocks = [{
        "type": "text",
        "text": f"Archivo: {filename}",
    }]
    if "pdf" in (mime or "").lower() or filename.lower().endswith(".pdf"):
        content_blocks.append({
            "type": "document",
            "source": {
                "type": "base64",
                "media_type": "application/pdf",
                "data": _to_base64(file_bytes),
            },
        })
    else:
        resized_data, resized_mime = _resize_image_if_needed(file_bytes, mime, filename)
        media = resized_mime if resized_mime in ("image/jpeg", "image/png", "image/gif", "image/webp") else "image/jpeg"
        content_blocks.append({
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": media,
                "data": _to_base64(resized_data),
            },
        })

    response = client.messages.create(
        model="claude-opus-4-7",
        max_tokens=600,
        system=EXTRACT_AUTO_PROMPT,
        messages=[{"role": "user", "content": content_blocks}],
    )
    text = "".join(b.text for b in response.content if b.type == "text").strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    return json.loads(text)


def extract_slip_data(file_bytes: bytes, mime: str, filename: str) -> dict:
    """Extract structured data from ONE bank slip (photo or PDF)."""
    import anthropic
    api_key = st.secrets["anthropic"]["api_key"]
    client = anthropic.Anthropic(api_key=api_key)

    content_blocks = [{
        "type": "text",
        "text": f"Archivo: {filename}",
    }]
    if "pdf" in (mime or "").lower() or filename.lower().endswith(".pdf"):
        content_blocks.append({
            "type": "document",
            "source": {
                "type": "base64",
                "media_type": "application/pdf",
                "data": _to_base64(file_bytes),
            },
        })
    else:
        resized_data, resized_mime = _resize_image_if_needed(file_bytes, mime, filename)
        media = resized_mime if resized_mime in ("image/jpeg", "image/png", "image/gif", "image/webp") else "image/jpeg"
        content_blocks.append({
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": media,
                "data": _to_base64(resized_data),
            },
        })

    response = client.messages.create(
        model="claude-opus-4-7",
        max_tokens=500,
        system=EXTRACT_SLIP_PROMPT,
        messages=[{"role": "user", "content": content_blocks}],
    )
    text = "".join(b.text for b in response.content if b.type == "text").strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    return json.loads(text)


def extract_pdf_data(file_bytes: bytes, filename: str) -> dict:
    """Extract structured data from ONE POS closing PDF."""
    import anthropic
    api_key = st.secrets["anthropic"]["api_key"]
    client = anthropic.Anthropic(api_key=api_key)

    response = client.messages.create(
        model="claude-opus-4-7",
        max_tokens=500,
        system=EXTRACT_PDF_PROMPT,
        messages=[{"role": "user", "content": [
            {"type": "text", "text": f"Archivo: {filename}"},
            {"type": "document", "source": {
                "type": "base64",
                "media_type": "application/pdf",
                "data": _to_base64(file_bytes),
            }},
        ]}],
    )
    text = "".join(b.text for b in response.content if b.type == "text").strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    return json.loads(text)


# ---------------------------------------------------------------------------
# Render report
# ---------------------------------------------------------------------------

def _fmt_q(amount) -> str:
    """Format as Q 1,234.50"""
    try:
        n = float(amount)
    except (ValueError, TypeError):
        return "Q 0.00"
    return f"Q {n:,.2f}"


def _render_report(report: dict):
    """Render the analysis result as HTML cards + tables."""
    report_date = report.get("report_date", "")
    status = report.get("overall_status", "ok").lower()
    summary = report.get("overall_summary", "")

    # Header
    try:
        d = dt.date.fromisoformat(report_date)
        date_display = d.strftime("%A %d de %B, %Y").capitalize()
    except Exception:
        date_display = report_date

    st.markdown(
        f'<div class="cc-report">'
        f'<div class="cc-report-header">'
        f'<div class="cc-report-eyebrow">Reporte de conciliación</div>'
        f'<div class="cc-report-title">Cierre de Caja</div>'
        f'<div class="cc-report-date">{date_display}</div>'
        f'</div>',
        unsafe_allow_html=True,
    )

    # Overall status banner
    status_class = {"ok": "green", "warning": "yellow", "error": "red"}.get(status, "yellow")
    status_label = {
        "green": "✓ Todo cuadra correctamente",
        "yellow": "⚠ Atención: hay discrepancias",
        "red": "🔴 Inconsistencias serias detectadas",
    }[status_class]
    st.markdown(
        f'<div class="cc-overall {status_class}">'
        f'<div class="cc-overall-title">{status_label}</div>'
        f'<div class="cc-overall-body">{summary}</div>'
        f'</div>',
        unsafe_allow_html=True,
    )

    # Totals
    totals = report.get("totals_from_pdfs", {})
    if totals:
        st.markdown('<div class="cc-section-label">Totales del día (según PDFs)</div>',
                    unsafe_allow_html=True)
        st.markdown(
            '<table class="cc-table">'
            '<thead><tr><th>Forma de pago</th><th style="text-align:right;">Monto</th></tr></thead>'
            '<tbody>'
            f'<tr><td>Tarjeta CREDOMATIC</td><td class="amount">{_fmt_q(totals.get("credomatic", 0))}</td></tr>'
            f'<tr><td>Tarjeta VISANET / NEONET</td><td class="amount">{_fmt_q(totals.get("visanet", 0))}</td></tr>'
            f'<tr><td>Efectivo</td><td class="amount">{_fmt_q(totals.get("efectivo", 0))}</td></tr>'
            f'<tr><td>Depósitos bancarios realizados</td><td class="amount">{_fmt_q(totals.get("depositos_bancarios", 0))}</td></tr>'
            f'<tr class="total"><td>TOTAL VENTAS</td><td class="amount">{_fmt_q(totals.get("total_ventas", 0))}</td></tr>'
            '</tbody></table>',
            unsafe_allow_html=True,
        )

    # Cashier breakdown
    breakdown = report.get("cashier_breakdown", [])
    if breakdown:
        st.markdown('<div class="cc-section-label">Detalle por cajero</div>',
                    unsafe_allow_html=True)
        rows = []
        for c in breakdown:
            diff_html = ""
            if c.get("diferencia_interna", 0):
                diff_html = (
                    f'<div style="color:#B91C1C;font-size:10px;margin-top:2px;">'
                    f'⚠ Diferencia interna: {_fmt_q(c["diferencia_interna"])}</div>'
                )
            note_html = ""
            if c.get("notes"):
                note_html = (
                    f'<div style="color:#6C7280;font-size:10px;margin-top:2px;">'
                    f'{c["notes"]}</div>'
                )
            rows.append(
                f'<tr>'
                f'<td><strong>{c.get("store", "?")}</strong><br>'
                f'<span style="font-size:10px;color:#6C7280;">{c.get("pos_ref", "")}</span></td>'
                f'<td>{c.get("cashier", "?")}'
                f'{diff_html}{note_html}</td>'
                f'<td class="amount">{_fmt_q(c.get("credomatic", 0))}</td>'
                f'<td class="amount">{_fmt_q(c.get("visanet", 0))}</td>'
                f'<td class="amount">{_fmt_q(c.get("efectivo", 0))}</td>'
                f'<td class="amount">{_fmt_q(c.get("deposito", 0))}</td>'
                f'</tr>'
            )
        st.markdown(
            '<table class="cc-table">'
            '<thead><tr>'
            '<th>Tienda</th><th>Cajero</th>'
            '<th style="text-align:right;">Credomatic</th>'
            '<th style="text-align:right;">Visanet</th>'
            '<th style="text-align:right;">Efectivo</th>'
            '<th style="text-align:right;">Depósito</th>'
            '</tr></thead><tbody>'
            + "".join(rows) +
            '</tbody></table>',
            unsafe_allow_html=True,
        )

    # Card reconciliation
    card_rec = report.get("card_reconciliation", {})
    if card_rec:
        st.markdown('<div class="cc-section-label">Conciliación de tarjetas</div>',
                    unsafe_allow_html=True)
        for key, label in [("credomatic", "CREDOMATIC"), ("visanet_neonet", "VISANET / NEONET")]:
            r = card_rec.get(key, {})
            if not r:
                continue
            r_status = r.get("status", "ok").lower()
            r_class = {"ok": "ok", "warning": "warn", "error": "alert"}.get(r_status, "warn")
            diff = r.get("difference", 0)
            st.markdown(
                f'<div class="cc-finding {r_class}">'
                f'<div class="cc-finding-title">{label} — '
                f'POS: {_fmt_q(r.get("pos_total", 0))} vs. '
                f'Ticket: {_fmt_q(r.get("ticket_total", 0))} '
                f'(diferencia: {_fmt_q(diff)})</div>'
                f'<div class="cc-finding-body">{r.get("note", "")}</div>'
                f'</div>',
                unsafe_allow_html=True,
            )

    # Bank reconciliation
    bank_rec = report.get("bank_reconciliation", {})
    if bank_rec:
        st.markdown('<div class="cc-section-label">Conciliación bancaria (efectivo)</div>',
                    unsafe_allow_html=True)
        pos_total = bank_rec.get("pos_deposits_total", 0)
        slips_total = bank_rec.get("bank_slips_total", 0)
        diff = bank_rec.get("difference", 0)
        st.markdown(
            f'<table class="cc-table">'
            f'<tr><td>Depósitos según PDFs</td><td class="amount">{_fmt_q(pos_total)}</td></tr>'
            f'<tr><td>Suma de boletas de banco subidas</td><td class="amount">{_fmt_q(slips_total)}</td></tr>'
            f'<tr class="total"><td>Diferencia</td><td class="amount">{_fmt_q(diff)}</td></tr>'
            f'</table>',
            unsafe_allow_html=True,
        )

        matched = bank_rec.get("matched", [])
        if matched:
            st.markdown('<div style="font-size:11px;font-weight:700;color:#15803D;'
                        'margin:14px 0 6px;text-transform:uppercase;letter-spacing:1.5px;">'
                        f'✓ {len(matched)} depósito(s) que cuadran</div>',
                        unsafe_allow_html=True)
            for m in matched:
                st.markdown(
                    f'<div class="cc-finding ok">'
                    f'<div class="cc-finding-title">'
                    f'{m.get("pos_ref","")} · {_fmt_q(m.get("pos_amount", 0))}'
                    f'</div>'
                    f'<div class="cc-finding-body">'
                    f'Boleta #{m.get("slip_number","")} · {_fmt_q(m.get("slip_amount", 0))}'
                    f'</div></div>',
                    unsafe_allow_html=True,
                )

        missing = bank_rec.get("missing_slips", [])
        if missing:
            st.markdown('<div style="font-size:11px;font-weight:700;color:#B45309;'
                        'margin:14px 0 6px;text-transform:uppercase;letter-spacing:1.5px;">'
                        f'⚠ {len(missing)} depósito(s) sin boleta de banco</div>',
                        unsafe_allow_html=True)
            for m in missing:
                st.markdown(
                    f'<div class="cc-finding warn">'
                    f'<div class="cc-finding-title">'
                    f'Falta boleta: {m.get("pos_ref","")} · {_fmt_q(m.get("amount", 0))}'
                    f'</div>'
                    f'<div class="cc-finding-body">Cajero: {m.get("cashier", "?")}</div>'
                    f'</div>',
                    unsafe_allow_html=True,
                )

        orphans = bank_rec.get("orphan_slips", [])
        if orphans:
            st.markdown('<div style="font-size:11px;font-weight:700;color:#B91C1C;'
                        'margin:14px 0 6px;text-transform:uppercase;letter-spacing:1.5px;">'
                        f'🔴 {len(orphans)} boleta(s) sin PDF correspondiente</div>',
                        unsafe_allow_html=True)
            for o in orphans:
                st.markdown(
                    f'<div class="cc-finding alert">'
                    f'<div class="cc-finding-title">'
                    f'Boleta huérfana #{o.get("slip_number","")} · {_fmt_q(o.get("amount", 0))}'
                    f'</div>'
                    f'<div class="cc-finding-body">Fecha: {o.get("date", "?")}</div>'
                    f'</div>',
                    unsafe_allow_html=True,
                )

    # VIP clients
    vips = report.get("vip_clients", [])
    if vips:
        st.markdown('<div class="cc-section-label">⭐ Clientes VIP del día '
                    f'<span style="color:#6C7280;font-weight:500;">'
                    f'({len(vips)} compras de Q 200+)</span></div>',
                    unsafe_allow_html=True)
        rows = []
        for v in vips:
            method = v.get("payment_method", "")
            method_color = {
                "CREDOMATIC": "#C9982A",
                "VISANET": "#1D4ED8",
                "Efectivo": "#1B7340",
            }.get(method, "#6C7280")
            rows.append(
                f'<tr>'
                f'<td><strong>{v.get("name","?")}</strong></td>'
                f'<td class="amount">{_fmt_q(v.get("amount", 0))}</td>'
                f'<td>{v.get("cashier","?")}</td>'
                f'<td>{v.get("store","?")}</td>'
                f'<td><span style="color:{method_color};font-weight:600;font-size:10px;">'
                f'{method}</span></td>'
                f'</tr>'
            )
        st.markdown(
            '<table class="cc-table">'
            '<thead><tr>'
            '<th>Cliente</th>'
            '<th style="text-align:right;">Monto</th>'
            '<th>Cajero</th>'
            '<th>Tienda</th>'
            '<th>Pago</th>'
            '</tr></thead><tbody>'
            + "".join(rows) +
            '</tbody></table>',
            unsafe_allow_html=True,
        )

    # Duplicados detectados
    dups = report.get("duplicates_detected", {}) or {}
    has_dups = any([
        dups.get("pdfs"), dups.get("bank_slips"), dups.get("neonet_tickets")
    ])
    if has_dups:
        st.markdown('<div class="cc-section-label">🚫 Duplicados detectados '
                    '<span style="color:#6C7280;font-weight:500;">'
                    '(excluidos automáticamente del cálculo)</span></div>',
                    unsafe_allow_html=True)
        for pdf in (dups.get("pdfs") or []):
            prev = pdf.get("previously_in_report_id") or "—"
            st.markdown(
                f'<div class="cc-finding alert">'
                f'<div class="cc-finding-title">'
                f'📄 PDF duplicado: {pdf.get("pos_ref", "?")}'
                f'</div>'
                f'<div class="cc-finding-body">'
                f'Archivo: <code>{pdf.get("filename", "")}</code> · '
                f'{pdf.get("reason", "")} · '
                f'En reporte: <code>{prev}</code>'
                f'</div></div>',
                unsafe_allow_html=True,
            )
        for slip in (dups.get("bank_slips") or []):
            prev = slip.get("previously_in_report_id") or "—"
            st.markdown(
                f'<div class="cc-finding alert">'
                f'<div class="cc-finding-title">'
                f'🧾 Boleta duplicada: J No. {slip.get("slip_number", "?")}'
                f'</div>'
                f'<div class="cc-finding-body">'
                f'Archivo: <code>{slip.get("filename", "")}</code> · '
                f'{slip.get("reason", "")} · '
                f'En reporte: <code>{prev}</code>'
                f'</div></div>',
                unsafe_allow_html=True,
            )
        for tk in (dups.get("neonet_tickets") or []):
            prev = tk.get("previously_in_report_id") or "—"
            st.markdown(
                f'<div class="cc-finding alert">'
                f'<div class="cc-finding-title">'
                f'💳 Ticket duplicado: {tk.get("procesador","?")} - Lote {tk.get("lote","?")}'
                f'</div>'
                f'<div class="cc-finding-body">'
                f'Archivo: <code>{tk.get("filename", "")}</code> · '
                f'{tk.get("reason", "")} · '
                f'En reporte: <code>{prev}</code>'
                f'</div></div>',
                unsafe_allow_html=True,
            )

    # Pendientes resueltos
    resolved = report.get("resolved_pending") or []
    if resolved:
        st.markdown('<div class="cc-section-label">✅ Pendientes resueltos en este análisis</div>',
                    unsafe_allow_html=True)
        for r in resolved:
            ptype_label = {
                "boleta_huerfana": "Boleta huérfana",
                "deposito_sin_boleta": "Depósito sin boleta",
            }.get(r.get("pending_type", ""), "Pendiente")
            st.markdown(
                f'<div class="cc-finding ok">'
                f'<div class="cc-finding-title">'
                f'{ptype_label} — {_fmt_q(r.get("amount", 0))}'
                f'</div>'
                f'<div class="cc-finding-body">'
                f'{r.get("note", "")} · '
                f'Cuadró con: <code>{r.get("matched_with", "")}</code> · '
                f'Cierre origen: <code>{r.get("original_report_id", "")}</code>'
                f'</div></div>',
                unsafe_allow_html=True,
            )

    # General findings
    findings = report.get("findings", [])
    if findings:
        st.markdown('<div class="cc-section-label">Hallazgos generales</div>',
                    unsafe_allow_html=True)
        for f in findings:
            sev = f.get("severity", "warn").lower()
            sev_class = {"ok": "ok", "warn": "warn", "alert": "alert"}.get(sev, "warn")
            icon = {"ok": "✓", "warn": "⚠", "alert": "🔴"}.get(sev, "•")
            st.markdown(
                f'<div class="cc-finding {sev_class}">'
                f'<div class="cc-finding-title">{icon} {f.get("title", "")}</div>'
                f'<div class="cc-finding-body">{f.get("detail", "")}</div>'
                f'</div>',
                unsafe_allow_html=True,
            )

    st.markdown('</div>', unsafe_allow_html=True)  # close .cc-report


# ---------------------------------------------------------------------------
# PDF generation for download
# ---------------------------------------------------------------------------

def _build_report_pdf(report: dict, user_name: str) -> bytes:
    """Generate a downloadable PDF of the report."""
    from reportlab.lib.pagesizes import LETTER
    from reportlab.platypus import (
        SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak,
    )
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib import colors
    from reportlab.lib.units import inch

    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=LETTER,
        leftMargin=0.7 * inch, rightMargin=0.7 * inch,
        topMargin=0.7 * inch, bottomMargin=0.7 * inch,
    )
    styles = getSampleStyleSheet()

    # Custom styles
    title_style = ParagraphStyle(
        "Title", parent=styles["Title"], fontSize=18, textColor=colors.HexColor("#0B0F19"),
        spaceAfter=4, alignment=0,
    )
    sub_style = ParagraphStyle(
        "Sub", parent=styles["Normal"], fontSize=9,
        textColor=colors.HexColor("#6C7280"), spaceAfter=18,
    )
    h2_style = ParagraphStyle(
        "H2", parent=styles["Heading2"], fontSize=11, textColor=colors.HexColor("#0B0F19"),
        spaceBefore=14, spaceAfter=8, fontName="Helvetica-Bold",
    )
    body_style = ParagraphStyle(
        "Body", parent=styles["Normal"], fontSize=9.5, leading=13,
        textColor=colors.HexColor("#3D4554"),
    )

    story = []

    # Title
    report_date = report.get("report_date", "")
    try:
        d = dt.date.fromisoformat(report_date)
        date_display = d.strftime("%A %d de %B de %Y").capitalize()
    except Exception:
        date_display = report_date

    story.append(Paragraph("VINTAGE BOUTIQUE", sub_style))
    story.append(Paragraph("Reporte de Conciliación de Cierres de Caja", title_style))
    story.append(Paragraph(f"{date_display}", sub_style))

    # Overall status
    status = report.get("overall_status", "ok").lower()
    status_color = {
        "ok": colors.HexColor("#059669"),
        "warning": colors.HexColor("#D97706"),
        "error": colors.HexColor("#DC2626"),
    }.get(status, colors.HexColor("#D97706"))
    status_label = {
        "ok": "TODO CUADRA CORRECTAMENTE",
        "warning": "ATENCIÓN: HAY DISCREPANCIAS",
        "error": "INCONSISTENCIAS SERIAS DETECTADAS",
    }.get(status, "ATENCIÓN")
    status_para = Paragraph(
        f'<para><font color="{status_color.hexval()}"><b>{status_label}</b></font></para>',
        body_style,
    )
    story.append(status_para)
    story.append(Spacer(1, 6))
    story.append(Paragraph(report.get("overall_summary", ""), body_style))
    story.append(Spacer(1, 14))

    # Totals
    totals = report.get("totals_from_pdfs", {})
    if totals:
        story.append(Paragraph("Totales del día (según PDFs)", h2_style))
        data = [
            ["Forma de pago", "Monto"],
            ["Tarjeta CREDOMATIC", _fmt_q(totals.get("credomatic", 0))],
            ["Tarjeta VISANET / NEONET", _fmt_q(totals.get("visanet", 0))],
            ["Efectivo", _fmt_q(totals.get("efectivo", 0))],
            ["Depósitos bancarios", _fmt_q(totals.get("depositos_bancarios", 0))],
            ["TOTAL VENTAS", _fmt_q(totals.get("total_ventas", 0))],
        ]
        t = Table(data, colWidths=[3.5 * inch, 2.5 * inch])
        t.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#F6F7F9")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#0B0F19")),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 9),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ("TOPPADDING", (0, 0), (-1, -1), 6),
            ("ALIGN", (1, 0), (1, -1), "RIGHT"),
            ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#E8EBF0")),
            ("BACKGROUND", (0, -1), (-1, -1), colors.HexColor("#FAFBFC")),
            ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
        ]))
        story.append(t)

    # Cashier breakdown
    breakdown = report.get("cashier_breakdown", [])
    if breakdown:
        story.append(Paragraph("Detalle por cajero", h2_style))
        data = [["Tienda / Cajero", "Cierre POS", "Credomatic", "Visanet", "Efectivo", "Depósito"]]
        for c in breakdown:
            data.append([
                Paragraph(
                    f'<b>{c.get("store","?")}</b><br/>'
                    f'<font size="8" color="#6C7280">{c.get("cashier","?")}</font>',
                    body_style,
                ),
                c.get("pos_ref", ""),
                _fmt_q(c.get("credomatic", 0)),
                _fmt_q(c.get("visanet", 0)),
                _fmt_q(c.get("efectivo", 0)),
                _fmt_q(c.get("deposito", 0)),
            ])
        t = Table(data, colWidths=[1.5*inch, 1.4*inch, 0.85*inch, 0.85*inch, 0.85*inch, 0.85*inch])
        t.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#F6F7F9")),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 8),
            ("ALIGN", (2, 0), (-1, -1), "RIGHT"),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#E8EBF0")),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ("TOPPADDING", (0, 0), (-1, -1), 5),
        ]))
        story.append(t)

    # Card reconciliation
    card_rec = report.get("card_reconciliation", {})
    if card_rec:
        story.append(Paragraph("Conciliación de tarjetas", h2_style))
        for key, label in [("credomatic", "CREDOMATIC"), ("visanet_neonet", "VISANET / NEONET")]:
            r = card_rec.get(key, {})
            if not r:
                continue
            line = (
                f"<b>{label}</b> — POS: {_fmt_q(r.get('pos_total', 0))} · "
                f"Ticket: {_fmt_q(r.get('ticket_total', 0))} · "
                f"Diferencia: <b>{_fmt_q(r.get('difference', 0))}</b>"
            )
            if r.get("note"):
                line += f"<br/><font size='8' color='#6C7280'>{r['note']}</font>"
            story.append(Paragraph(line, body_style))
            story.append(Spacer(1, 6))

    # Bank reconciliation
    bank_rec = report.get("bank_reconciliation", {})
    if bank_rec:
        story.append(Paragraph("Conciliación bancaria", h2_style))
        story.append(Paragraph(
            f"Depósitos según PDFs: <b>{_fmt_q(bank_rec.get('pos_deposits_total', 0))}</b> · "
            f"Boletas: <b>{_fmt_q(bank_rec.get('bank_slips_total', 0))}</b> · "
            f"Diferencia: <b>{_fmt_q(bank_rec.get('difference', 0))}</b>",
            body_style,
        ))

        missing = bank_rec.get("missing_slips", [])
        if missing:
            story.append(Spacer(1, 6))
            story.append(Paragraph(
                f"<b><font color='#B45309'>Depósitos sin boleta ({len(missing)}):</font></b>",
                body_style,
            ))
            for m in missing:
                story.append(Paragraph(
                    f"• {m.get('pos_ref','')} — {_fmt_q(m.get('amount', 0))} "
                    f"({m.get('cashier','?')})",
                    body_style,
                ))

        orphans = bank_rec.get("orphan_slips", [])
        if orphans:
            story.append(Spacer(1, 6))
            story.append(Paragraph(
                f"<b><font color='#B91C1C'>Boletas huérfanas ({len(orphans)}):</font></b>",
                body_style,
            ))
            for o in orphans:
                story.append(Paragraph(
                    f"• Boleta #{o.get('slip_number','')} — {_fmt_q(o.get('amount', 0))} "
                    f"({o.get('date','?')})",
                    body_style,
                ))

    # VIP clients
    vips = report.get("vip_clients", [])
    if vips:
        story.append(Paragraph(f"⭐ Clientes VIP del día ({len(vips)} compras de Q 200+)", h2_style))
        data = [["Cliente", "Monto", "Cajero", "Tienda", "Pago"]]
        for v in vips:
            data.append([
                Paragraph(f'<b>{v.get("name","?")}</b>', body_style),
                _fmt_q(v.get("amount", 0)),
                v.get("cashier", "?"),
                v.get("store", "?"),
                v.get("payment_method", ""),
            ])
        t = Table(data, colWidths=[2.0*inch, 0.9*inch, 1.3*inch, 1.0*inch, 1.0*inch])
        t.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#F6F7F9")),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 8),
            ("ALIGN", (1, 0), (1, -1), "RIGHT"),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#E8EBF0")),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ("TOPPADDING", (0, 0), (-1, -1), 5),
        ]))
        story.append(t)

    # Duplicados detectados
    dups = report.get("duplicates_detected", {}) or {}
    has_dups = any([
        dups.get("pdfs"), dups.get("bank_slips"), dups.get("neonet_tickets")
    ])
    if has_dups:
        story.append(Paragraph("Duplicados detectados (excluidos del cálculo)", h2_style))
        for pdf in (dups.get("pdfs") or []):
            prev = pdf.get("previously_in_report_id") or "—"
            story.append(Paragraph(
                f"<font color='#B91C1C'><b>📄 PDF duplicado:</b> {pdf.get('pos_ref','?')}</font><br/>"
                f"<font size='8' color='#6C7280'>Archivo: {pdf.get('filename','')} · "
                f"{pdf.get('reason','')} · En reporte: {prev}</font>",
                body_style,
            ))
            story.append(Spacer(1, 4))
        for slip in (dups.get("bank_slips") or []):
            prev = slip.get("previously_in_report_id") or "—"
            story.append(Paragraph(
                f"<font color='#B91C1C'><b>🧾 Boleta duplicada:</b> J No. {slip.get('slip_number','?')}</font><br/>"
                f"<font size='8' color='#6C7280'>Archivo: {slip.get('filename','')} · "
                f"{slip.get('reason','')} · En reporte: {prev}</font>",
                body_style,
            ))
            story.append(Spacer(1, 4))
        for tk in (dups.get("neonet_tickets") or []):
            prev = tk.get("previously_in_report_id") or "—"
            story.append(Paragraph(
                f"<font color='#B91C1C'><b>💳 Ticket duplicado:</b> "
                f"{tk.get('procesador','?')} Lote {tk.get('lote','?')}</font><br/>"
                f"<font size='8' color='#6C7280'>Archivo: {tk.get('filename','')} · "
                f"{tk.get('reason','')} · En reporte: {prev}</font>",
                body_style,
            ))
            story.append(Spacer(1, 4))

    # Pendientes resueltos
    resolved = report.get("resolved_pending") or []
    if resolved:
        story.append(Paragraph("Pendientes resueltos en este análisis", h2_style))
        for r in resolved:
            ptype_label = {
                "boleta_huerfana": "Boleta huérfana",
                "deposito_sin_boleta": "Depósito sin boleta",
            }.get(r.get("pending_type", ""), "Pendiente")
            story.append(Paragraph(
                f"<font color='#15803D'><b>✓ {ptype_label}:</b> {_fmt_q(r.get('amount', 0))}</font><br/>"
                f"<font size='8' color='#6C7280'>{r.get('note','')} · "
                f"Cuadró con: {r.get('matched_with','')} · "
                f"Origen: {r.get('original_report_id','')}</font>",
                body_style,
            ))
            story.append(Spacer(1, 4))

    # Findings
    findings = report.get("findings", [])
    if findings:
        story.append(Paragraph("Hallazgos", h2_style))
        for f in findings:
            sev = f.get("severity", "warn").lower()
            sev_color = {
                "ok": "#15803D",
                "warn": "#B45309",
                "alert": "#B91C1C",
            }.get(sev, "#B45309")
            icon = {"ok": "✓", "warn": "⚠", "alert": "•"}.get(sev, "•")
            story.append(Paragraph(
                f"<font color='{sev_color}'><b>{icon} {f.get('title','')}</b></font>",
                body_style,
            ))
            story.append(Paragraph(f.get("detail", ""), body_style))
            story.append(Spacer(1, 6))

    # Footer
    story.append(Spacer(1, 24))
    story.append(Paragraph(
        f'<font size="7" color="#9CA3AF">Reporte generado por '
        f'{user_name} · {dt.datetime.now(GT_TZ).strftime("%d/%m/%Y %H:%M GT")} · '
        f'Vintage Boutique — Sistema de Asistencia y Reportes</font>',
        body_style,
    ))

    doc.build(story)
    return buf.getvalue()


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

    # Top bar: file count + clear-all button (no date picker — Claude extracts date)
    col1, col2 = st.columns([3, 1])
    with col1:
        n_total = (len(_bucket("cc_pdfs")) + len(_bucket("cc_neonet"))
                   + len(_bucket("cc_boletas")))
        # Check pending tray
        try:
            pending_count = len(cash_history.list_pending(only_open=True))
        except Exception:
            pending_count = 0
        st.markdown(
            f"<div style='display:flex;align-items:center;gap:18px;height:38px;'>"
            f"<span style='font-size:12px;color:#3D4554;'>"
            f"📂 Archivos cargados: <strong>{n_total}</strong></span>"
            f"<span style='font-size:12px;color:#3D4554;'>"
            f"⏳ Pendientes en bandeja: <strong>{pending_count}</strong></span>"
            f"<span style='font-size:11px;color:#6C7280;font-style:italic;'>"
            f"La fecha del cierre se detecta automáticamente de los PDFs.</span>"
            f"</div>",
            unsafe_allow_html=True,
        )

    with col2:
        if st.button("🗑 Limpiar todo", use_container_width=True):
            _clear_bucket("cc_pdfs")
            _clear_bucket("cc_neonet")
            _clear_bucket("cc_boletas")
            st.session_state.pop("cc_last_report", None)
            st.session_state.pop("cc_last_report_id", None)
            # Also clear upload fingerprints so user can re-upload same files
            for k in ("cc_pdfs_fp", "cc_neonet_fp", "cc_boletas_fp"):
                st.session_state.pop(k, None)
            st.rerun()

    st.markdown("---")

    # 3 sections
    st.markdown('<div class="cc-section">', unsafe_allow_html=True)
    _render_section_pdfs()
    st.markdown('</div>', unsafe_allow_html=True)

    st.markdown('<div class="cc-section">', unsafe_allow_html=True)
    _render_section_photos(
        "cc_neonet", 2, "Foto NEONET / Credomatic",
        "Tickets resumen de transacciones de tarjeta del POS.",
        "neonet",
    )

    # Manual ticket totals (in case papel térmico is illegible)
    st.markdown(
        '<div style="margin-top:14px;padding:14px 18px;background:#FAFBFC;'
        'border:1px dashed #D8DCE2;border-radius:4px;">'
        '<div style="font-size:10px;letter-spacing:2px;text-transform:uppercase;'
        'color:#6C7280;font-weight:600;margin-bottom:4px;">'
        '🖍 Totales manuales (opcional)</div>'
        '<div style="font-size:11.5px;color:#6C7280;line-height:1.5;margin-bottom:10px;">'
        'Si el papel térmico está borroso/ilegible, escribe aquí los totales que tu '
        'puedes leer del ticket físico. Si los dejas en 0.00, la IA leerá del ticket directamente.'
        '</div>',
        unsafe_allow_html=True,
    )
    col_cm, col_vn = st.columns(2)
    with col_cm:
        manual_credomatic = st.number_input(
            "Total CREDOMATIC del ticket (Q)",
            min_value=0.0,
            step=0.01,
            format="%.2f",
            value=float(st.session_state.get("cc_manual_credomatic", 0.0)),
            key="cc_manual_credomatic",
            help="Solo llenar si el ticket está parcialmente ilegible y no quieres que la IA adivine.",
        )
    with col_vn:
        manual_visanet = st.number_input(
            "Total VISANET / NEONET del ticket (Q)",
            min_value=0.0,
            step=0.01,
            format="%.2f",
            value=float(st.session_state.get("cc_manual_visanet", 0.0)),
            key="cc_manual_visanet",
            help="Solo llenar si el ticket está parcialmente ilegible y no quieres que la IA adivine.",
        )
    st.markdown('</div>', unsafe_allow_html=True)
    st.markdown('</div>', unsafe_allow_html=True)

    st.markdown('<div class="cc-section">', unsafe_allow_html=True)
    _render_section_photos(
        "cc_boletas", 3, "Boletas de Banco / Depósitos",
        "Comprobantes físicos de los depósitos hechos al banco.",
        "boleta",
    )
    st.markdown('</div>', unsafe_allow_html=True)

    # ========== Analyze button ==========
    pdfs = _bucket("cc_pdfs")
    neonet = _bucket("cc_neonet")
    boletas = _bucket("cc_boletas")

    if not pdfs:
        st.info(
            "📤 **Para empezar:** Sube al menos un PDF de cierre de caja en la Sección 1. "
            "Las fotos de NEONET y boletas de banco son opcionales — pero entre más subas, "
            "más completa será la conciliación."
        )
    else:
        st.markdown(
            f'<div class="cc-analyze-cta">'
            f'<h3>Listo para analizar y conciliar</h3>'
            f'<p>Tenemos <span class="cta-gold">{len(pdfs)} PDF(s)</span> · '
            f'<span class="cta-gold">{len(neonet)} foto(s) NEONET</span> · '
            f'<span class="cta-gold">{len(boletas)} boleta(s)</span>. '
            f'La IA cruzará los datos contra el historial y la bandeja de pendientes, '
            f'detectará duplicados y matcheará por monto sin importar la fecha.</p>'
            f'</div>',
            unsafe_allow_html=True,
        )

        col1, col2, col3 = st.columns([1, 2, 1])
        with col2:
            analyze = st.button(
                "🔬 Analizar y Conciliar con IA",
                use_container_width=True,
                type="primary",
            )

        if analyze:
            try:
                _ = st.secrets["anthropic"]["api_key"]
            except Exception:
                st.error(
                    "⚠ Falta configurar la API key de Anthropic en los secrets. "
                    "Agrega:\n```toml\n[anthropic]\napi_key = \"sk-ant-...\"\n```"
                )
                return

            with st.spinner(
                "🔬 Claude está leyendo todos los documentos, comparando contra el "
                "historial y revisando la bandeja de pendientes... Esto puede tardar "
                "30–90 segundos."
            ):
                try:
                    # Build catalog of already-processed IDs
                    catalog = cash_history.build_processed_catalog()
                    # Get open pending items
                    pending = cash_history.list_pending(only_open=True)
                    # Read manual ticket totals (override if illegible papers)
                    m_credomatic = float(st.session_state.get("cc_manual_credomatic", 0.0))
                    m_visanet = float(st.session_state.get("cc_manual_visanet", 0.0))
                    # Call Claude with full context
                    report = _call_claude(
                        pdfs, neonet, boletas, catalog, pending,
                        manual_credomatic=m_credomatic,
                        manual_visanet=m_visanet,
                    )
                    st.session_state.cc_last_report = report
                except Exception as e:
                    st.error(f"Error durante el análisis: `{e}`")
                    return

                # Save the report
                try:
                    rid = cash_history.save_report(
                        report,
                        user_email=current_user["email"],
                        n_pdfs=len(pdfs),
                        n_neonet=len(neonet),
                        n_boletas=len(boletas),
                    )
                    st.session_state.cc_last_report_id = rid
                except Exception as e:
                    st.warning(f"Análisis OK, pero no se guardó en historial: `{e}`")
                    rid = None

                # Process resolved pendings: mark them and update origin reports
                resolved = report.get("resolved_pending") or []
                resolved_count = 0
                origin_updates = 0
                if resolved and rid:
                    try:
                        for r in resolved:
                            pid = r.get("pending_id", "")
                            if pid and cash_history.mark_pending_resolved(pid, rid):
                                resolved_count += 1
                        origin_updates = cash_history.apply_resolutions_to_origin_reports(resolved)
                    except Exception as e:
                        st.warning(f"No se pudieron procesar las resoluciones: `{e}`")

                # Add new pendings from this report's missing/orphans
                new_pending_added = 0
                if rid:
                    try:
                        info = cash_history.add_pending_from_report(report, rid)
                        new_pending_added = info["added"]
                    except Exception as e:
                        st.warning(f"No se pudieron registrar nuevos pendientes: `{e}`")

                # Final success message
                msg = "✓ Análisis completo"
                bits = []
                if rid:
                    bits.append(f"guardado en historial (ID: {rid})")
                if resolved_count:
                    bits.append(f"{resolved_count} pendiente(s) resuelto(s)")
                if origin_updates:
                    bits.append(f"{origin_updates} cierre(s) antiguo(s) actualizado(s)")
                if new_pending_added:
                    bits.append(f"{new_pending_added} nuevo(s) pendiente(s) en bandeja")
                if bits:
                    msg += " · " + " · ".join(bits)
                st.success(msg)

    # Show last report if it exists
    if st.session_state.get("cc_last_report"):
        report = st.session_state["cc_last_report"]
        _render_report(report)

        # Download buttons
        st.markdown("---")
        col1, col2 = st.columns([1, 1])

        with col1:
            try:
                pdf_bytes = _build_report_pdf(report, current_user["name"])
                report_date_str = report.get("report_date", _today_gt().isoformat())
                filename = f"Conciliacion_Cierre_{report_date_str}.pdf"
                st.download_button(
                    "📥 Descargar PDF del reporte",
                    data=pdf_bytes,
                    file_name=filename,
                    mime="application/pdf",
                    use_container_width=True,
                    type="primary",
                )
            except Exception as e:
                st.error(f"Error generando PDF: `{e}`")

        with col2:
            json_bytes = json.dumps(report, indent=2, ensure_ascii=False).encode("utf-8")
            st.download_button(
                "📄 Descargar datos crudos (JSON)",
                data=json_bytes,
                file_name=f"reporte_{report.get('report_date', 'sin-fecha')}.json",
                mime="application/json",
                use_container_width=True,
            )

        st.caption(
            "💡 El PDF lo puedes guardar manualmente en tu Google Drive arrastrándolo "
            "después de descargarlo, o reenviarlo por email/WhatsApp."
        )
