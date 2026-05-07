"""
flowworkshop · routers/docs.py
Dokumente-API (Plan v3.2 §7).
"""
from __future__ import annotations
import hashlib
import logging
import mimetypes
import os
import re
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, UploadFile, File, Form
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel
from sqlalchemy import desc, func
from sqlalchemy.orm import Session

from database import get_db
from models.docs import DocumentFolder, DocumentFile, DocumentVersion, DocumentDownloadLog
from models.registration import Registration
from routers.auth import require_session, require_moderator, require_admin

router = APIRouter(prefix="/api/docs", tags=["documents"])
log = logging.getLogger(__name__)

STORAGE_ROOT = Path(os.environ.get("DOC_STORAGE_ROOT", "/app/data/documents"))
TOTAL_QUOTA_BYTES = int(os.environ.get("DOC_TOTAL_QUOTA_BYTES", str(5 * 1024**3)))  # 5 GB
MAX_FILE_BYTES = int(os.environ.get("DOC_MAX_FILE_BYTES", str(50 * 1024**2)))       # 50 MB

ALLOWED_MIME_PREFIXES = (
    "application/pdf", "application/msword",
    "application/vnd.openxmlformats", "application/vnd.ms-excel",
    "application/vnd.ms-powerpoint", "application/zip",
    "image/", "text/", "application/json", "application/xml",
)


# ─── Schemas ────────────────────────────────────────────────────────────────

class FolderOut(BaseModel):
    id: str
    parent_id: str | None = None
    name: str
    slug: str
    description: str | None = None
    visibility: str
    upload_policy: str
    is_shared_pool: bool
    icon: str | None = None
    sort_order: int = 0
    file_count: int = 0
    size_bytes: int = 0


class FileOut(BaseModel):
    id: str
    folder_id: str
    name: str
    description: str | None = None
    tags: list[str] | None = None
    mime_type: str | None = None
    size_bytes: int
    current_version_no: int
    uploaded_at: datetime | None = None
    uploader_name: str | None = None
    uploader_organization: str | None = None
    uploader_bundesland: str | None = None
    download_count: int = 0
    can_delete: bool = False


class VersionOut(BaseModel):
    version_no: int
    sha256: str
    size_bytes: int
    uploaded_at: datetime | None = None
    uploader_name: str | None = None
    change_note: str | None = None


# ─── Helpers ────────────────────────────────────────────────────────────────

def _check_role_can_read(folder: DocumentFolder, request: Request, db: Session) -> tuple[Optional[Registration], str]:
    """Gibt (user, role) zurück. Wirft 403 falls Lese-Recht fehlt."""
    if folder.visibility == "public_read":
        try:
            sess = require_session(request)
        except HTTPException:
            return None, ""
        user = db.query(Registration).filter(Registration.id == sess["user_id"]).first()
        return user, sess.get("role", "")
    sess = require_session(request)
    role = sess.get("role", "")
    user = db.query(Registration).filter(Registration.id == sess["user_id"]).first()
    if folder.visibility == "moderators_only" and role not in ("moderator", "admin"):
        raise HTTPException(403, "Nur für Moderatoren.")
    return user, role


def _check_role_can_upload(folder: DocumentFolder, request: Request, db: Session) -> Registration:
    sess = require_session(request)
    user = db.query(Registration).filter(Registration.id == sess["user_id"]).first()
    if not user:
        raise HTTPException(401)
    if (user.status or "active") != "active":
        raise HTTPException(403, "Konto nicht aktiv.")
    role = sess.get("role", "")
    if folder.upload_policy == "none":
        raise HTTPException(403, "Uploads gesperrt.")
    if folder.upload_policy == "moderators" and role not in ("moderator", "admin"):
        raise HTTPException(403, "Nur Moderatoren dürfen hier hochladen.")
    return user


def _validate_mime(mime: str) -> bool:
    if not mime:
        return False
    return any(mime.startswith(p) for p in ALLOWED_MIME_PREFIXES)


def _hash_ip(request: Request) -> str | None:
    if not request.client:
        return None
    return hashlib.sha256((request.client.host + ":auditworkshop").encode()).hexdigest()[:32]


def _disk_used() -> int:
    if not STORAGE_ROOT.exists():
        return 0
    total = 0
    for p in STORAGE_ROOT.rglob("*"):
        if p.is_file():
            try: total += p.stat().st_size
            except Exception: pass
    return total


# ─── Folders ─────────────────────────────────────────────────────────────────

