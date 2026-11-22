"""Progress claims. Work lines earn only on verified completion (``schedule.progress``, KERP TD-563).

Arithmetic, per line: ``to_date_value = to_date_qty × rate``, ``previous_value = previous_qty × rate``,
``this_value = to_date_value − previous_value``. Per claim::

    gross to date      = works to date + variations to date
    retention to date  = min(gross to date × retention %, retention cap)
    net to date        = gross to date − retention to date
    previous payments  = what earlier claims were certified for (or claimed, while not yet certified)
    this claim         = net to date − previous payments

``previous_qty`` comes from the latest earlier claim that isn't a draft. Money is a mirror: nothing here posts to
a ledger; ``claims.claim.certified`` is published for an integration to pick up.
"""

from collections.abc import Iterable
from datetime import UTC, date, datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ...infrastructure.modules import publish
from ...infrastructure.modules.state import is_enabled
from ...infrastructure.pdf import Document, render_pdf
from ...infrastructure.records import assert_transition, next_reference, record_transition
from ..asset_tree import service as tree
from ..asset_tree.models import AssetNode
from ..change_of_scope.models import ChangeCard
from ..change_orders.models import ChangeOrder, ChangeOrderLine
from ..common.exceptions import ResourceExistsError, ResourceNotFoundError, ValidationError
from ..projects.models import Project
from ..schedule import progress
from .models import Claim, ClaimLine, RateItem
from .schemas import ClaimStatus

ENTITY = "progress_claim"
CENT = Decimal("0.01")
ZERO = Decimal(0)
FLOW: dict[str, set[str]] = {
    ClaimStatus.DRAFT: {ClaimStatus.SUBMITTED},
    ClaimStatus.SUBMITTED: {ClaimStatus.DRAFT, ClaimStatus.CERTIFIED},
    ClaimStatus.CERTIFIED: {ClaimStatus.PAID},
    ClaimStatus.PAID: set(),
}
"""A submitted claim can be returned to draft until it is certified."""


class ClaimNotFound(ResourceNotFoundError):
    public_detail = "Claim not found."


class RateItemNotFound(ResourceNotFoundError):
    public_detail = "Rate item not found."


class LineNotFound(ResourceNotFoundError):
    public_detail = "Claim line not found."


class DuplicateRateCode(ResourceExistsError):
    public_detail = "Another rate item already uses that code."


class ClaimError(ValidationError):
    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.public_detail = message  # type: ignore[misc]


def cents(value: Decimal) -> Decimal:
    return Decimal(value).quantize(CENT, ROUND_HALF_UP)


# --- arithmetic (pure) ---------------------------------------------------------------------------


def line_values(line: ClaimLine) -> dict[str, Any]:
    rate = Decimal(line.rate)
    to_date, previous, contract = Decimal(line.to_date_qty), Decimal(line.previous_qty), Decimal(line.contract_qty)
    to_date_value, previous_value = cents(to_date * rate), cents(previous * rate)
    return {
        "contract_value": cents(contract * rate),
        "to_date_value": to_date_value,
        "previous_value": previous_value,
        "this_value": to_date_value - previous_value,
        "this_qty": to_date - previous,
        "percent_complete": round(float(to_date / contract * 100), 1) if contract else 0.0,
    }


def totals(
    lines: Iterable[ClaimLine], retention_pct: Decimal, retention_cap: Decimal | None, previous_payments: Decimal
) -> dict[str, Decimal]:
    t = {k: ZERO for k in ("contract_sum", "variations_sum", "works_to_date", "variations_to_date", "previous_gross")}
    for line in lines:
        v = line_values(line)
        if line.kind == "work":
            t["contract_sum"] += v["contract_value"]
            t["works_to_date"] += v["to_date_value"]
        else:
            t["variations_sum"] += v["contract_value"]
            t["variations_to_date"] += v["to_date_value"]
        t["previous_gross"] += v["previous_value"]
    gross = t["works_to_date"] + t["variations_to_date"]
    retention = cents(gross * Decimal(retention_pct) / 100)
    if retention_cap is not None:
        retention = min(retention, Decimal(retention_cap))
    net = gross - retention
    return {
        **t,
        "gross_to_date": gross,
        "gross_this_period": gross - t["previous_gross"],
        "retention_to_date": retention,
        "net_to_date": net,
        "previous_payments": cents(previous_payments),
        "this_claim": net - cents(previous_payments),
    }


# --- rate items ----------------------------------------------------------------------------------


