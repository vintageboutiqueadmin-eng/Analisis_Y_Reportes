"""
Google Drive storage for cash closing reports.

Folder structure inside the configured root Drive folder:
    {root}/
        cierres-de-caja/
            2026-05-12/
                pdfs/
                    Reporte_xxx.pdf
                neonet/
                    foto_xxx.jpg
                boletas/
                    foto_xxx.jpg
                analisis/
                    reporte_consolidado_2026-05-12.json
                    reporte_consolidado_2026-05-12.pdf

The service account from secrets.toml [gcp_service_account] is reused.
The root folder ID is set in secrets.toml [drive] root_folder_id.
"""

from __future__ import annotations

import io
import datetime as dt
from typing import Optional
from zoneinfo import ZoneInfo

import streamlit as st


GT_TZ = ZoneInfo("America/Guatemala")


@st.cache_resource
def get_drive_service():
    """Authenticated Google Drive client (service account)."""
    from googleapiclient.discovery import build
    from google.oauth2.service_account import Credentials

    scopes = [
        "https://www.googleapis.com/auth/drive",
        "https://www.googleapis.com/auth/drive.file",
    ]
    info = dict(st.secrets["gcp_service_account"])
    creds = Credentials.from_service_account_info(info, scopes=scopes)
    return build("drive", "v3", credentials=creds, cache_discovery=False)


def _root_folder_id() -> str:
    try:
        raw = st.secrets["drive"]["root_folder_id"]
    except Exception:
        raise RuntimeError(
            "Falta `[drive] root_folder_id` en los secrets. "
            "El admin debe crear una carpeta de Google Drive y compartirla con la "
            "cuenta de servicio, luego copiar el ID de la URL aquí."
        )
    # Be lenient: accept full Drive URLs and extract the ID
    s = str(raw).strip()
    if "/folders/" in s:
        s = s.split("/folders/", 1)[1]
    if "?" in s:
        s = s.split("?", 1)[0]
    if "/" in s:
        s = s.split("/", 1)[0]
    return s.strip()


# ---------------------------------------------------------------------------
# Folder management
# ---------------------------------------------------------------------------

def _find_child_folder(service, parent_id: str, name: str) -> Optional[str]:
    """Return folder ID if a folder with the given name exists under parent_id."""
    safe_name = name.replace("'", "\\'")
    q = (
        f"'{parent_id}' in parents and "
        f"mimeType='application/vnd.google-apps.folder' and "
        f"name='{safe_name}' and trashed=false"
    )
    resp = service.files().list(
        q=q, fields="files(id, name)", pageSize=10,
        supportsAllDrives=True, includeItemsFromAllDrives=True,
    ).execute()
    files = resp.get("files", [])
    return files[0]["id"] if files else None


def _create_folder(service, parent_id: str, name: str) -> str:
    """Create a folder under parent_id and return its ID."""
    metadata = {
        "name": name,
        "mimeType": "application/vnd.google-apps.folder",
        "parents": [parent_id],
    }
    folder = service.files().create(
        body=metadata, fields="id", supportsAllDrives=True,
    ).execute()
    return folder["id"]


def _ensure_folder(service, parent_id: str, name: str) -> str:
    """Get or create a child folder by name."""
    existing = _find_child_folder(service, parent_id, name)
    if existing:
        return existing
    return _create_folder(service, parent_id, name)


def ensure_day_structure(date: dt.date) -> dict:
    """
    Ensure the folder structure exists for a given date.
    Returns dict with folder IDs: {root, day, pdfs, neonet, boletas, analisis}
    """
    service = get_drive_service()
    root = _root_folder_id()

    cierres = _ensure_folder(service, root, "cierres-de-caja")
    day = _ensure_folder(service, cierres, date.isoformat())
    pdfs = _ensure_folder(service, day, "pdfs")
    neonet = _ensure_folder(service, day, "neonet")
    boletas = _ensure_folder(service, day, "boletas")
    analisis = _ensure_folder(service, day, "analisis")

    return {
        "root": root,
        "cierres": cierres,
        "day": day,
        "pdfs": pdfs,
        "neonet": neonet,
        "boletas": boletas,
        "analisis": analisis,
    }


# ---------------------------------------------------------------------------
# Upload / list / delete
# ---------------------------------------------------------------------------

def upload_file(folder_id: str, filename: str, file_bytes: bytes, mime_type: str) -> dict:
    """Upload bytes to a Drive folder. Returns the created file metadata."""
    from googleapiclient.http import MediaIoBaseUpload

    media = MediaIoBaseUpload(
        io.BytesIO(file_bytes), mimetype=mime_type, resumable=False,
    )
    metadata = {"name": filename, "parents": [folder_id]}
    f = get_drive_service().files().create(
        body=metadata,
        media_body=media,
        fields="id, name, mimeType, size, createdTime, modifiedTime, webViewLink",
        supportsAllDrives=True,
    ).execute()
    return f


def list_folder(folder_id: str) -> list[dict]:
    """List files in a folder, ordered by modifiedTime desc."""
    q = f"'{folder_id}' in parents and trashed=false"
    resp = get_drive_service().files().list(
        q=q,
        fields="files(id, name, mimeType, size, createdTime, modifiedTime, webViewLink)",
        orderBy="modifiedTime desc",
        pageSize=200,
        supportsAllDrives=True,
        includeItemsFromAllDrives=True,
    ).execute()
    return resp.get("files", [])


def delete_file(file_id: str) -> None:
    get_drive_service().files().delete(
        fileId=file_id, supportsAllDrives=True,
    ).execute()


def download_file_bytes(file_id: str) -> bytes:
    """Download a file from Drive and return its raw bytes."""
    from googleapiclient.http import MediaIoBaseDownload

    request = get_drive_service().files().get_media(
        fileId=file_id, supportsAllDrives=True,
    )
    buf = io.BytesIO()
    downloader = MediaIoBaseDownload(buf, request)
    done = False
    while not done:
        _status, done = downloader.next_chunk()
    return buf.getvalue()


# ---------------------------------------------------------------------------
# Historial: list available dates
# ---------------------------------------------------------------------------

def list_processed_dates() -> list[str]:
    """List date folders that already exist under cierres-de-caja."""
    service = get_drive_service()
    cierres_id = _find_child_folder(service, _root_folder_id(), "cierres-de-caja")
    if not cierres_id:
        return []
    q = (
        f"'{cierres_id}' in parents and "
        f"mimeType='application/vnd.google-apps.folder' and trashed=false"
    )
    resp = service.files().list(
        q=q, fields="files(id, name)", orderBy="name desc",
        pageSize=200, supportsAllDrives=True, includeItemsFromAllDrives=True,
    ).execute()
    return [f["name"] for f in resp.get("files", [])]


def has_analysis_for_date(date: dt.date) -> bool:
    """Quick check if the analysis folder for a date has any files."""
    try:
        folders = ensure_day_structure(date)
        files = list_folder(folders["analisis"])
        return len(files) > 0
    except Exception:
        return False
