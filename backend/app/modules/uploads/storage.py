from pathlib import Path
from uuid import uuid4

from fastapi import UploadFile

from app.core.config import settings


class LocalStorageService:
    def __init__(self, base_dir: Path | None = None) -> None:
        self.base_dir = base_dir or settings.uploads_dir_path

    async def save(self, file: UploadFile, folder: str) -> str:
        target_dir = self.base_dir / folder
        target_dir.mkdir(parents=True, exist_ok=True)

        suffix = Path(file.filename or "").suffix.lower()
        filename = f"{uuid4().hex}{suffix}"
        target_path = target_dir / filename

        content = await file.read()
        target_path.write_bytes(content)

        return str(target_path.as_posix())
