from enum import StrEnum


class ContactType(StrEnum):
    CLIENT = "client"
    SUBCONTRACTOR = "subcontractor"
    SUPPLIER = "supplier"
    CONSULTANT = "consultant"
    ARCHITECT = "architect"
    ENGINEER = "engineer"
    AUTHORITY = "authority"
    INTERNAL = "internal"
    OTHER = "other"