@router.get("/folders", response_model=list[FolderOut])
def list_folders(request: Request, db: Session = Depends(get_db)):
    folders = db.query(DocumentFolder).order_by(DocumentFolder.sort_order, DocumentFolder.name).all()
    # Sichtbarkeit filtern
    sess = None
    try:
        sess = require_session(request)
    except HTTPException:
        pass
    role = sess.get("role", "") if sess else ""

    out: list[FolderOut] = []
    for f in folders:
        if f.visibility == "moderators_only" and role not in ("moderator", "admin"):
            continue
        if f.visibility == "members_read" and not sess:
            continue
        # Stats
        stats = (
            db.query(func.count(DocumentFile.id), func.coalesce(func.sum(DocumentFile.size_bytes), 0))
            .filter(DocumentFile.folder_id == f.id, DocumentFile.deleted_at.is_(None))
            .one()
        )
        out.append(FolderOut(
            id=f.id, parent_id=f.parent_id, name=f.name, slug=f.slug,
            description=f.description, visibility=f.visibility,
            upload_policy=f.upload_policy, is_shared_pool=f.is_shared_pool,
            icon=f.icon, sort_order=f.sort_order or 0,
            file_count=int(stats[0] or 0),
            size_bytes=int(stats[1] or 0),
        ))
    return out


# ─── Files ───────────────────────────────────────────────────────────────────

@router.get("/folders/{folder_id}/files", response_model=list[FileOut])
def list_files(
    folder_id: str, request: Request,
    bundesland: str | None = Query(None),
    tag: str | None = Query(None),
    mime: str | None = Query(None),
    q: str | None = Query(None),
    db: Session = Depends(get_db),
):
    folder = db.query(DocumentFolder).filter(DocumentFolder.id == folder_id).first()
    if not folder:
        raise HTTPException(404, "Ordner nicht gefunden.")
    user, role = _check_role_can_read(folder, request, db)

    qry = db.query(DocumentFile).filter(
        DocumentFile.folder_id == folder_id,
        DocumentFile.deleted_at.is_(None),
    )
    if bundesland:
        qry = qry.filter(DocumentFile.uploader_bundesland == bundesland)
    if mime:
        qry = qry.filter(DocumentFile.mime_type.ilike(f"{mime}%"))
    if q:
        like = f"%{q}%"
        qry = qry.filter(
            (DocumentFile.name.ilike(like)) | (DocumentFile.description.ilike(like))
        )
    rows = qry.order_by(desc(DocumentFile.uploaded_at)).all()
    if tag:
        rows = [r for r in rows if r.tags and tag in (r.tags or [])]

    return [
        FileOut(
            id=r.id, folder_id=r.folder_id, name=r.name, description=r.description,
            tags=r.tags or [], mime_type=r.mime_type, size_bytes=r.size_bytes,
            current_version_no=r.current_version_no,
            uploaded_at=r.uploaded_at, uploader_name=r.uploader_name,
            uploader_organization=r.uploader_organization,
            uploader_bundesland=r.uploader_bundesland,
            download_count=r.download_count,
            can_delete=(user is not None and (r.uploader_id == user.id or role in ("moderator", "admin"))),
        )
        for r in rows
    ]


@router.post("/folders/{folder_id}/files", response_model=FileOut, status_code=201)
async def upload_file(
    folder_id: str,
    request: Request,
    file: UploadFile = File(...),
    description: str = Form(""),
    tags: str = Form(""),
    db: Session = Depends(get_db),
):
    folder = db.query(DocumentFolder).filter(DocumentFolder.id == folder_id).first()
    if not folder:
        raise HTTPException(404, "Ordner nicht gefunden.")
    user = _check_role_can_upload(folder, request, db)
    role = "admin" if user.role == "admin" else ("moderator" if user.role == "moderator" else "attendee")

    content = await file.read()
    size = len(content)
    if size == 0:
        raise HTTPException(422, "Datei ist leer.")
    if size > MAX_FILE_BYTES:
        raise HTTPException(413, f"Datei zu groß (max {MAX_FILE_BYTES // 1024 // 1024} MB).")

    mime = file.content_type or mimetypes.guess_type(file.filename or "")[0] or "application/octet-stream"
    if not _validate_mime(mime):
        raise HTTPException(415, f"Dateityp '{mime}' nicht erlaubt.")

    # Quota — User
    if (user.used_bytes or 0) + size > (user.quota_bytes or 0):
        raise HTTPException(413, "User-Quota überschritten.")

    # Quota — total
    total_used = _disk_used()
    if total_used + size > TOTAL_QUOTA_BYTES:
        raise HTTPException(507, "Speicherplatz erschöpft. Bitte Admin kontaktieren.")

    # Hash + Storage-Pfad
    sha = hashlib.sha256(content).hexdigest()
    file_id = str(uuid.uuid4())
    storage_dir = STORAGE_ROOT / file_id
    storage_dir.mkdir(parents=True, exist_ok=True)
    version_path = storage_dir / "v1.bin"
    version_path.write_bytes(content)

    name = (file.filename or "unbekannt.bin")[:200]
    tag_list = [t.strip() for t in tags.split(",") if t.strip()][:10] if tags else None

    df = DocumentFile(
        id=file_id, folder_id=folder_id, name=name,
        description=(description or "").strip()[:2000] or None,
        tags=tag_list, mime_type=mime, size_bytes=size, current_version_no=1,
        storage_dir=str(storage_dir),
        uploader_id=user.id,
        uploader_name=f"{user.first_name} {user.last_name}",
        uploader_organization=user.organization,
        uploader_bundesland=user.bundesland,
    )
    db.add(df)
    db.add(DocumentVersion(
        file_id=file_id, version_no=1, storage_key=str(version_path),
        sha256=sha, size_bytes=size, mime_type=mime,
        uploader_id=user.id, uploader_name=df.uploader_name,
    ))
    user.used_bytes = (user.used_bytes or 0) + size
    db.commit()
    db.refresh(df)
    return FileOut(
        id=df.id, folder_id=df.folder_id, name=df.name, description=df.description,
        tags=df.tags or [], mime_type=df.mime_type, size_bytes=df.size_bytes,
        current_version_no=df.current_version_no,
        uploaded_at=df.uploaded_at, uploader_name=df.uploader_name,
        uploader_organization=df.uploader_organization,
        uploader_bundesland=df.uploader_bundesland,
        download_count=0, can_delete=True,
    )


