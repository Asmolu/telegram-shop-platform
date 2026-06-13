from pathlib import Path
from uuid import uuid4

from fastapi import UploadFile

from app.core.config import settings


class LocalStorageService:
    def __init__(self, base_dir: Path | None = None) -> None:
        self.base_dir = base_dir or settings.uploads_dir_path

    async def save(self, file: UploadFile, folder: str) -> str:
        content = await file.read()
        return self.save_bytes(content, folder=folder, suffix=Path(file.filename or "").suffix)

    def save_bytes(self, content: bytes, *, folder: str, suffix: str) -> str:
        target_dir = self._safe_target_dir(folder)
        filename = f"{uuid4().hex}{suffix.lower()}"
        target_path = target_dir / filename
        target_path.write_bytes(content)

        return target_path.relative_to(self.base_dir).as_posix()

    def delete(self, relative_path: str) -> None:
        target_path = (self.base_dir / relative_path).resolve()
        base_path = self.base_dir.resolve()
        if not target_path.is_relative_to(base_path):
            return
        if target_path.is_file():
            target_path.unlink()

    def exists(self, relative_path: str) -> bool:
        target_path = (self.base_dir / relative_path).resolve()
        base_path = self.base_dir.resolve()
        return target_path.is_relative_to(base_path) and target_path.is_file()

    def _safe_target_dir(self, folder: str) -> Path:
        if folder not in settings.upload_subdirs:
            msg = "Unsupported upload folder"
            raise ValueError(msg)

        target_dir = (self.base_dir / folder).resolve()
        base_path = self.base_dir.resolve()
        if not target_dir.is_relative_to(base_path):
            msg = "Upload folder escapes base directory"
            raise ValueError(msg)

        target_dir.mkdir(parents=True, exist_ok=True)
        return target_dir


def ensure_upload_directories() -> None:
    settings.uploads_dir_path.mkdir(parents=True, exist_ok=True)
    for subdir in settings.upload_subdirs:
        (settings.uploads_dir_path / subdir).mkdir(parents=True, exist_ok=True)
