from pydantic_settings import BaseSettings

from ...infrastructure.config.base import config


class FileSettings(BaseSettings):
    FILE_STORAGE_DIR: str = config("FILE_STORAGE_DIR", default="./data/files")
    FILE_MAX_UPLOAD_MB: int = config("FILE_MAX_UPLOAD_MB", default=100, cast=int)
