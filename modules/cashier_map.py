"""
Cashier → Store mapping.

Reads the `cashier_store_map` tab from the main Google Sheet and provides:
  - get_cashier_map() — returns the raw mapping
  - resolve_cashier_store(name) — given a cashier name (possibly messy like
    "CAJA DAISY (no usado)"), finds the best match by substring and returns
    (store_id, store_name, matched_name) or (None, None, None) if not found.
  - build_prompt_block() — produces a text block to inject into the Claude
    prompt with the full map.

The sheet tab has 3 columns:
  cashier_name | store_id | store_name

Examples:
  Daisy       | 7ma | 7ma Avenida
  Jonathan    | 7ma | 7ma Avenida
  Marisol     | 6ta | 6ta Avenida
  Alejandra   | 6ta | 6ta Avenida
"""

from __future__ import annotations

import streamlit as st

from . import sheets


CASHIER_MAP_TAB = "cashier_store_map"
CASHIER_MAP_HEADERS = ["cashier_name", "store_id", "store_name"]


def _ensure_cashier_map_tab():
    """Ensure the cashier_store_map tab exists with correct headers."""
    ss = sheets.get_spreadsheet()
    titles = {ws.title for ws in ss.worksheets()}
    if CASHIER_MAP_TAB not in titles:
        ss.add_worksheet(title=CASHIER_MAP_TAB, rows=100, cols=len(CASHIER_MAP_HEADERS))
    ws = ss.worksheet(CASHIER_MAP_TAB)
    first_row = ws.row_values(1)
    if [h.strip().lower() for h in first_row] != [h.lower() for h in CASHIER_MAP_HEADERS]:
        ws.update("A1", [CASHIER_MAP_HEADERS])
    return ws


@st.cache_data(ttl=300, show_spinner=False)
def get_cashier_map() -> list[dict]:
    """
    Return all cashier mappings as a list of dicts:
      [{"cashier_name": "Daisy", "store_id": "7ma", "store_name": "7ma Avenida"}, ...]
    """
    try:
        _ensure_cashier_map_tab()
        ws = sheets.get_spreadsheet().worksheet(CASHIER_MAP_TAB)
        rows = ws.get_all_records()
    except Exception:
        return []

    out = []
    for r in rows:
        name = str(r.get("cashier_name", "")).strip()
        sid = str(r.get("store_id", "")).strip()
        sname = str(r.get("store_name", "")).strip()
        if name and sid:
            out.append({
                "cashier_name": name,
                "store_id": sid,
                "store_name": sname or sid,
            })
    return out


def resolve_cashier_store(raw_cashier_name: str) -> tuple[str | None, str | None, str | None]:
    """
    Given a raw cashier name from a PDF (can be messy like "CAJA DAISY (no usado)"),
    find the best matching cashier in the map by substring (case-insensitive).

    Returns (store_id, store_name, matched_cashier_name) or (None, None, None) if no match.

    Priority:
      1. Exact match (case-insensitive)
      2. Map entry's cashier_name appears as substring in raw_cashier_name
      3. raw_cashier_name appears as substring in map entry's cashier_name
    """
    if not raw_cashier_name:
        return (None, None, None)

    raw_upper = raw_cashier_name.upper().strip()
    cmap = get_cashier_map()

    # Pass 1: exact match
    for entry in cmap:
        if entry["cashier_name"].upper() == raw_upper:
            return (entry["store_id"], entry["store_name"], entry["cashier_name"])

    # Pass 2: map entry appears in raw name (most common case for "CAJA DAISY")
    # We prefer longer cashier_name matches (more specific wins)
    candidates = []
    for entry in cmap:
        entry_upper = entry["cashier_name"].upper()
        if entry_upper in raw_upper:
            candidates.append((len(entry_upper), entry))
    if candidates:
        candidates.sort(key=lambda x: x[0], reverse=True)
        entry = candidates[0][1]
        return (entry["store_id"], entry["store_name"], entry["cashier_name"])

    # Pass 3: raw name appears in map entry (uncommon but useful)
    for entry in cmap:
        entry_upper = entry["cashier_name"].upper()
        if raw_upper in entry_upper:
            return (entry["store_id"], entry["store_name"], entry["cashier_name"])

    return (None, None, None)


def build_prompt_block() -> str:
    """
    Build the text block to inject into the Claude analysis prompt with the
    complete cashier → store mapping. The model uses this as authoritative
    truth when a PDF doesn't make the store clear.
    """
    cmap = get_cashier_map()
    if not cmap:
        return ""

    # Group by store for readability
    by_store: dict[str, list[str]] = {}
    for entry in cmap:
        sname = entry["store_name"] or entry["store_id"]
        by_store.setdefault(sname, []).append(entry["cashier_name"])

    lines = ["=== MAPA AUTORITATIVO DE CAJEROS → TIENDA ==="]
    lines.append(
        "Este mapa indica DEFINITIVAMENTE en qué tienda trabaja cada cajero. "
        "Si el PDF de cierre no menciona la tienda explícitamente (o la menciona "
        "ambiguamente como 'CAJA DAISY (no usado)'), USA ESTE MAPA como fuente "
        "de verdad. Busca el nombre del cajero del PDF como substring contra los "
        "nombres aquí (case-insensitive). NUNCA inventes ni adivines la tienda — "
        "si no encuentras el cajero aquí, marca el `store` como 'DESCONOCIDA' en "
        "el cashier_breakdown y agrega un finding tipo `warn` indicando 'Cajero "
        "no encontrado en el mapa: [nombre]'."
    )
    lines.append("")

    for sname, cashiers in sorted(by_store.items()):
        lines.append(f"  • Tienda **{sname}**:")
        for name in sorted(cashiers, key=str.lower):
            lines.append(f"    - {name}")

    lines.append("")
    lines.append(
        "IMPORTANTE: Este mapa también afecta `card_reconciliation` y el "
        "agrupamiento de VISANET/CREDOMATIC por tienda. Si un POS dice 'Daisy' "
        "(7ma según el mapa) y tiene VISANET Q 205, ese monto pertenece a la "
        "TERMINAL DE LA 7MA, no a la 6ta — aunque otros cajeros del mismo análisis "
        "sean 6ta. Distribuye correctamente los totales de tarjeta por tienda usando "
        "este mapa."
    )
    return "\n".join(lines) + "\n"


def add_or_update_mapping(cashier_name: str, store_id: str, store_name: str = "") -> bool:
    """Add a new cashier or update existing one."""
    if not cashier_name or not store_id:
        return False
    ws = _ensure_cashier_map_tab()
    all_values = ws.get_all_values()

    # Look for existing row
    for i, row in enumerate(all_values[1:], start=2):
        if row and row[0].strip().lower() == cashier_name.strip().lower():
            ws.update_cell(i, 2, store_id)
            ws.update_cell(i, 3, store_name or store_id)
            get_cashier_map.clear()
            return True

    # Append new
    ws.append_row(
        [cashier_name.strip(), store_id.strip(), store_name.strip() or store_id.strip()],
        value_input_option="USER_ENTERED",
    )
    get_cashier_map.clear()
    return True


def delete_mapping(cashier_name: str) -> bool:
    """Delete a cashier mapping by name."""
    ws = _ensure_cashier_map_tab()
    all_values = ws.get_all_values()
    for i, row in enumerate(all_values[1:], start=2):
        if row and row[0].strip().lower() == cashier_name.strip().lower():
            ws.delete_rows(i)
            get_cashier_map.clear()
            return True
    return False