@router.get("/files/{file_id}/download")
def download_file(file_id: str, request: Request, db: Session = Depends(get_db)):
    df = db.query(DocumentFile).filter(DocumentFile.id == file_id, DocumentFile.deleted_at.is_(None)).first()
    if not df:
        raise HTTPException(404, "Datei nicht gefunden.")
    folder = db.query(DocumentFolder).filter(DocumentFolder.id == df.folder_id).first()
    user, _ = _check_role_can_read(folder, request, db)

    version = (
        db.query(DocumentVersion)
        .filter(DocumentVersion.file_id == file_id, DocumentVersion.version_no == df.current_version_no)
        .first()
    )
    if not version or not Path(version.storage_key).exists():
        raise HTTPException(404, "Datei-Inhalt fehlt.")

    df.download_count = (df.download_count or 0) + 1
    db.add(DocumentDownloadLog(
        file_id=file_id, version_no=version.version_no,
        user_id=user.id if user else None, ip_hash=_hash_ip(request),
    ))
    db.commit()
    return FileResponse(
        path=version.storage_key,
        media_type=df.mime_type or "application/octet-stream",
        filename=df.name,
    )


@router.delete("/files/{file_id}")
def delete_file(file_id: str, request: Request, db: Session = Depends(get_db)):
    sess = require_session(request)
    user = db.query(Registration).filter(Registration.id == sess["user_id"]).first()
    df = db.query(DocumentFile).filter(DocumentFile.id == file_id, DocumentFile.deleted_at.is_(None)).first()
    if not df:
        raise HTTPException(404)
    role = sess.get("role", "")
    is_owner = user and df.uploader_id == user.id
    is_mod = role in ("moderator", "admin")
    if not (is_owner or is_mod):
        raise HTTPException(403, "Nicht erlaubt.")
    df.deleted_at = datetime.utcnow()
    if is_owner and user:
        user.used_bytes = max(0, (user.used_bytes or 0) - (df.size_bytes or 0))
    db.commit()
    return {"status": "deleted"}


@router.get("/files/{file_id}/versions", response_model=list[VersionOut])
def list_versions(file_id: str, request: Request, db: Session = Depends(get_db)):
    require_session(request)
    versions = (
        db.query(DocumentVersion)
        .filter(DocumentVersion.file_id == file_id)
        .order_by(desc(DocumentVersion.version_no)).all()
    )
    return [
        VersionOut(
            version_no=v.version_no, sha256=v.sha256,
            size_bytes=v.size_bytes, uploaded_at=v.uploaded_at,
            uploader_name=v.uploader_name, change_note=v.change_note,
        )
        for v in versions
    ]


# ─── Admin / Stats ──────────────────────────────────────────────────────────

@router.get("/system/usage")
def system_usage(request: Request):
    require_admin(request)
    used = _disk_used()
    return {
        "used_bytes": used,
        "total_quota_bytes": TOTAL_QUOTA_BYTES,
        "max_file_bytes": MAX_FILE_BYTES,
        "warn_at_pct": 80,
        "block_at_pct": 95,
    }


@router.post("/admin/folders", status_code=201)
def create_folder(
    name: str = Form(...),
    slug: str = Form(...),
    description: str = Form(""),
    visibility: str = Form("members_read"),
    upload_policy: str = Form("moderators"),
    icon: str = Form(""),
    request: Request = None,  # type: ignore
    db: Session = Depends(get_db),
):
    require_moderator(request)
    if visibility not in ("public_read", "members_read", "moderators_only"):
        raise HTTPException(422, "Ungültige visibility.")
    if upload_policy not in ("members", "moderators", "none"):
        raise HTTPException(422, "Ungültige upload_policy.")
    f = DocumentFolder(
        name=name.strip(), slug=re.sub(r"[^a-z0-9-]+", "-", slug.lower()).strip("-"),
        description=description.strip() or None,
        visibility=visibility, upload_policy=upload_policy,
        icon=icon or None,
    )
    db.add(f)
    db.commit()
    db.refresh(f)
    return {"id": f.id, "slug": f.slug}