async def get_rate_item(db: AsyncSession, item_id: int) -> RateItem:
    item = await db.get(RateItem, item_id)
    if item is None:
        raise RateItemNotFound(str(item_id))
    return item


async def _check_code(db: AsyncSession, project_id: int, code: str, item_id: int | None = None) -> None:
    clash = await db.scalar(select(RateItem.id).where(RateItem.project_id == project_id, RateItem.code == code))
    if clash and clash != item_id:
        raise DuplicateRateCode(code)


async def create_rate_item(db: AsyncSession, values: dict[str, Any]) -> RateItem:
    if values.get("node_id"):
        await tree.get_node(db, values["node_id"], values["project_id"])
    await _check_code(db, values["project_id"], values["code"])
    item = RateItem(**values)
    db.add(item)
    await db.commit()
    return item


async def update_rate_item(db: AsyncSession, item: RateItem, values: dict[str, Any]) -> RateItem:
    if values.get("node_id"):
        await tree.get_node(db, values["node_id"], item.project_id)
    if values.get("code"):
        await _check_code(db, item.project_id, values["code"], item.id)
    for key, value in values.items():
        if value is None and key not in ("unit", "node_id"):
            continue
        setattr(item, key, value)
    await db.commit()
    return item


async def seed_from_tree(db: AsyncSession, project_id: int) -> int:
    """One rate item per progress-unit node not priced yet: its budget quantity, unit and a zero rate."""
    units = await progress.progress_units(db, project_id)
    have = set((await db.execute(select(RateItem.node_id).where(RateItem.project_id == project_id))).scalars())
    codes = set((await db.execute(select(RateItem.code).where(RateItem.project_id == project_id))).scalars())
    created = 0
    for n, u in enumerate(units):
        if u.id in have:
            continue
        code = (u.display_code or u.display_path.replace(" / ", "."))[:60]
        while code in codes:
            code = f"{code[:55]}-{u.id}"
        codes.add(code)
        db.add(
            RateItem(
                project_id=project_id,
                code=code,
                description=(u.name or u.display_path)[:300],
                unit=u.uom,
                contract_qty=u.budget_qty or ZERO,
                rate=ZERO,
                node_id=u.id,
                sort_order=n,
            )
        )
        created += 1
    await db.commit()
    return created


async def read_rate_items(db: AsyncSession, items: list[RateItem]) -> list[dict[str, Any]]:
    paths = await _paths(db, {i.node_id for i in items if i.node_id})
    return [
        {
            **{k: getattr(i, k) for k in RateItem.__table__.columns.keys() if k not in ("created_at", "updated_at")},  # noqa: SIM118
            "node_path": paths.get(i.node_id or 0),
            "contract_value": cents(Decimal(i.contract_qty) * Decimal(i.rate)),
        }
        for i in items
    ]


async def _paths(db: AsyncSession, ids: set[int]) -> dict[int, str]:
    if not ids:
        return {}
    return {n.id: n.display_path for n in (await db.execute(select(AssetNode).where(AssetNode.id.in_(ids)))).scalars()}


# --- claims --------------------------------------------------------------------------------------


async def get_claim(db: AsyncSession, claim_id: int) -> Claim:
    claim = await db.get(Claim, claim_id)
    if claim is None:
        raise ClaimNotFound(str(claim_id))
    return claim


async def lines_of(db: AsyncSession, claim_id: int) -> list[ClaimLine]:
    return list(
        (
            await db.execute(
                select(ClaimLine)
                .where(ClaimLine.claim_id == claim_id)
                .order_by(ClaimLine.kind.desc(), ClaimLine.sort_order, ClaimLine.id)
            )
        ).scalars()
    )


async def earlier(db: AsyncSession, claim: Claim) -> list[Claim]:
    """Claims before this one that aren't drafts, oldest first."""
    return list(
        (
            await db.execute(
                select(Claim)
                .where(Claim.project_id == claim.project_id, Claim.id != claim.id, Claim.status != ClaimStatus.DRAFT)
                .where((Claim.period_end < claim.period_end) | ((Claim.period_end == claim.period_end) & (Claim.id < claim.id)))
                .order_by(Claim.period_end, Claim.id)
            )
        ).scalars()
    )


def _paid_or_claimed(c: Claim) -> Decimal:
    if c.certified_amount is not None:
        return Decimal(c.certified_amount)
    return Decimal(str(c.totals.get("this_claim", "0"))) if c.totals else ZERO


async def previous_payments(db: AsyncSession, claim: Claim) -> Decimal:
    return sum((_paid_or_claimed(c) for c in await earlier(db, claim)), ZERO)


