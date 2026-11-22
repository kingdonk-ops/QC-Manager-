from enum import StrEnum


class FileCategory(StrEnum):
    DRAWING = "drawing"
    CONTRACT = "contract"
    SPECIFICATION = "specification"
    PHOTO = "photo"
    CORRESPONDENCE = "correspondence"
    REPORT = "report"
    MODEL = "model"
    OTHER = "other"


def guess_category(name: str, content_type: str) -> FileCategory:
    lower = name.lower()
    if content_type.startswith("image/"):
        return FileCategory.PHOTO
    if lower.endswith((".dwg", ".dxf")) or "-dr-" in lower or "drawing" in lower:
        return FileCategory.DRAWING
    if lower.endswith((".ifc", ".rvt", ".nwd")):
        return FileCategory.MODEL
    if "spec" in lower:
        return FileCategory.SPECIFICATION
    if "contract" in lower or "agreement" in lower:
        return FileCategory.CONTRACT
    if "report" in lower:
        return FileCategory.REPORT
    return FileCategory.OTHER
