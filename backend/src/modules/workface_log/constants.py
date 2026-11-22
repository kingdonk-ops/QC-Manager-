from enum import StrEnum


class LogStatus(StrEnum):
    DRAFT = "draft"
    SUBMITTED = "submitted"
    SIGNED = "signed"


LOG_FLOW: dict[str, set[str]] = {
    "draft": {"submitted"},
    "submitted": {"draft", "signed"},
    "signed": set(),
}


class Shift(StrEnum):
    DAY = "day"
    NIGHT = "night"


class DelayCode(StrEnum):
    """Non-productive time with a cause (the reasons-for-non-completion list)."""

    WEATHER = "weather"
    PERMIT = "permit"
    ISOLATION = "isolation"
    MATERIALS = "materials"
    SCAFFOLD = "scaffold"
    EQUIPMENT = "equipment"
    CLIENT_HOLD = "client_hold"
    PRECEDING_TRADE = "preceding_trade"
    ENGINEERING = "engineering"
    SAFETY = "safety"
    LABOUR = "labour"
    OTHER = "other"


class OverheadCode(StrEnum):
    """Paid time that belongs to no work anchor."""

    TOOLBOX = "toolbox"
    TRAVEL = "travel"
    INDUCTION = "induction"
    TRAINING = "training"
    HOUSEKEEPING = "housekeeping"
    MOBILISATION = "mobilisation"
    STANDBY = "standby"
    OTHER = "other"


class EquipmentStatus(StrEnum):
    OPERATING = "operating"
    STANDBY = "standby"
    BREAKDOWN = "breakdown"
