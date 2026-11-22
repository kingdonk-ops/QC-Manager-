from enum import StrEnum


class Curve(StrEnum):
    """How a work package's budget is planned to be spent between its start and finish."""

    LINEAR = "linear"
    FRONT_LOADED = "front_loaded"
    BACK_LOADED = "back_loaded"
    S_CURVE = "s_curve"


class Basis(StrEnum):
    HOURS = "hours"
    COST = "cost"


class EacMethod(StrEnum):
    CPI = "cpi"
    """EAC = BAC / CPI: the efficiency so far continues."""
    BUDGET_RATE = "budget_rate"
    """EAC = AC + (BAC - EV): the remaining work goes to budget."""
    CPI_SPI = "cpi_spi"
    """EAC = AC + (BAC - EV) / (CPI x SPI): cost and schedule performance both weigh on the rest."""


class GroupBy(StrEnum):
    PACKAGE = "package"
    ACCOUNT = "account"
    DISCIPLINE = "discipline"
    PROJECT = "project"


class Interval(StrEnum):
    WEEK = "week"
    MONTH = "month"
