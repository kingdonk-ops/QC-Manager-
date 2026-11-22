from enum import StrEnum


class EquipmentType(StrEnum):
    PRESSURE_GAUGE = "pressure_gauge"
    DFT_METER = "dft_meter"
    THERMOMETER = "thermometer"
    TORQUE_WRENCH = "torque_wrench"
    TENSIONING_TOOL = "tensioning_tool"
    UT_THICKNESS_GAUGE = "ut_thickness_gauge"
    PMI_ANALYSER = "pmi_analyser"
    SURFACE_PROFILE_GAUGE = "surface_profile_gauge"
    HOLIDAY_DETECTOR = "holiday_detector"
    HYGROMETER = "hygrometer"
    WELDING_GAUGE = "welding_gauge"
    MULTIMETER = "multimeter"
    OTHER = "other"


class EquipmentClass(StrEnum):
    INSTRUMENT = "instrument"
    VEHICLE = "vehicle"
    PLANT = "plant"


class EquipmentStatus(StrEnum):
    """The stored status. ``due`` and ``overdue`` are worked out from the due date when read."""

    IN_SERVICE = "in_service"
    SENT_FOR_CALIBRATION = "sent_for_calibration"
    QUARANTINED = "quarantined"
    OUT_OF_SERVICE = "out_of_service"


class DisplayStatus(StrEnum):
    IN_SERVICE = "in_service"
    DUE = "due"
    OVERDUE = "overdue"
    SENT_FOR_CALIBRATION = "sent_for_calibration"
    QUARANTINED = "quarantined"
    OUT_OF_SERVICE = "out_of_service"


class CertificateResult(StrEnum):
    PASS = "pass"
    ADJUSTED = "adjusted"
    """Found out of tolerance, adjusted, then passed: readings since the last calibration need review."""


S = EquipmentStatus
FLOW: dict[str, set[str]] = {
    S.IN_SERVICE: {S.SENT_FOR_CALIBRATION, S.QUARANTINED, S.OUT_OF_SERVICE},
    S.SENT_FOR_CALIBRATION: {S.IN_SERVICE, S.QUARANTINED, S.OUT_OF_SERVICE},
    S.QUARANTINED: {S.IN_SERVICE, S.SENT_FOR_CALIBRATION, S.OUT_OF_SERVICE},
    S.OUT_OF_SERVICE: {S.IN_SERVICE, S.SENT_FOR_CALIBRATION},
}

ENTITY = "calibration_equipment"
