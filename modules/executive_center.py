"""
Centro Ejecutivo — vista para el Lic. Juan Orozco.

3 pestañas:
  1. Resumen — KPIs grandes del último cierre y de la semana / mes
  2. Historial — tabla filtrable con todos los cierres procesados
  3. Clientes VIP — todos los clientes que han hecho compras grandes
"""

from __future__ import annotations

import datetime as dt
from collections import defaultdict
from zoneinfo import ZoneInfo

import streamlit as st

from . import cash_history
from . import cash_reports  # for _fmt_q, _build_report_pdf, _render_report


GT_TZ = ZoneInfo("America/Guatemala")


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
.block-container { padding-top: 1.5rem !important; max-width: 1200px !important; }

.ce-header {
    background: #0B0F19; color: #F9FAFB; padding: 16px 24px;
    border-radius: 6px; margin-bottom: 18px;
    display: flex; justify-content: space-between; align-items: center;
}
.ce-header .ttl { font-size: 18px; font-weight: 600; letter-spacing: -0.2px; }
.ce-header .sub {
    font-size: 10px; letter-spacing: 2.5px; text-transform: uppercase;
    color: #C9982A; font-weight: 600; margin-bottom: 2px;
}

/* KPI cards */
.ce-kpi-grid {
    display: grid; grid-template-columns: repeat(4, 1fr); gap: 0;
    background: #FFFFFF; border: 1px solid #D8DCE2; border-radius: 6px;
    overflow: hidden; margin-bottom: 18px;
}
.ce-kpi {
    padding: 18px 22px; border-right: 1px solid #E8EBF0;
}
.ce-kpi:last-child { border-right: none; }
.ce-kpi-label {
    font-size: 10px; color: #6C7280; text-transform: uppercase;
    letter-spacing: 2px; margin-bottom: 10px; font-weight: 600;
}
.ce-kpi-value {
    font-family: 'Geist Mono', monospace; font-weight: 600; font-size: 26px;
    line-height: 1; color: #0B0F19; letter-spacing: -0.6px;
}
.ce-kpi-detail {
    font-size: 11px; color: #6C7280; margin-top: 6px;
}
.ce-kpi-positive { color: #1B7340; font-weight: 600; }
.ce-kpi-negative { color: #B91C1C; font-weight: 600; }

@media (max-width: 900px) {
    .ce-kpi-grid { grid-template-columns: repeat(2, 1fr); }
    .ce-kpi:nth-child(2) { border-right: none; }
    .ce-kpi:nth-child(1), .ce-kpi:nth-child(2) {
        border-bottom: 1px solid #E8EBF0;
    }
}

/* History row */
.ce-history-row {
    background: #FFFFFF; border: 1px solid #D8DCE2; border-radius: 6px;
    padding: 14px 18px; margin-bottom: 8px;
    display: flex; align-items: center; gap: 14px;
}
.ce-history-status-dot {
    width: 10px; height: 10px; border-radius: 50%; flex-shrink: 0;
}
.ce-history-status-dot.ok { background: #1B7340; }
.ce-history-status-dot.warning { background: #D97706; }
.ce-history-status-dot.error { background: #DC2626; }
.ce-history-date {
    font-family: 'Geist Mono', monospace; font-weight: 600;
    font-size: 13px; color: #0B0F19; min-width: 110px;
}
.ce-history-summary {
    flex: 1; font-size: 12px; color: #3D4554; line-height: 1.4;
}
.ce-history-amount {
    font-family: 'Geist Mono', monospace; font-weight: 700;
    font-size: 14px; color: #0B0F19; min-width: 100px; text-align: right;
}
.ce-empty {
    text-align: center; padding: 50px 22px;
    background: #FFFFFF; border: 1px dashed #D8DCE2; border-radius: 6px;
    color: #6C7280; font-size: 13px;
}
.ce-empty strong { display: block; color: #0B0F19; margin-bottom: 8px;
    font-size: 14px; font-weight: 600; }
</style>
"""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _today_gt() -> dt.date:
    return dt.datetime.now(GT_TZ).date()


def _fmt_q(amount) -> str:
    try:
        return f"Q {float(amount):,.2f}"
    except (ValueError, TypeError):
        return "Q 0.00"


def _parse_date(s: str) -> dt.date | None:
    try:
        return dt.date.fromisoformat(s[:10])
    except Exception:
        return None


def _status_color(s: str) -> str:
    return {"ok": "ok", "warning": "warning", "error": "error"}.get(s, "warning")


def _status_label(s: str) -> str:
    return {"ok": "OK", "warning": "ADVERTENCIA", "error": "ERROR"}.get(s, s.upper())


# ---------------------------------------------------------------------------
# Tab 1: Resumen
# ---------------------------------------------------------------------------

def _render_summary_tab(history: list[dict]):
    if not history:
        st.markdown(
            '<div class="ce-empty">'
            '<strong>Sin cierres procesados todavía</strong>'
            'Ve a la pestaña <em>Cierres de Caja</em>, sube los archivos del día '
            'y genera tu primer análisis. Aparecerá aquí automáticamente.'
            '</div>',
            unsafe_allow_html=True,
        )
        return

    last = history[0]
    last_data = last.get("json_data") or {}
    last_totals = last_data.get("totals_from_pdfs") or {}

    # Compute week-to-date and month-to-date
    today = _today_gt()
    start_of_week = today - dt.timedelta(days=today.weekday())  # Monday
    start_of_month = today.replace(day=1)

    week_total = 0.0
    month_total = 0.0
    week_count = 0
    month_count = 0
    for h in history:
        d = _parse_date(h["report_date"])
        if d is None:
            continue
        if d >= start_of_week:
            week_total += h["total_ventas"]
            week_count += 1
        if d >= start_of_month:
            month_total += h["total_ventas"]
            month_count += 1

    # KPI cards
    last_date_label = last["report_date"] or "—"
    last_total = last["total_ventas"]
    last_status = _status_color(last["overall_status"])
    status_icon = {"ok": "✓", "warning": "⚠", "error": "🔴"}.get(last_status, "·")
    status_color = {"ok": "#1B7340", "warning": "#D97706", "error": "#DC2626"}.get(last_status, "#6C7280")

    st.markdown(
        f'<div class="ce-kpi-grid">'
        f'<div class="ce-kpi">'
        f'<div class="ce-kpi-label">Último cierre</div>'
        f'<div class="ce-kpi-value">{_fmt_q(last_total)}</div>'
        f'<div class="ce-kpi-detail">'
        f'<span style="color:{status_color};font-weight:600;">{status_icon}</span> '
        f'{last_date_label}'
        f'</div></div>'

        f'<div class="ce-kpi">'
        f'<div class="ce-kpi-label">Semana en curso</div>'
        f'<div class="ce-kpi-value">{_fmt_q(week_total)}</div>'
        f'<div class="ce-kpi-detail">{week_count} cierre(s) desde el lunes</div>'
        f'</div>'

        f'<div class="ce-kpi">'
        f'<div class="ce-kpi-label">Mes en curso</div>'
        f'<div class="ce-kpi-value">{_fmt_q(month_total)}</div>'
        f'<div class="ce-kpi-detail">{month_count} cierre(s) desde el 1ro</div>'
        f'</div>'

        f'<div class="ce-kpi">'
        f'<div class="ce-kpi-label">Total histórico</div>'
        f'<div class="ce-kpi-value">{len(history)}</div>'
        f'<div class="ce-kpi-detail">conciliaciones procesadas</div>'
        f'</div>'
        f'</div>',
        unsafe_allow_html=True,
    )

    # Breakdown by payment method (last cierre)
    st.markdown('##### Desglose del último cierre por forma de pago')
    cred = last_totals.get("credomatic", 0) or 0
    visa = last_totals.get("visanet", 0) or 0
    cash = last_totals.get("efectivo", 0) or 0
    total = cred + visa + cash

    if total > 0:
        chart_data = {
            "Credomatic": cred,
            "Visanet/NEONET": visa,
            "Efectivo": cash,
        }
        st.bar_chart(chart_data, height=200)

    # Last 7 days trend
    st.markdown('##### Tendencia: últimos 14 días')
    last_14 = []
    for offset in range(13, -1, -1):
        d = today - dt.timedelta(days=offset)
        day_total = sum(
            h["total_ventas"] for h in history
            if _parse_date(h["report_date"]) == d
        )
        last_14.append((d.strftime("%d/%m"), day_total))

    if any(v for _, v in last_14):
        import pandas as pd
        df = pd.DataFrame(last_14, columns=["Día", "Ventas"]).set_index("Día")
        st.line_chart(df, height=240)
    else:
        st.caption("Sin datos suficientes para graficar (necesitas más cierres procesados).")


# ---------------------------------------------------------------------------
# Tab 2: Historial filtrable
# ---------------------------------------------------------------------------

def _render_history_tab(history: list[dict], current_user: dict):
    if not history:
        st.markdown(
            '<div class="ce-empty">'
            '<strong>Sin cierres procesados todavía</strong>'
            'El historial aparecerá aquí en cuanto generes tu primer análisis.'
            '</div>',
            unsafe_allow_html=True,
        )
        return

    # ----- Filters -----
    with st.container(border=True):
        st.markdown(
            "<div style='font-size:11px;letter-spacing:2px;text-transform:uppercase;"
            "color:#6C7280;font-weight:600;margin-bottom:10px;'>"
            "🔍 Filtros</div>",
            unsafe_allow_html=True,
        )
        col1, col2, col3, col4 = st.columns(4)

        # Date range
        all_dates = [
            _parse_date(h["report_date"]) for h in history
            if _parse_date(h["report_date"])
        ]
        min_d = min(all_dates) if all_dates else _today_gt() - dt.timedelta(days=30)
        max_d = max(all_dates) if all_dates else _today_gt()

        with col1:
            date_from = st.date_input(
                "Desde",
                value=min_d,
                min_value=min_d,
                max_value=max_d,
                format="DD/MM/YYYY",
                key="hist_date_from",
            )
        with col2:
            date_to = st.date_input(
                "Hasta",
                value=max_d,
                min_value=min_d,
                max_value=max_d,
                format="DD/MM/YYYY",
                key="hist_date_to",
            )

        # Store filter (extract from JSON)
        stores_in_history = set()
        cashiers_in_history = set()
        for h in history:
            data = h.get("json_data") or {}
            for c in (data.get("cashier_breakdown") or []):
                if c.get("store"):
                    stores_in_history.add(c["store"])
                if c.get("cashier"):
                    cashiers_in_history.add(c["cashier"])

        with col3:
            store_opts = ["Todas"] + sorted(stores_in_history)
            store_choice = st.selectbox("Tienda", store_opts, key="hist_store")

        with col4:
            cashier_opts = ["Todos"] + sorted(cashiers_in_history)
            cashier_choice = st.selectbox("Cajero", cashier_opts, key="hist_cashier")

        col5, col6 = st.columns(2)
        with col5:
            status_choice = st.selectbox(
                "Estado",
                ["Todos", "✓ Sin problemas (ok)", "⚠ Con advertencias (warning)",
                 "🔴 Con errores (error)"],
                key="hist_status",
            )
        with col6:
            search = st.text_input(
                "Buscar por número de cierre POS (opcional)",
                placeholder="Ej. POS/2026/05/12/7488",
                key="hist_search",
            )

    # ----- Apply filters -----
    filtered = []
    for h in history:
        d = _parse_date(h["report_date"])
        if d is None or d < date_from or d > date_to:
            continue
        if status_choice != "Todos":
            status_key = status_choice.split("(")[-1].rstrip(")")
            if h["overall_status"] != status_key:
                continue
        data = h.get("json_data") or {}
        cashiers = [c for c in (data.get("cashier_breakdown") or [])]
        if store_choice != "Todas":
            if not any(c.get("store") == store_choice for c in cashiers):
                continue
        if cashier_choice != "Todos":
            if not any(c.get("cashier") == cashier_choice for c in cashiers):
                continue
        if search.strip():
            s = search.strip().lower()
            refs = [str(c.get("pos_ref", "")).lower() for c in cashiers]
            if not any(s in r for r in refs):
                continue
        filtered.append(h)

    st.markdown(
        f"<div style='margin:14px 0 12px;font-size:11px;letter-spacing:2px;"
        f"text-transform:uppercase;color:#6C7280;font-weight:600;'>"
        f"{len(filtered)} resultado(s) encontrados</div>",
        unsafe_allow_html=True,
    )

    if not filtered:
        st.caption("No hay cierres que coincidan con esos filtros.")
        return

    # ----- Render list -----
    for h in filtered:
        status = _status_color(h["overall_status"])
        d_human = ""
        d = _parse_date(h["report_date"])
        if d:
            try:
                d_human = d.strftime("%a %d/%b").replace(".", "").lower()
            except Exception:
                pass

        col_main, col_actions = st.columns([5, 1])

        with col_main:
            st.markdown(
                f'<div class="ce-history-row">'
                f'<div class="ce-history-status-dot {status}"></div>'
                f'<div class="ce-history-date">{h["report_date"]}<br>'
                f'<span style="font-size:10px;color:#6C7280;font-weight:400;">{d_human}</span>'
                f'</div>'
                f'<div class="ce-history-summary">{h["summary"][:200]}</div>'
                f'<div class="ce-history-amount">{_fmt_q(h["total_ventas"])}</div>'
                f'</div>',
                unsafe_allow_html=True,
            )

        with col_actions:
            with st.popover("⋮", use_container_width=True):
                # Re-generate PDF button
                if st.button("📄 Ver / Descargar PDF",
                             key=f"pdf_{h['id']}", use_container_width=True):
                    st.session_state["hist_show_id"] = h["id"]
                    st.rerun()
                if current_user["role"] == "admin":
                    if st.button("🗑 Eliminar",
                                 key=f"del_{h['id']}", use_container_width=True):
                        if cash_history.delete_history_entry(h["id"]):
                            st.success("✓ Eliminado")
                            st.rerun()

    # If a row was clicked → show full report inline + download
    show_id = st.session_state.get("hist_show_id")
    if show_id:
        entry = cash_history.get_report_by_id(show_id)
        if entry and entry.get("json_data"):
            st.markdown("---")
            col_close, col_dl = st.columns([3, 1])
            with col_close:
                st.markdown(
                    f"<div style='font-size:11px;letter-spacing:2px;"
                    f"text-transform:uppercase;color:#6C7280;font-weight:600;'>"
                    f"Reporte abierto: {entry['report_date']} · ID: {entry['id']}</div>",
                    unsafe_allow_html=True,
                )
            with col_dl:
                try:
                    pdf_bytes = cash_reports._build_report_pdf(
                        entry["json_data"], current_user["name"]
                    )
                    st.download_button(
                        "📥 Descargar PDF",
                        data=pdf_bytes,
                        file_name=f"Conciliacion_{entry['report_date']}.pdf",
                        mime="application/pdf",
                        use_container_width=True,
                        type="primary",
                        key=f"dl_hist_{entry['id']}",
                    )
                except Exception as e:
                    st.error(f"Error generando PDF: `{e}`")

            if st.button("✕ Cerrar vista", key="close_hist_view"):
                st.session_state.pop("hist_show_id", None)
                st.rerun()

            cash_reports._render_report(entry["json_data"])


# ---------------------------------------------------------------------------
# Tab 3: Clientes VIP
# ---------------------------------------------------------------------------

def _render_vip_tab(history: list[dict]):
    if not history:
        st.markdown(
            '<div class="ce-empty">'
            '<strong>Sin datos de clientes</strong>'
            'Los clientes VIP aparecerán cuando proceses al menos un cierre.'
            '</div>',
            unsafe_allow_html=True,
        )
        return

    # Aggregate all VIPs across all history
    all_vips = []  # list of {name, amount, cashier, store, payment_method, date, pos_ref}
    for h in history:
        data = h.get("json_data") or {}
        for v in (data.get("vip_clients") or []):
            all_vips.append({
                "name": (v.get("name") or "").strip(),
                "amount": float(v.get("amount") or 0),
                "cashier": v.get("cashier", ""),
                "store": v.get("store", ""),
                "payment_method": v.get("payment_method", ""),
                "pos_ref": v.get("pos_ref", ""),
                "date": h["report_date"],
            })

    if not all_vips:
        st.markdown(
            '<div class="ce-empty">'
            '<strong>Aún no se han identificado clientes VIP</strong>'
            'Un cliente VIP es alguien que hizo una compra individual de Q 200 o más. '
            'Cuando proceses cierres con compras grandes, aparecerán aquí.'
            '</div>',
            unsafe_allow_html=True,
        )
        return

    # Filters
    col1, col2, col3 = st.columns(3)
    with col1:
        view = st.selectbox(
            "Ver",
            ["Top compras individuales", "Top clientes (por suma total)"],
            key="vip_view",
        )
    with col2:
        # Date range
        all_dates = [_parse_date(v["date"]) for v in all_vips if _parse_date(v["date"])]
        if all_dates:
            min_d = min(all_dates)
            max_d = max(all_dates)
        else:
            min_d = _today_gt() - dt.timedelta(days=30)
            max_d = _today_gt()
        days_back = st.selectbox(
            "Período",
            ["Todo el historial", "Últimos 7 días", "Últimos 30 días",
             "Últimos 90 días", "Este mes"],
            index=0,
            key="vip_days",
        )
    with col3:
        min_amount = st.number_input(
            "Monto mínimo (Q)",
            min_value=200, max_value=100000, value=200, step=100,
            key="vip_min_amount",
        )

    today = _today_gt()
    cutoff = None
    if days_back == "Últimos 7 días":
        cutoff = today - dt.timedelta(days=7)
    elif days_back == "Últimos 30 días":
        cutoff = today - dt.timedelta(days=30)
    elif days_back == "Últimos 90 días":
        cutoff = today - dt.timedelta(days=90)
    elif days_back == "Este mes":
        cutoff = today.replace(day=1)

    # Filter
    def _passes(v):
        if v["amount"] < min_amount:
            return False
        if cutoff:
            d = _parse_date(v["date"])
            if d is None or d < cutoff:
                return False
        return True

    filtered = [v for v in all_vips if _passes(v)]

    if not filtered:
        st.info("Sin compras VIP en el rango seleccionado.")
        return

    st.markdown(
        f"<div style='margin:14px 0 12px;font-size:11px;letter-spacing:2px;"
        f"text-transform:uppercase;color:#6C7280;font-weight:600;'>"
        f"{len(filtered)} compra(s) encontradas</div>",
        unsafe_allow_html=True,
    )

    if view == "Top compras individuales":
        # Show each transaction, sorted by amount desc
        filtered.sort(key=lambda x: x["amount"], reverse=True)
        rows = []
        for v in filtered[:50]:  # top 50
            method_color = {
                "CREDOMATIC": "#C9982A",
                "VISANET": "#1D4ED8",
                "Efectivo": "#1B7340",
            }.get(v["payment_method"], "#6C7280")
            rows.append(
                f'<tr>'
                f'<td><strong>{v["name"] or "(sin nombre)"}</strong></td>'
                f'<td style="text-align:right;font-family:Geist Mono,monospace;'
                f'font-weight:700;">{_fmt_q(v["amount"])}</td>'
                f'<td>{v["date"]}</td>'
                f'<td>{v["cashier"]}</td>'
                f'<td>{v["store"]}</td>'
                f'<td><span style="color:{method_color};font-weight:600;font-size:10px;">'
                f'{v["payment_method"]}</span></td>'
                f'</tr>'
            )
        st.markdown(
            '<table style="width:100%;border-collapse:collapse;font-size:12px;">'
            '<thead><tr style="background:#F6F7F9;">'
            '<th style="padding:9px 12px;text-align:left;font-size:9.5px;'
            'letter-spacing:1.5px;text-transform:uppercase;font-weight:600;">Cliente</th>'
            '<th style="padding:9px 12px;text-align:right;font-size:9.5px;'
            'letter-spacing:1.5px;text-transform:uppercase;font-weight:600;">Monto</th>'
            '<th style="padding:9px 12px;text-align:left;font-size:9.5px;'
            'letter-spacing:1.5px;text-transform:uppercase;font-weight:600;">Fecha</th>'
            '<th style="padding:9px 12px;text-align:left;font-size:9.5px;'
            'letter-spacing:1.5px;text-transform:uppercase;font-weight:600;">Cajero</th>'
            '<th style="padding:9px 12px;text-align:left;font-size:9.5px;'
            'letter-spacing:1.5px;text-transform:uppercase;font-weight:600;">Tienda</th>'
            '<th style="padding:9px 12px;text-align:left;font-size:9.5px;'
            'letter-spacing:1.5px;text-transform:uppercase;font-weight:600;">Pago</th>'
            '</tr></thead><tbody>'
            + "".join(f'<tr style="border-bottom:1px solid #E8EBF0;">{r[4:]}'
                     for r in rows) +
            '</tbody></table>',
            unsafe_allow_html=True,
        )
        if len(filtered) > 50:
            st.caption(f"Mostrando top 50 de {len(filtered)}. Acota filtros para ver el resto.")
    else:
        # Aggregate by client name
        agg = defaultdict(lambda: {
            "total": 0.0, "count": 0, "last_date": "", "last_store": "",
            "payment_methods": set(),
        })
        for v in filtered:
            key = (v["name"] or "(sin nombre)").upper().strip()
            agg[key]["total"] += v["amount"]
            agg[key]["count"] += 1
            if v["date"] > agg[key]["last_date"]:
                agg[key]["last_date"] = v["date"]
                agg[key]["last_store"] = v["store"]
            agg[key]["payment_methods"].add(v["payment_method"])

        ranked = sorted(agg.items(), key=lambda x: x[1]["total"], reverse=True)
        rows = []
        for i, (name, data) in enumerate(ranked[:50], 1):
            methods = ", ".join(sorted(data["payment_methods"]))
            rows.append(
                f'<tr style="border-bottom:1px solid #E8EBF0;">'
                f'<td style="padding:9px 12px;font-family:Geist Mono,monospace;'
                f'color:#9CA3AF;width:30px;">{i}</td>'
                f'<td style="padding:9px 12px;"><strong>{name}</strong></td>'
                f'<td style="padding:9px 12px;text-align:right;'
                f'font-family:Geist Mono,monospace;font-weight:700;">'
                f'{_fmt_q(data["total"])}</td>'
                f'<td style="padding:9px 12px;text-align:center;">{data["count"]}</td>'
                f'<td style="padding:9px 12px;font-family:Geist Mono,monospace;'
                f'font-size:11px;">{data["last_date"]}</td>'
                f'<td style="padding:9px 12px;">{data["last_store"]}</td>'
                f'<td style="padding:9px 12px;font-size:10px;color:#6C7280;">{methods}</td>'
                f'</tr>'
            )
        st.markdown(
            '<table style="width:100%;border-collapse:collapse;font-size:12px;">'
            '<thead><tr style="background:#F6F7F9;">'
            '<th style="padding:9px 12px;text-align:left;font-size:9.5px;'
            'letter-spacing:1.5px;text-transform:uppercase;font-weight:600;">#</th>'
            '<th style="padding:9px 12px;text-align:left;font-size:9.5px;'
            'letter-spacing:1.5px;text-transform:uppercase;font-weight:600;">Cliente</th>'
            '<th style="padding:9px 12px;text-align:right;font-size:9.5px;'
            'letter-spacing:1.5px;text-transform:uppercase;font-weight:600;">'
            'Total acumulado</th>'
            '<th style="padding:9px 12px;text-align:center;font-size:9.5px;'
            'letter-spacing:1.5px;text-transform:uppercase;font-weight:600;">'
            'Visitas</th>'
            '<th style="padding:9px 12px;text-align:left;font-size:9.5px;'
            'letter-spacing:1.5px;text-transform:uppercase;font-weight:600;">'
            'Última compra</th>'
            '<th style="padding:9px 12px;text-align:left;font-size:9.5px;'
            'letter-spacing:1.5px;text-transform:uppercase;font-weight:600;">'
            'Tienda</th>'
            '<th style="padding:9px 12px;text-align:left;font-size:9.5px;'
            'letter-spacing:1.5px;text-transform:uppercase;font-weight:600;">'
            'Métodos pago</th>'
            '</tr></thead><tbody>'
            + "".join(rows) +
            '</tbody></table>',
            unsafe_allow_html=True,
        )


# ---------------------------------------------------------------------------
# Tab 4: Pendientes
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Tab 4: Pendientes — inline resolution flow
# ---------------------------------------------------------------------------

def _render_pending_row(p: dict, current_user: dict, row_type: str,
                         all_open_same_type: list[dict]) -> None:
    """
    Render a single pending row with an "Adjuntar" expander that lets the user
    upload the missing document inline and resolve the pending(s).
    """
    d = p.get("details", {})

    # Header line
    col_main, col_action = st.columns([5, 1])
    with col_main:
        if row_type == "boleta_huerfana":
            primary = f"J No. {d.get('slip_number', '?')}"
            secondary = f"Boleta del {d.get('date', '?')}"
        elif row_type == "deposito_sin_boleta":
            primary = d.get("pos_ref", "?")
            secondary = d.get("cashier", "?")
        else:  # diferencia_interna_cierre
            primary = f"{d.get('cashier', '?')}"
            secondary = f"{d.get('pos_ref', '?')} · {d.get('store', '')}"

        st.markdown(
            f'<div class="ce-history-row">'
            f'<div class="ce-history-status-dot warning"></div>'
            f'<div class="ce-history-date">{primary}<br>'
            f'<span style="font-size:10px;color:#6C7280;font-weight:400;">'
            f'{secondary}</span></div>'
            f'<div class="ce-history-summary">'
            f'Origen: cierre <code>{p["origin_report_id"]}</code> '
            f'(reporte del {p["origin_date"]})'
            f'</div>'
            f'<div class="ce-history-amount">{_fmt_q(p["amount"])}</div>'
            f'</div>',
            unsafe_allow_html=True,
        )
    with col_action:
        if current_user["role"] in ("admin", "viewer"):
            if st.button("🗑", key=f"del_pend_{p['id']}",
                         help="Eliminar este pendiente (úsalo si sabes que ya no aplica)"):
                if cash_history.delete_pending(p["id"]):
                    st.success("Eliminado")
                    st.rerun()

    # Inline resolution flow (only admin + viewer can resolve)
    if current_user["role"] not in ("admin", "viewer"):
        return

    if row_type == "diferencia_interna_cierre":
        # Two options: attach slip OR manual mark as repaid
        with st.expander("📎 Resolver este faltante", expanded=False):
            _render_internal_diff_resolver(p, current_user)
    else:
        label = (
            "📎 Adjuntar PDF de cierre del POS para resolver"
            if row_type == "boleta_huerfana"
            else "📎 Adjuntar boleta del banco para resolver"
        )
        with st.expander(label, expanded=False):
            _render_inline_resolver(p, row_type, all_open_same_type, current_user)


def _render_internal_diff_resolver(p: dict, current_user: dict) -> None:
    """Resolver for diferencia_interna_cierre — two paths: manual or boleta."""
    d = p.get("details", {})

    st.markdown(
        f"<div style='background:#FAFBFC;border:1px solid #E8EBF0;border-radius:4px;"
        f"padding:12px 16px;margin:6px 0 14px;font-size:12.5px;line-height:1.6;color:#3D4554;'>"
        f"<strong>{d.get('cashier','?')}</strong> debe reponer "
        f"<strong style='color:#B91C1C;'>{_fmt_q(p['amount'])}</strong> del cierre "
        f"<code>{d.get('pos_ref','?')}</code>."
        f"</div>",
        unsafe_allow_html=True,
    )

    st.markdown(
        "<div style='font-size:11px;letter-spacing:2px;text-transform:uppercase;"
        "color:#0B0F19;font-weight:700;margin-bottom:8px;'>"
        "Opción 1: Repuesto en efectivo (sin boleta)</div>",
        unsafe_allow_html=True,
    )
    st.caption("Usa esta opción si el cajero entregó el efectivo directamente al Lic.")
    note = st.text_input(
        "Nota (opcional, ej. fecha en que entregó el efectivo)",
        placeholder="Ej. Daisy entregó Q 0.50 al Lic. el 15/05/2026",
        key=f"manual_note_{p['id']}",
    )
    if st.button(
        "✓ Marcar como repuesto manualmente",
        key=f"manual_resolve_{p['id']}",
        type="primary",
        use_container_width=True,
    ):
        try:
            result = cash_history.resolve_pending_manually(
                pending_id=p["id"],
                user_email=current_user["email"],
                note=note or "Repuesto en efectivo (resolución manual)",
            )
            if result["resolved"]:
                st.success(
                    f"✅ Pendiente resuelto · "
                    f"{result['origin_reports_updated']} cierre(s) actualizado(s). "
                    f"La página se recargará."
                )
                st.balloons()
                cash_history.list_pending.clear()
                cash_history.list_history.clear()
                import time
                time.sleep(1)
                st.rerun()
            else:
                st.error("No se pudo resolver. Recarga la página.")
        except Exception as e:
            st.error(f"Error: `{e}`")

    st.markdown(
        "<div style='margin:18px 0 8px;font-size:11px;letter-spacing:2px;"
        "text-transform:uppercase;color:#0B0F19;font-weight:700;'>"
        "Opción 2: Boleta de depósito por la diferencia</div>",
        unsafe_allow_html=True,
    )
    st.caption("Usa esta opción si el cajero depositó la diferencia al banco con una boleta aparte.")

    # Reuse the standard slip resolver — same flow as deposito_sin_boleta
    _render_inline_resolver(p, "deposito_sin_boleta", [p], current_user)


def _render_inline_resolver(p: dict, row_type: str,
                              all_open_same_type: list[dict],
                              current_user: dict) -> None:
    """
    Versatile inline resolver:
      - Accepts any visual format (PDF, JPG, PNG, WEBP, HEIC)
      - Auto-detects whether the file is a boleta or POS-closing PDF
      - Searches the ENTIRE pending tray (all types) for matches by amount
      - Resolves cross-type when both sides exist (boleta huérfana + depósito sin boleta)
    """
    file_key = f"resolve_upload_{p['id']}"
    extract_state_key = f"resolve_extract_{p['id']}"

    uploaded = st.file_uploader(
        "Subir documento (boleta de banco o PDF de cierre)",
        type=["pdf", "jpg", "jpeg", "png", "webp", "heic"],
        key=file_key,
        label_visibility="collapsed",
    )
    st.caption(
        "📎 Sube cualquier documento relacionado: foto/PDF de la boleta del banco, "
        "o PDF de cierre del POS. La app detecta automáticamente qué es y busca "
        "matches en toda la bandeja de pendientes."
    )

    if not uploaded:
        st.session_state.pop(extract_state_key, None)
        return

    # Extract (only once per upload)
    extract = st.session_state.get(extract_state_key)
    if extract is None or extract.get("filename") != uploaded.name:
        with st.spinner("🔬 Leyendo el documento..."):
            try:
                uploaded.seek(0)
                file_bytes = uploaded.read()
                mime = uploaded.type or ""
                data = cash_reports.extract_auto(file_bytes, mime, uploaded.name)
                doc_type = data.get("document_type", "otro")
                if doc_type == "boleta":
                    extract = {
                        "kind": "slip",
                        "filename": uploaded.name,
                        "ref": str(data.get("slip_number", "")),
                        "amount": float(data.get("amount") or 0),
                        "date": data.get("date", ""),
                        "confidence": data.get("confidence", "medium"),
                    }
                elif doc_type == "pdf_cierre":
                    extract = {
                        "kind": "pdf",
                        "filename": uploaded.name,
                        "ref": str(data.get("pos_ref", "")),
                        "amount": float(data.get("amount") or 0),
                        "cashier": data.get("cashier", ""),
                        "store": data.get("store", ""),
                        "confidence": data.get("confidence", "medium"),
                    }
                else:
                    extract = {
                        "kind": "unknown",
                        "filename": uploaded.name,
                        "ref": "",
                        "amount": 0,
                        "confidence": "low",
                    }
                st.session_state[extract_state_key] = extract
            except Exception as e:
                st.error(f"No se pudo leer el documento: `{e}`")
                return

    # Unknown document type
    if extract["kind"] == "unknown":
        st.error(
            "🚫 **No se reconoció el documento.** Esperábamos una boleta de banco o un "
            "PDF de cierre del POS. Verifica que la imagen sea legible y que sea el "
            "documento correcto."
        )
        return

    # Show extracted data
    ref = extract["ref"]
    amount = extract["amount"]
    confidence = extract.get("confidence", "medium")
    cfg_color = {"high": "#1B7340", "medium": "#D97706", "low": "#B91C1C"}.get(confidence, "#6C7280")
    type_label = "📤 Boleta de banco" if extract["kind"] == "slip" else "📄 PDF de cierre del POS"
    ref_label = "J No." if extract["kind"] == "slip" else "POS ref"

    extra_info = ""
    if extract["kind"] == "pdf":
        if extract.get("cashier"):
            extra_info = f"  ·  <strong>Cajero:</strong> {extract['cashier']}"
        if extract.get("store"):
            extra_info += f"  ·  <strong>Tienda:</strong> {extract['store']}"
    elif extract.get("date"):
        extra_info = f"  ·  <strong>Fecha:</strong> {extract['date']}"

    st.markdown(
        f"<div style='background:#FAFBFC;border:1px solid #E8EBF0;border-radius:4px;"
        f"padding:12px 16px;margin:10px 0;'>"
        f"<div style='font-size:10px;letter-spacing:2px;text-transform:uppercase;"
        f"color:#6C7280;font-weight:600;margin-bottom:6px;'>"
        f"Datos extraídos · {type_label}</div>"
        f"<div style='font-size:13px;color:#0B0F19;line-height:1.6;'>"
        f"<strong>{ref_label}:</strong> <code>{ref or '(no detectado)'}</code>  ·  "
        f"<strong>Monto:</strong> {_fmt_q(amount)}  ·  "
        f"<strong>Confianza:</strong> <span style='color:{cfg_color};'>{confidence}</span>"
        f"{extra_info}"
        f"</div></div>",
        unsafe_allow_html=True,
    )

    if not ref:
        st.warning(
            "⚠ No se pudo extraer el identificador del documento. "
            "Verifica que la imagen sea legible. Si la confianza es baja, "
            "puedes intentar con una foto más clara."
        )
        return

    # Duplicate check against history
    if extract["kind"] == "slip":
        exists, where = cash_history.slip_number_exists_in_history(ref)
    else:
        exists, where = cash_history.pos_ref_exists_in_history(ref)
    if exists:
        st.error(
            f"🚫 **Este documento ya está registrado en el historial.** "
            f"`{ref}` ya existe en `{where}`. No se puede usar de nuevo."
        )
        return

    # ========================================================================
    # SEARCH FOR MATCHES ACROSS THE ENTIRE PENDING TRAY (versatile mode)
    # ========================================================================
    # The uploaded doc can match pendings of any type that complement it:
    #   - Uploaded a boleta? It matches deposito_sin_boleta or diferencia_interna
    #   - Uploaded a pdf_cierre? It matches boleta_huerfana (its deposit total)
    try:
        all_pending = cash_history.list_pending(only_open=True)
    except Exception as e:
        st.error(f"No se pudo leer la bandeja: `{e}`")
        return

    if extract["kind"] == "slip":
        # Boletas resolve depósitos sin boleta and diferencias internas
        candidates = [
            x for x in all_pending
            if x["type"] in ("deposito_sin_boleta", "diferencia_interna_cierre")
        ]
    else:
        # PDFs resolve boletas huérfanas
        candidates = [
            x for x in all_pending if x["type"] == "boleta_huerfana"
        ]

    # Find combinations whose sum matches the uploaded amount
    combos = cash_history.find_pending_combinations(
        amount, candidates, tolerance=1.0, max_size=3
    )

    # ========================================================================
    # CASE A: No candidates of complementary type at all
    # ========================================================================
    if not candidates:
        st.warning(
            "⚠ No hay pendientes en la bandeja que puedan cuadrar con este documento. "
            "Quizás ya están todos resueltos. Si crees que este documento corresponde a un "
            "nuevo cierre, súbelo desde **Cierres de Caja** en lugar de aquí."
        )
        return

    # ========================================================================
    # CASE B: One or more combinations found
    # ========================================================================
    if combos:
        # Highlight combos that include p (the pending the user is currently viewing)
        combos_including_p = [c for c in combos if any(x["id"] == p["id"] for x in c)]
        combos_other = [c for c in combos if not any(x["id"] == p["id"] for x in c)]

        if combos_including_p:
            st.success(
                f"✅ **Encontramos una coincidencia que incluye este pendiente.** "
                f"Confirma cuál aplicar:"
            )
            for idx, combo in enumerate(combos_including_p[:5]):
                _render_combo_choice(combo, amount, ref, extract['filename'], idx, p, "p")

        if combos_other:
            st.info(
                f"🔗 **También hay otras coincidencias por monto en la bandeja.** "
                f"Si crees que el documento que subiste corresponde a uno de estos, puedes resolverlos:"
            )
            for idx, combo in enumerate(combos_other[:5]):
                _render_combo_choice(combo, amount, ref, extract['filename'], idx, p, "other")
        return

    # ========================================================================
    # CASE C: No combinations matched exactly — show closest options
    # ========================================================================
    # Find single pendings close in amount (partial or excess scenarios)
    if extract["kind"] == "slip":
        # Slip with no combo → could be partial payment of one pending or excess
        # Show the pending p (the one user opened) as the primary partial/excess option
        diff = amount - p["amount"]
        if abs(diff) <= 1.0:
            # Exact (shouldn't reach here since combos would catch it, but defensive)
            st.success(
                f"✅ **Cuadra con este pendiente** ({_fmt_q(amount)} ≈ {_fmt_q(p['amount'])})."
            )
            if st.button(
                "Resolver pendiente",
                key=f"resolve_exact_{p['id']}",
                type="primary",
                use_container_width=True,
            ):
                _do_resolve_pendings(
                    [p],
                    resolver_label=f"inline-{ref}",
                    slip_or_pdf_id=ref,
                    amount=amount,
                    note=f"Resuelto inline subiendo {extract['filename']}",
                )
            return
        elif diff < -1.0:
            # Partial payment
            falt = abs(diff)
            st.warning(
                f"⚠ **Pago parcial.** El pendiente que abriste es de "
                f"{_fmt_q(p['amount'])} pero el documento es de {_fmt_q(amount)}. "
                f"Faltan **{_fmt_q(falt)}**.\n\n"
                f"Al resolver, marcaremos este pendiente como cubierto y crearemos un nuevo "
                f"pendiente de {_fmt_q(falt)} para cuando suban el complemento."
            )
            if st.button(
                f"Aceptar pago parcial y crear pendiente por {_fmt_q(falt)}",
                key=f"resolve_partial_{p['id']}",
                type="primary",
                use_container_width=True,
            ):
                _do_resolve_pendings_partial(
                    p,
                    resolver_label=f"inline-{ref}",
                    slip_or_pdf_id=ref,
                    amount=amount,
                    remainder=falt,
                    note=f"Pago parcial inline subiendo {extract['filename']}",
                )
            return
        else:
            # Excess
            excess = diff
            st.error(
                f"🚨 **Excedente sospechoso.** El pendiente que abriste es de "
                f"{_fmt_q(p['amount'])} pero el documento es de {_fmt_q(amount)}. "
                f"Sobran **{_fmt_q(excess)}**.\n\n"
                f"Esta diferencia no se resuelve automáticamente. Posibles causas:\n"
                f"- El documento cubre **más de un pendiente** — pero ninguna combinación cuadra\n"
                f"- El monto se ingresó mal en algún lado\n"
                f"- Hay un depósito adicional que aún no se ha registrado\n\n"
                f"Revisa manualmente antes de continuar."
            )
            return

    # Kind == pdf, no combos
    st.warning(
        f"⚠ Ningún pendiente cuadra exactamente con este monto ({_fmt_q(amount)}). "
        f"Quizás el documento corresponde a un cierre nuevo. En ese caso, súbelo "
        f"desde **Cierres de Caja**."
    )


def _render_combo_choice(combo: list[dict], amount: float, ref: str,
                          filename: str, idx: int, p: dict, suffix: str) -> None:
    """Render one combination as a clickable card with a resolve button."""
    ids_in_combo = [x["id"] for x in combo]
    total = sum(x["amount"] for x in combo)
    descs = []
    type_emoji = {
        "boleta_huerfana": "🧾",
        "deposito_sin_boleta": "📤",
        "diferencia_interna_cierre": "⚖️",
    }
    for x in combo:
        xd = x.get("details", {})
        emoji = type_emoji.get(x["type"], "•")
        if x["type"] == "boleta_huerfana":
            descs.append(f"{emoji} J No. {xd.get('slip_number','?')} ({_fmt_q(x['amount'])})")
        elif x["type"] == "deposito_sin_boleta":
            descs.append(
                f"{emoji} {xd.get('pos_ref','?')} · {xd.get('cashier','?')} ({_fmt_q(x['amount'])})"
            )
        else:  # diferencia_interna_cierre
            descs.append(
                f"{emoji} {xd.get('cashier','?')} ({xd.get('pos_ref','?')}) · "
                f"diferencia {_fmt_q(x['amount'])}"
            )

    with st.container(border=True):
        st.markdown(
            f"<div style='font-size:12.5px;color:#0B0F19;line-height:1.6;'>"
            f"<strong>Combinación {idx+1}:</strong><br>{'<br>'.join(descs)}<br>"
            f"<span style='color:#6C7280;'>Suma total: {_fmt_q(total)}</span>"
            f"</div>",
            unsafe_allow_html=True,
        )
        if st.button(
            f"✓ Resolver con esta combinación ({len(combo)} pendiente(s))",
            key=f"resolve_combo_{p['id']}_{suffix}_{idx}",
            type="primary",
            use_container_width=True,
        ):
            _do_resolve_pendings(
                combo,
                resolver_label=f"inline-{ref}",
                slip_or_pdf_id=ref,
                amount=amount,
                note=f"Resuelto inline con {filename} (combinación de {len(combo)})",
            )


def _do_resolve_pendings(pendings: list[dict], resolver_label: str,
                          slip_or_pdf_id: str, amount: float, note: str):
    """Mark pendings as resolved and update origin reports."""
    try:
        result = cash_history.resolve_pending_inline(
            pending_ids=[x["id"] for x in pendings],
            resolver_report_id=resolver_label,
            slip_or_pdf_id=slip_or_pdf_id,
            amount=amount,
            note=note,
        )
        st.success(
            f"✅ {result['resolved']} pendiente(s) resuelto(s) · "
            f"{result['origin_reports_updated']} cierre(s) origen actualizado(s). "
            f"La página se recargará en un momento."
        )
        st.balloons()
        # Clear caches so the row disappears
        cash_history.list_pending.clear()
        cash_history.list_history.clear()
        # Trigger rerun after a brief moment so the user sees the success
        import time
        time.sleep(1)
        st.rerun()
    except Exception as e:
        st.error(f"Error al resolver: `{e}`")


def _do_resolve_pendings_partial(p: dict, resolver_label: str,
                                   slip_or_pdf_id: str, amount: float,
                                   remainder: float, note: str):
    """Resolve a pending partially and create a remainder pending."""
    try:
        result = cash_history.resolve_pending_inline(
            pending_ids=[p["id"]],
            resolver_report_id=resolver_label,
            slip_or_pdf_id=slip_or_pdf_id,
            amount=amount,
            note=note,
        )
        new_pid = cash_history.create_partial_remainder_pending(
            original_pending=p,
            remainder_amount=remainder,
            note=note,
        )
        st.success(
            f"✅ Pendiente cubierto parcialmente · Nuevo pendiente creado por "
            f"{_fmt_q(remainder)} (ID: {new_pid}). La página se recargará."
        )
        cash_history.list_pending.clear()
        cash_history.list_history.clear()
        import time
        time.sleep(1)
        st.rerun()
    except Exception as e:
        st.error(f"Error al resolver parcialmente: `{e}`")


def _render_pending_tab(current_user: dict):
    try:
        pending = cash_history.list_pending(only_open=True)
    except Exception as e:
        st.error(f"No se pudo cargar la bandeja: `{e}`")
        return

    st.markdown(
        "<div style='font-size:12px;color:#3D4554;line-height:1.6;margin-bottom:14px;'>"
        "<strong>Bandeja de pendientes:</strong> aquí quedan boletas de banco sin "
        "depósito correspondiente, depósitos del POS sin boleta de banco, y "
        "<strong>faltantes internos de caja</strong> (efectivo que el cajero debe reponer). "
        "<strong>La próxima vez que ejecutes un análisis</strong>, la IA intentará "
        "automáticamente cuadrarlos con los nuevos archivos que subas (por monto)."
        "</div>",
        unsafe_allow_html=True,
    )

    # Utilities: reparations available to admin AND viewer (Lic. lleva el proceso)
    if current_user["role"] in ("admin", "viewer"):
        with st.expander("🔧 Utilidades de reparación", expanded=False):
            st.caption(
                "**Reparaciones one-time** para limpiar el historial cuando hay reportes "
                "antiguos con problemas (de versiones anteriores del sistema o por "
                "alucinaciones de la IA). Estas operaciones son idempotentes: se pueden "
                "correr múltiples veces sin generar duplicados."
            )

            st.markdown("**1. Reindexar diferencias internas de cierre**")
            st.caption(
                "Busca cajeros que cobraron más efectivo del que depositaron y los agrega "
                "a la bandeja como pendientes tipo *diferencia interna*. "
                "Detecta tanto el campo `diferencia_interna` como diferencias calculadas "
                "de `efectivo - depósito`."
            )
            if st.button(
                "🔄 Reindexar diferencias internas del historial",
                key="backfill_internal",
                use_container_width=True,
            ):
                try:
                    res = cash_history.backfill_internal_diffs_from_history()
                    st.success(
                        f"✓ Reindexado: {res['scanned']} cajero(s) revisado(s) · "
                        f"{res['added']} pendiente(s) nuevo(s) agregado(s)."
                    )
                    cash_history.list_pending.clear()
                    import time
                    time.sleep(1)
                    st.rerun()
                except Exception as e:
                    st.error(f"Error: `{e}`")

            st.markdown("---")
            st.markdown("**2. Reparar matches sospechosos del historial**")
            st.caption(
                "Detecta y repara matches incorrectos donde la IA juntó depósitos "
                "con boletas que NO cuadran por monto (diferencia > Q 1.00) o donde "
                "la misma boleta se usó para dos depósitos. Los depósitos afectados "
                "se mueven a la bandeja de pendientes para que adjuntes la boleta correcta."
            )
            if st.button(
                "🔍 Reparar matches sospechosos del historial",
                key="repair_matches",
                use_container_width=True,
            ):
                try:
                    res = cash_history.repair_suspicious_matches_in_history()
                    if res["reports_repaired"] == 0:
                        st.info("✓ No se encontraron matches sospechosos. Todo está limpio.")
                    else:
                        msg = (
                            f"✓ Reparado: {res['reports_repaired']} reporte(s) · "
                            f"{res['matches_moved']} depósito(s) movidos a pendientes"
                        )
                        if res.get("fake_orphans_removed", 0) > 0:
                            msg += f" · {res['fake_orphans_removed']} boleta(s) ficticia(s) eliminada(s)"
                        st.success(msg + ".")
                        if res.get("suspicious_slips"):
                            with st.expander("Boletas marcadas como sospechosas", expanded=True):
                                st.caption(
                                    "Estas boletas se usaron incorrectamente en los reportes. "
                                    "Verifica si las boletas físicas existen realmente."
                                )
                                seen = set()
                                for s in res["suspicious_slips"]:
                                    sn = s["slip_number"]
                                    if sn in seen:
                                        continue
                                    seen.add(sn)
                                    st.markdown(
                                        f"&nbsp;&nbsp;• J No. `{sn}` — razón: {s['reason']}"
                                    )
                    cash_history.list_pending.clear()
                    cash_history.list_history.clear()
                    import time
                    time.sleep(2)
                    st.rerun()
                except Exception as e:
                    st.error(f"Error: `{e}`")

    if not pending:
        st.markdown(
            '<div class="ce-empty">'
            '<strong>✓ Bandeja vacía</strong>'
            'No hay pendientes — todos los cierres están cuadrados.'
            '</div>',
            unsafe_allow_html=True,
        )
        # Optionally show resolved history
        with st.expander("Ver historial de resoluciones", expanded=False):
            try:
                all_p = cash_history.list_pending(only_open=False)
                resolved_only = [p for p in all_p if p["status"] == "resolved"]
            except Exception:
                resolved_only = []
            if not resolved_only:
                st.caption("Aún no hay resoluciones registradas.")
            else:
                type_labels = {
                    "boleta_huerfana": "Boleta huérfana",
                    "deposito_sin_boleta": "Depósito sin boleta",
                    "diferencia_interna_cierre": "Diferencia interna",
                }
                for p in resolved_only[:30]:
                    ptype = type_labels.get(p["type"], p["type"])
                    st.markdown(
                        f"&nbsp;&nbsp;✓ **{ptype}** — {_fmt_q(p['amount'])} · "
                        f"de `{p['origin_report_id']}` → resuelto en "
                        f"`{p['resolved_in_report_id']}`"
                    )
        return

    # Separate by type
    boletas_huerfanas = [p for p in pending if p["type"] == "boleta_huerfana"]
    depositos_sin_boleta = [p for p in pending if p["type"] == "deposito_sin_boleta"]
    diferencias_internas = [p for p in pending if p["type"] == "diferencia_interna_cierre"]

    total_boletas = sum(p["amount"] for p in boletas_huerfanas)
    total_depositos = sum(p["amount"] for p in depositos_sin_boleta)
    total_internas = sum(p["amount"] for p in diferencias_internas)

    # KPI cards: 4 columns now
    st.markdown(
        f'<div class="ce-kpi-grid" style="grid-template-columns:repeat(4,1fr);">'
        f'<div class="ce-kpi">'
        f'<div class="ce-kpi-label">🧾 Boletas huérfanas</div>'
        f'<div class="ce-kpi-value">{_fmt_q(total_boletas)}</div>'
        f'<div class="ce-kpi-detail">{len(boletas_huerfanas)} sin depósito</div>'
        f'</div>'

        f'<div class="ce-kpi">'
        f'<div class="ce-kpi-label">📤 Depósitos sin boleta</div>'
        f'<div class="ce-kpi-value">{_fmt_q(total_depositos)}</div>'
        f'<div class="ce-kpi-detail">{len(depositos_sin_boleta)} sin comprobante</div>'
        f'</div>'

        f'<div class="ce-kpi">'
        f'<div class="ce-kpi-label">⚖️ Diferencias internas</div>'
        f'<div class="ce-kpi-value">{_fmt_q(total_internas)}</div>'
        f'<div class="ce-kpi-detail">{len(diferencias_internas)} faltante(s) de caja</div>'
        f'</div>'

        f'<div class="ce-kpi">'
        f'<div class="ce-kpi-label">Diferencia neta</div>'
        f'<div class="ce-kpi-value" style="color:{"#B91C1C" if (total_boletas != total_depositos or total_internas > 0) else "#1B7340"};">'
        f'{_fmt_q(abs(total_depositos - total_boletas) + total_internas)}</div>'
        f'<div class="ce-kpi-detail">'
        f'{"Pendiente por cuadrar" if (total_boletas != total_depositos or total_internas > 0) else "✓ Cuadran"}'
        f'</div></div>'
        f'</div>',
        unsafe_allow_html=True,
    )

    # Boletas huérfanas
    if boletas_huerfanas:
        st.markdown(
            "<div style='margin:18px 0 10px;font-size:11px;letter-spacing:2px;"
            "text-transform:uppercase;color:#0B0F19;font-weight:700;'>"
            f"🧾 Boletas huérfanas ({len(boletas_huerfanas)})</div>",
            unsafe_allow_html=True,
        )
        st.caption(
            "📎 Estas boletas existen pero no encontramos el PDF de cierre del POS que les corresponde. "
            "Sube el PDF del cierre original con el botón **Adjuntar PDF**."
        )
        for p in boletas_huerfanas:
            _render_pending_row(
                p, current_user,
                row_type="boleta_huerfana",
                all_open_same_type=boletas_huerfanas,
            )

    # Depósitos sin boleta
    if depositos_sin_boleta:
        st.markdown(
            "<div style='margin:18px 0 10px;font-size:11px;letter-spacing:2px;"
            "text-transform:uppercase;color:#0B0F19;font-weight:700;'>"
            f"📤 Depósitos sin boleta ({len(depositos_sin_boleta)})</div>",
            unsafe_allow_html=True,
        )
        st.caption(
            "📎 Estos depósitos se hicieron según el POS pero no hemos recibido la boleta del banco. "
            "Cuando llegue la boleta, súbela con el botón **Adjuntar boleta** para cerrar el pendiente."
        )
        for p in depositos_sin_boleta:
            _render_pending_row(
                p, current_user,
                row_type="deposito_sin_boleta",
                all_open_same_type=depositos_sin_boleta,
            )

    # Diferencias internas de cierre (faltante físico de caja)
    if diferencias_internas:
        st.markdown(
            "<div style='margin:18px 0 10px;font-size:11px;letter-spacing:2px;"
            "text-transform:uppercase;color:#0B0F19;font-weight:700;'>"
            f"⚖️ Diferencias internas de cierre ({len(diferencias_internas)})</div>",
            unsafe_allow_html=True,
        )
        st.caption(
            "🧮 Estos son cierres donde el efectivo cobrado fue mayor al depósito realizado — "
            "el cajero debe **reponer la diferencia**. Cuando reponga, marca como repuesto manualmente "
            "(si entregó el efectivo al Lic.) o adjunta la boleta si lo depositó al banco aparte."
        )
        for p in diferencias_internas:
            _render_pending_row(
                p, current_user,
                row_type="diferencia_interna_cierre",
                all_open_same_type=diferencias_internas,
            )


# ---------------------------------------------------------------------------
# Main render
# ---------------------------------------------------------------------------

def render(current_user: dict) -> None:
    st.markdown(_CSS, unsafe_allow_html=True)

    st.markdown(
        f"""
        <div class="ce-header">
          <div>
            <div class="sub">● Vintage Boutique · Inteligencia Ejecutiva</div>
            <div class="ttl">Centro Ejecutivo</div>
          </div>
          <div style="text-align:right;font-size:11px;color:#9CA3AF;">
            <div style="color:#F9FAFB;font-weight:500;">{current_user['name']}</div>
            <div>{current_user['email']}</div>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # Load history
    try:
        history = cash_history.list_history()
    except Exception as e:
        st.error(f"No se pudo cargar el historial: `{e}`")
        return

    # Tabs
    tab1, tab2, tab3, tab4 = st.tabs([
        "📊 Resumen",
        "📚 Historial",
        "⭐ Clientes VIP",
        "⏳ Pendientes",
    ])

    with tab1:
        _render_summary_tab(history)
    with tab2:
        _render_history_tab(history, current_user)
    with tab3:
        _render_vip_tab(history)
    with tab4:
        _render_pending_tab(current_user)