def _key(line: ClaimLine) -> tuple:
    return ("rate", line.rate_item_id) if line.kind == "work" else (line.source_type, line.source_id)


async def verified_for(db: AsyncSession, project_id: int, node_ids: set[int]) -> dict[int, Decimal]:
    """Verified quantity to date at or below each node, from verified completion only."""
    if not node_ids:
        return {}
    under = await progress.under(db, project_id, node_ids)
    qty = await progress.node_quantities(db, project_id)
    return {nid: sum((qty[u].verified_qty for u in units if u in qty), ZERO) for nid, units in under.items()}


async def _variations(db: AsyncSession, project_id: int) -> list[dict[str, Any]]:
    """Approved variations: change cards (unless converted to a change order) and approved change orders."""
    out: list[dict[str, Any]] = []
    if await is_enabled(db, "change_orders", project_id):
        delta = func.coalesce(func.sum(ChangeOrderLine.delta), 0)
        rows = await db.execute(
            select(ChangeOrder, delta)
            .outerjoin(ChangeOrderLine, ChangeOrderLine.change_order_id == ChangeOrder.id)
            .where(ChangeOrder.project_id == project_id, ChangeOrder.status == "approved")
            .group_by(ChangeOrder.id)
            .order_by(ChangeOrder.id)
        )
        for co, total in rows.all():
            out.append(
                {
                    "source_type": "change_order",
                    "source_id": co.id,
                    "code": co.code,
                    "description": co.title,
                    "amount": Decimal(total),
                }
            )
    if await is_enabled(db, "change_of_scope", project_id):
        cards = (
            await db.execute(
                select(ChangeCard)
                .where(ChangeCard.project_id == project_id, ChangeCard.status.in_(("approved", "converted")))
                .order_by(ChangeCard.id)
            )
        ).scalars()
        counted_cos = {v["source_id"] for v in out}
        for card in cards:
            if card.change_order_id and card.change_order_id in counted_cos:
                continue  # the change order carries it
            amount = card.approved_amount if card.approved_amount is not None else card.estimated_amount
            out.append(
                {
                    "source_type": "change_card",
                    "source_id": card.id,
                    "code": card.code,
                    "description": card.title,
                    "amount": Decimal(amount),
                }
            )
    return out


async def refresh(db: AsyncSession, claim: Claim) -> None:
    """Rebuild a draft's lines: verified quantities, previous quantities and approved variations."""
    if claim.status != ClaimStatus.DRAFT:
        raise ClaimError("Only a draft claim can be refreshed.")
    prev_claims = await earlier(db, claim)
    prev_lines = {_key(x): x for x in await lines_of(db, prev_claims[-1].id)} if prev_claims else {}
    current = {_key(x): x for x in await lines_of(db, claim.id)}
    items = list(
        (
            await db.execute(
                select(RateItem).where(RateItem.project_id == claim.project_id).order_by(RateItem.sort_order, RateItem.code)
            )
        ).scalars()
    )
    verified = await verified_for(db, claim.project_id, {i.node_id for i in items if i.node_id})
    for n, item in enumerate(items):
        key = ("rate", item.id)
        line = current.get(key)
        if line is None:
            line = ClaimLine(claim_id=claim.id, kind="work", code=item.code, description=item.description, rate_item_id=item.id)
            db.add(line)
        qty = min(verified.get(item.node_id or 0, ZERO), Decimal(item.contract_qty))
        line.code, line.description, line.unit, line.node_id, line.sort_order = (
            item.code,
            item.description,
            item.unit,
            item.node_id,
            n,
        )
        line.contract_qty, line.rate, line.verified_qty = item.contract_qty, item.rate, qty
        line.previous_qty = prev_lines[key].to_date_qty if key in prev_lines else ZERO
        line.to_date_qty = min(Decimal(line.to_date_qty), qty) if line.overridden else qty
    for n, v in enumerate(await _variations(db, claim.project_id)):
        key = (v["source_type"], v["source_id"])
        line = current.get(key)
        if line is None:
            line = ClaimLine(
                claim_id=claim.id,
                kind="variation",
                code=v["code"],
                description=v["description"][:300],
                source_type=v["source_type"],
                source_id=v["source_id"],
                unit="item",
            )
            db.add(line)
        line.code, line.description, line.sort_order = v["code"], v["description"][:300], n
        line.contract_qty, line.rate, line.verified_qty = Decimal(1), cents(v["amount"]), Decimal(1)
        line.previous_qty = prev_lines[key].to_date_qty if key in prev_lines else ZERO
        if not line.overridden:
            line.to_date_qty = Decimal(1)
    await db.flush()


