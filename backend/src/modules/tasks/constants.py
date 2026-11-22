from enum import StrEnum


class TaskType(StrEnum):
    GENERAL = "general"
    DESIGN = "design"
    PROCUREMENT = "procurement"
    CONSTRUCTION = "construction"
    COMMISSIONING = "commissioning"


class TaskStatus(StrEnum):
    TODO = "todo"
    IN_PROGRESS = "in_progress"
    REVIEW = "review"
    DONE = "done"


class Priority(StrEnum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


TYPE_FIELDS: dict[str, list[str]] = {
    TaskType.GENERAL: [],
    TaskType.DESIGN: ["discipline", "drawing_ref"],
    TaskType.PROCUREMENT: ["supplier", "po_ref", "required_on_site"],
    TaskType.CONSTRUCTION: ["location", "trade"],
    TaskType.COMMISSIONING: ["system", "test_ref"],
}
"""The extra fields each type carries in ``type_fields``."""
