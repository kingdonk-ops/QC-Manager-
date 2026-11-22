from enum import StrEnum


class Role(StrEnum):
    GROUPING = "grouping"
    PHYSICAL = "physical"
    WORK_ANCHOR = "work_anchor"
    INSPECTION_ANCHOR = "inspection_anchor"
    PROGRESS_UNIT = "progress_unit"
    SCHEDULE_LINK = "schedule_link"


class CodeUniqueness(StrEnum):
    PER_PARENT = "per_parent"
    PER_LEVEL = "per_level"
    PER_PROJECT = "per_project"


class NodeStatus(StrEnum):
    ACTIVE = "active"
    RETIRED = "retired"


class IdentifierKind(StrEnum):
    BARCODE = "barcode"
    QR = "qr"
    NFC = "nfc"


class CollectionKind(StrEnum):
    JOB_PACK = "job_pack"
    SHUTDOWN_WINDOW = "shutdown_window"
    TEST_PACK = "test_pack"
    WORK_PLAN = "work_plan"
    OTHER = "other"