async def create_claim(db: AsyncSession, project: Project, values: dict[str, Any], actor_id: int) -> Claim:
    if values["period_end"] < values["period_start"]:
        raise ClaimError("The period ends before it starts.")
    if await db.scalar(select(Claim.id).where(Claim.project_id == project.id, Claim.status == ClaimStatus.DRAFT)):
        raise ClaimError("This project already has a draft claim. Submit or delete it first.")
    values = {k: v for k, v in values.items() if k != "project_id"}
    claim = Claim(project_id=project.id, code=await next_reference(db, "PC", project.id), created_by_id=actor_id, **values)
    db.add(claim)
    await db.flush()
    await refresh(db, claim)
    await record_transition(db, ENTITY, claim.id, None, ClaimStatus.DRAFT, actor_id)
    await db.commit()
    return claim


async def update_claim(db: AsyncSession, claim: Claim, values: dict[str, Any]) -> Claim:
    if claim.status != ClaimStatus.DRAFT:
        raise ClaimError("Only a draft claim can be changed.")
    for key, value in values.items():
        if value is None and key not in ("retention_cap", "notes"):
            continue
        setattr(claim, key, value)
    if claim.period_end < claim.period_start:
        raise ClaimError("The period ends before it starts.")
    await db.commit()
    return claim


async def get_line(db: AsyncSession, claim: Claim, line_id: int) -> ClaimLine:
    line = await db.get(ClaimLine, line_id)
    if line is None or line.claim_id != claim.id:
        raise LineNotFound(str(line_id))
    return line


async def set_to_date(db: AsyncSession, claim: Claim, line: ClaimLine, qty: Decimal) -> ClaimLine:
    if claim.status != ClaimStatus.DRAFT:
        raise ClaimError("Only a draft claim can be changed.")
    limit = Decimal(line.verified_qty) if line.kind == "work" else Decimal(line.contract_qty)
    if qty > limit:
        raise ClaimError(
            f"Only verified completion can be claimed: at most {limit.normalize():f} for {line.code}."
            if line.kind == "work"
            else f"A variation can be claimed up to its approved amount ({limit.normalize():f})."
        )
    line.to_date_qty, line.overridden = qty, True
    await db.commit()
    return line


async def figures(db: AsyncSession, claim: Claim, lines: list[ClaimLine] | None = None) -> dict[str, Decimal]:
    """Live for a draft; frozen at submission afterwards."""
    if claim.status != ClaimStatus.DRAFT and claim.totals:
        return {k: Decimal(str(v)) for k, v in claim.totals.items()}
    lines = lines if lines is not None else await lines_of(db, claim.id)
    return totals(lines, claim.retention_pct, claim.retention_cap, await previous_payments(db, claim))


async def transition(db: AsyncSession, claim: Claim, target: str, actor_id: int, values: dict[str, Any]) -> Claim:
    assert_transition(FLOW, claim.status, target)
    before = claim.status
    on = values.get("on") or date.today()
    if target == ClaimStatus.SUBMITTED:
        if await db.scalar(
            select(Claim.id).where(
                Claim.project_id == claim.project_id,
                Claim.status == ClaimStatus.SUBMITTED,
                Claim.id != claim.id,
                Claim.period_end > claim.period_end,
            )
        ):
            raise ClaimError("A later claim is already submitted.")
        claim.totals = {k: str(v) for k, v in (await figures(db, claim)).items()}
        claim.submitted_at = datetime.now(UTC)
    elif target == ClaimStatus.DRAFT:
        claim.totals, claim.submitted_at = {}, None
    elif target == ClaimStatus.CERTIFIED:
        if values.get("certified_amount") is None:
            raise ClaimError("Enter the certified amount.")
        claim.certified_amount, claim.certified_on, claim.certified_by_id = values["certified_amount"], on, actor_id
        claim.client_reference = values.get("client_reference") or claim.client_reference
    elif target == ClaimStatus.PAID:
        claim.paid_amount = values.get("paid_amount") if values.get("paid_amount") is not None else claim.certified_amount
        claim.paid_on = on
    claim.status = target
    await record_transition(db, ENTITY, claim.id, before, target, actor_id, values.get("note"))
    await db.commit()
    await publish(
        f"claims.claim.{target}",
        {
            "project_id": claim.project_id,
            "claim_id": claim.id,
            "code": claim.code,
            "this_claim": claim.totals.get("this_claim"),
            "certified_amount": str(claim.certified_amount) if claim.certified_amount is not None else None,
        },
    )
    return claim


