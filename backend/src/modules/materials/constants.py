from enum import StrEnum


class SuppliedBy(StrEnum):
    COMPANY = "company"
    """Bought by us (KERP: ``kaefer``)."""
    CLIENT = "client"
    """Free-issue material from the client."""


class HeatStatus(StrEnum):
    EXPECTED = "expected"
    """Not received yet (client-supplied lines are planned before they arrive)."""
    AVAILABLE = "available"
    QUARANTINED = "quarantined"
    REJECTED = "rejected"


class ProductForm(StrEnum):
    PIPE = "pipe"
    FITTING = "fitting"
    FLANGE = "flange"
    PLATE = "plate"
    BOLTING = "bolting"
    GASKET = "gasket"
    VALVE = "valve"
    STRUCTURAL = "structural"
    CONSUMABLE = "consumable"
    COATING = "coating"
    INSULATION = "insulation"
    OTHER = "other"


class CertificateType(StrEnum):
    EN_10204_2_2 = "2.2"
    EN_10204_3_1 = "3.1"
    EN_10204_3_2 = "3.2"
    COC = "coc"
    OTHER = "other"


class VerificationStatus(StrEnum):
    PENDING = "pending_verification"
    VERIFIED = "verified"
    REJECTED = "rejected"


class ReceiptStatus(StrEnum):
    RECEIVED = "received"
    ACCEPTED = "accepted"
    REJECTED = "rejected"


RECEIPT_FLOW: dict[str, set[str]] = {
    ReceiptStatus.RECEIVED: {ReceiptStatus.ACCEPTED, ReceiptStatus.REJECTED},
    ReceiptStatus.ACCEPTED: {ReceiptStatus.RECEIVED},
    ReceiptStatus.REJECTED: {ReceiptStatus.RECEIVED},
}


class HoldStatus(StrEnum):
    OPEN = "open"
    RELEASED = "released"
    REJECTED = "rejected"
    """Disposition: scrap / return to supplier; the heat stays rejected."""


class PmiResult(StrEnum):
    ACCEPTED = "accepted"
    REJECTED = "rejected"


HEAT_ENTITY = "material_heat"
CERT_ENTITY = "material_certificate"
HOLD_ENTITY = "material_hold"
RECEIPT_ENTITY = "material_receipt"
