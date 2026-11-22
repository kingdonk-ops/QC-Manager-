"""Where file bytes live. Local disk ships; register another backend for blob storage."""

import hashlib
import os
import secrets
from pathlib import Path
from typing import Protocol

import anyio
from fastapi import UploadFile

from ...infrastructure.config.settings import settings

CHUNK = 1024 * 1024


class FileTooLarge(Exception):
    pass


class Storage(Protocol):
    async def save(self, upload: UploadFile, max_bytes: int) -> tuple[str, int, str]: ...
    def path(self, key: str) -> Path: ...
    async def delete(self, key: str) -> None: ...


class LocalStorage:
    def __init__(self, root: str) -> None:
        self.root = Path(root).resolve()

    def path(self, key: str) -> Path:
        target = (self.root / key).resolve()
        if not str(target).startswith(str(self.root) + os.sep):
            raise ValueError("Bad storage key")
        return target

    async def save(self, upload: UploadFile, max_bytes: int) -> tuple[str, int, str]:
        key = f"{secrets.token_hex(2)}/{secrets.token_hex(16)}"
        target = self.path(key)
        await anyio.Path(target.parent).mkdir(parents=True, exist_ok=True)
        digest, size = hashlib.sha256(), 0
        try:
            async with await anyio.open_file(target, "wb") as out:
                while chunk := await upload.read(CHUNK):
                    size += len(chunk)
                    if size > max_bytes:
                        raise FileTooLarge()
                    digest.update(chunk)
                    await out.write(chunk)
        except BaseException:
            await anyio.Path(target).unlink(missing_ok=True)
            raise
        return key, size, digest.hexdigest()

    async def delete(self, key: str) -> None:
        await anyio.Path(self.path(key)).unlink(missing_ok=True)


def storage() -> Storage:
    return LocalStorage(settings.FILE_STORAGE_DIR)