async def delete_claim(db: AsyncSession, claim: Claim) -> None:
    if claim.status != ClaimStatus.DRAFT:
        raise ClaimError("Only a draft claim can be deleted.")
    await db.delete(claim)
    await db.commit()


def read_line(line: ClaimLine) -> dict[str, Any]:
    return {
        **{k: getattr(line, k) for k in ClaimLine.__table__.columns.keys() if k != "claim_id"},  # noqa: SIM118
        **line_values(line),
    }


async def read_claim(db: AsyncSession, claim: Claim, currency: str, with_lines: bool = False) -> dict[str, Any]:
    lines = await lines_of(db, claim.id)
    out = {
        **{k: getattr(claim, k) for k in Claim.__table__.columns.keys() if k not in ("totals",)},  # noqa: SIM118
        "currency": currency,
        "totals": await figures(db, claim, lines),
    }
    if with_lines:
        out["lines"] = [read_line(x) for x in lines]
    return out


def _m(value: Any) -> str:
    return f"{Decimal(value):,.2f}"


def _q(value: Any) -> str:
    return f"{Decimal(value).normalize():f}"


async def pdf(db: AsyncSession, claim: Claim, project: Project) -> bytes:
    data = await read_claim(db, claim, project.currency, with_lines=True)
    t = data["totals"]
    doc = Document(
        title=f"Progress Claim {claim.code}",
        subtitle=f"{project.name} · {project.code}",
        footer=f"{project.code} {claim.code}",
        landscape=True,
    )
    doc.fields(
        [
            ("Period", f"{claim.period_start.isoformat()} to {claim.period_end.isoformat()}"),
            ("Status", claim.status.capitalize()),
            ("Client", project.client_name or ""),
            ("Currency", project.currency),
            ("Basis", "Quantities are verified completion only (inspected and passed, or attested by a verifier)."),
        ]
    )
    head = [
        "Code",
        "Description",
        "Unit",
        "Contract qty",
        "Rate",
        "Verified",
        "Previous",
        "To date",
        "This period",
        "Value to date",
        "This claim",
    ]
    widths = [0.08, 0.22, 0.05, 0.08, 0.08, 0.07, 0.07, 0.07, 0.08, 0.1, 0.1]
    numeric = set(range(3, 11))
    for kind, title in (("work", "Schedule of rates"), ("variation", "Approved variations")):
        rows = [
            [
                x["code"],
                x["description"],
                x["unit"] or "",
                _q(x["contract_qty"]),
                _m(x["rate"]),
                _q(x["verified_qty"]),
                _q(x["previous_qty"]),
                _q(x["to_date_qty"]),
                _q(x["this_qty"]),
                _m(x["to_date_value"]),
                _m(x["this_value"]),
            ]
            for x in data["lines"]
            if x["kind"] == kind
        ]
        if rows:
            doc.heading(title)
            doc.table(head, rows, widths=widths, numeric=numeric)
    doc.heading("Summary")
    doc.table(
        ["", "Amount"],
        [
            ["Works to date", _m(t["works_to_date"])],
            ["Variations to date", _m(t["variations_to_date"])],
            ["Gross value to date", _m(t["gross_to_date"])],
            [
                f"Less retention ({_q(claim.retention_pct)} %{', capped' if claim.retention_cap is not None else ''})",
                _m(t["retention_to_date"]),
            ],
            ["Net value to date", _m(t["net_to_date"])],
            ["Less previous payments", _m(t["previous_payments"])],
            ["Amount claimed this period", _m(t["this_claim"])],
        ],
        widths=[0.5, 0.2],
        numeric={1},
    )
    if claim.certified_amount is not None:
        doc.fields(
            [
                ("Certified", _m(claim.certified_amount)),
                ("Certified on", claim.certified_on.isoformat() if claim.certified_on else ""),
                ("Client reference", claim.client_reference or ""),
                ("Paid", _m(claim.paid_amount) if claim.paid_amount is not None else ""),
            ]
        )
    return render_pdf(doc)


EXPORT_COLUMNS = [
    ("code", "Claim"),
    ("period_start", "From"),
    ("period_end", "To"),
    ("status", "Status"),
    ("gross_to_date", "Gross to date"),
    ("retention_to_date", "Retention"),
    ("previous_payments", "Previous payments"),
    ("this_claim", "This claim"),
    ("certified_amount", "Certified"),
    ("certified_on", "Certified on"),
    ("paid_amount", "Paid"),
    ("paid_on", "Paid on"),
]
