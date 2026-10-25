from __future__ import annotations

import re

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse

from ..config import Settings
from ..deps import settings_dep

router = APIRouter()

_SAFE_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")


@router.get("/files/{name}")
def get_file(name: str, settings: Settings = Depends(settings_dep)) -> FileResponse:
    if not _SAFE_NAME.fullmatch(name):
        raise HTTPException(404, "file not found")
    root = settings.files_dir.resolve()
    path = (root / name).resolve()
    if path.parent != root or not path.is_file():
        raise HTTPException(404, "file not found")
    return FileResponse(path, media_type="application/pdf" if name.endswith(".pdf") else None, filename=name)
