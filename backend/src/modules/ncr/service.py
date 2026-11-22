"""The issues engine: raise, step, void, flag overrides, upgrade and escalation, registers and gate facts.

Public functions for other modules:

* ``create_issue(db, project_id=..., title=..., raised_by_id=..., issue_type=..., template_id=..., ...)`` raises a
  punch or NCR (used for "raise issue from failed inspection"; the ``inspections.item.ncr_requested`` event is
  handled in ``events.py``). ``create_ncr`` keeps the original NCR signature.
* ``blocking_issues(db, project_id, node_ids)`` -> the open issues with ``mdr_effect = blocks`` in an MDR
  dossier scope (the MDR compile gate).
* ``mdr_register(db, project_id, node_ids)`` -> the NCR / concession register rows of a dossier (client issues
  only, never ``excluded`` or void); marks them client-seen.
* ``completion_blockers(db, project_id, node_id)`` -> open Cat A punches and open NCRs with
  ``completion_effect = blocks`` on a work anchor (the work-completion gate).
* ``mark_client_seen(db, issue_ids, channel)`` for any client-facing output that includes issues.
"""

from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import Select, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from ...infrastructure.auth.authorization import load_permissions
from ...infrastructure.modules import publish
from ...infrastructure.pdf import Document, render_pdf
from ...infrastructure.records import assert_transition, history_of, next_reference, record_transition
from ..asset_tree import service as tree
from ..asset_tree.constants import NodeStatus
from ..asset_tree.models import AssetItem, AssetLevel, AssetNode
from ..common.exceptions import PermissionDeniedError, ResourceNotFoundError
from ..contacts.models import Company
from ..contacts.service import contact_names
from ..notifications.constants import Category
from ..notifications.service import notify
from ..projects.models import Project
from ..projects.permissions import ProjectPermissionName
from ..projects.service import readable_project
from ..role.models import RolePermission, UserRole
from ..team.models import TeamMembership
from ..user.models import User
from . import templates as tpl
from .constants import (
    DONE,
    EFFECTIVENESS_STATEMENT,
    FLOWS,
    LOCKED_ORIGINS,
    MDR_RANK,
    NEEDS_CONCESSION,
    STEP_AT,
    STEPS,
    TERMINAL,
    ActionKind,
    ActionStatus,
    AnchorKind,
    CompletionEffect,
    Flag,
    IssueType,
    MdrEffect,
    NcrStatus,
    Origin,
    PunchCategory,
    Visibility,
)
from .models import IssueFlagOverride, IssueLink, IssueTemplate, IssueTemplateRevision, Ncr, NcrAction
from .permissions import NcrPermissionName as P
from .schemas import NcrActionRead, NcrRead
from .templates import IssueRuleError

ENTITY = "ncr"
OPEN_ACTION = (ActionStatus.OPEN.value, ActionStatus.IN_PROGRESS.value)
S = NcrStatus


class NcrNotFoundError(ResourceNotFoundError):
    public_detail = "NCR not found."


class NcrActionNotFoundError(ResourceNotFoundError):
    public_detail = "Action not found."


class IssueForbidden(PermissionDeniedError):
    public_detail = "You can't do that on this issue."

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.public_detail = message  # type: ignore[misc]


# --- callers and visibility --------------------------------------------------------------------------


def is_external(user: dict[str, Any], held: frozenset[str]) -> bool:
    """Portal users (clients, subcontractors) reach a project through its client team, without ``projects.read``."""
    return not user.get("is_superuser") and ProjectPermissionName.READ.value not in held


async def user_is_external(db: AsyncSession, user_id: int, project_id: int) -> bool:
    """A portal account of this project: in its client team, without ``projects.read``."""
    user = await db.get(User, user_id)
    project = await db.get(Project, project_id)
    if user is None or user.is_superuser or project is None or project.client_team_id is None:
        return False
    member = await db.scalar(
        select(TeamMembership.user_id).where(
            TeamMembership.team_id == project.client_team_id, TeamMembership.user_id == user_id
        )
    )
    if member is None:
        return False
    held = await load_permissions(db, user_id)
    return ProjectPermissionName.READ.value not in held


def require(held: frozenset[str], user: dict[str, Any], permission: P) -> None:
    if not user.get("is_superuser") and permission.value not in held:
        raise IssueForbidden(f"That step needs the {permission.value} permission.")


def is_open(issue: Ncr) -> bool:
    return issue.status not in TERMINAL


def link_of(ncr: Ncr) -> str:
    return f"/issues?project={ncr.project_id}&id={ncr.id}"


def total_cost(ncr: Ncr) -> Decimal:
    return Decimal(ncr.rework_cost or 0) + Decimal(ncr.delay_cost or 0) + Decimal(ncr.other_cost or 0)


async def user_names(db: AsyncSession, ids: set[int | None]) -> dict[int, str]:
    wanted = {i for i in ids if i}
    if not wanted:
        return {}
    return dict((await db.execute(select(User.id, User.name).where(User.id.in_(wanted)))).tuples().all())


async def get_ncr(db: AsyncSession, ncr_id: int) -> Ncr:
    ncr = await db.get(Ncr, ncr_id)
    if ncr is None:
        raise NcrNotFoundError("No such NCR")
    return ncr


async def readable_issue(db: AsyncSession, issue_id: int, user: dict[str, Any], held: frozenset[str]) -> Ncr:
    """The issue, if the caller may read its project; internal issues answer 404 to external callers."""
    issue = await get_ncr(db, issue_id)
    await readable_project(db, issue.project_id, user["id"], held)
    if is_external(user, held) and issue.visibility != Visibility.CLIENT:
        raise NcrNotFoundError("No such NCR")
    return issue


async def get_action(db: AsyncSession, ncr: Ncr, action_id: int) -> NcrAction:
    action = await db.get(NcrAction, action_id)
    if action is None or action.ncr_id != ncr.id:
        raise NcrActionNotFoundError("No such action")
    return action


async def mark_client_seen(db: AsyncSession, issue_ids: list[int] | set[int], channel: str) -> None:
    """Record that client-side people have seen these issues (first value wins; never cleared). Caller commits."""
    if not issue_ids:
        return
    await db.execute(
        update(Ncr)
        .where(Ncr.id.in_(list(issue_ids)), Ncr.client_seen_at.is_(None), Ncr.visibility == Visibility.CLIENT.value)
        .values(client_seen_at=datetime.now(UTC), client_seen_channel=channel[:20])
        .execution_options(synchronize_session=False)
    )


# --- reading -----------------------------------------------------------------------------------------


async def read_one(db: AsyncSession, issue: Ncr, user: dict[str, Any], held: frozenset[str]) -> dict[str, Any]:
    """One issue with its actions, as the caller may see it; an external read marks it client-seen."""
    external = is_external(user, held)
    if external and issue.client_seen_at is None:
        await mark_client_seen(db, [issue.id], "api")
        await db.commit()
        await db.refresh(issue)
    return (await read_ncrs(db, [issue], with_actions=True, external=external))[0]


async def _node_labels(db: AsyncSession, ids: set[int]) -> dict[int, str]:
    if not ids:
        return {}
    rows = (await db.execute(select(AssetNode.id, AssetNode.display_path, AssetNode.code).where(AssetNode.id.in_(ids)))).all()
    return {i: (path or code) for i, path, code in rows}


async def _item_labels(db: AsyncSession, ids: set[int]) -> dict[int, str]:
    if not ids:
        return {}
    return dict((await db.execute(select(AssetItem.id, AssetItem.tag).where(AssetItem.id.in_(ids)))).tuples().all())


async def read_ncrs(
    db: AsyncSession, ncrs: list[Ncr], *, with_actions: bool = False, external: bool = False
) -> list[dict[str, Any]]:
    ids = [n.id for n in ncrs]
    actions: list[NcrAction] = []
    links: list[IssueLink] = []
    if ids:
        actions = list(
            (
                await db.execute(select(NcrAction).where(NcrAction.ncr_id.in_(ids)).order_by(NcrAction.due_date, NcrAction.id))
            ).scalars()
        )
        links = list((await db.execute(select(IssueLink).where(IssueLink.issue_id.in_(ids)))).scalars())
    people = await user_names(
        db,
        {n.raised_by_id for n in ncrs}
        | {n.responsible_user_id for n in ncrs}
        | {n.verified_by_id for n in ncrs}
        | {a.responsible_id for a in actions}
        | {a.verified_by_id for a in actions},
    )
    contacts = await contact_names(db, {n.responsible_contact_id for n in ncrs if n.responsible_contact_id})
    company_ids = {n.responsible_company_id for n in ncrs if n.responsible_company_id}
    companies = (
        dict((await db.execute(select(Company.id, Company.name).where(Company.id.in_(company_ids)))).tuples().all())
        if company_ids
        else {}
    )
    template_ids = {n.template_id for n in ncrs if n.template_id}
    template_names = (
        dict(
            (await db.execute(select(IssueTemplate.id, IssueTemplate.name).where(IssueTemplate.id.in_(template_ids))))
            .tuples()
            .all()
        )
        if template_ids
        else {}
    )
    nodes = await _node_labels(
        db,
        {i for n in ncrs for i in (n.anchor_node_id, n.location_node_id) if i}
        | {lk.target_id for lk in links if lk.target_kind == AnchorKind.NODE},
    )
    items = await _item_labels(
        db, {n.anchor_item_id for n in ncrs if n.anchor_item_id} | {lk.target_id for lk in links if lk.target_kind == "item"}
    )
    hidden: set[int] = set()
    if external:
        linked = {i for n in ncrs for i in (n.upgraded_from_id, n.escalated_from_id, n.successor_id) if i}
        if linked:
            hidden = set(
                (
                    await db.execute(select(Ncr.id).where(Ncr.id.in_(linked), Ncr.visibility != Visibility.CLIENT.value))
                ).scalars()
            )
    today = date.today()
    by_ncr: dict[int, list[NcrActionRead]] = {i: [] for i in ids}
    for a in actions:
        by_ncr[a.ncr_id].append(
            NcrActionRead.model_validate(a).model_copy(
                update={
                    "responsible_name": people.get(a.responsible_id) if a.responsible_id else None,
                    "verified_by_name": people.get(a.verified_by_id) if a.verified_by_id else None,
                    "overdue": bool(a.due_date and a.due_date < today and a.status in OPEN_ACTION),
                }
            )
        )
    links_of: dict[int, list[dict[str, Any]]] = {i: [] for i in ids}
    for lk in links:
        label = nodes.get(lk.target_id) if lk.target_kind == AnchorKind.NODE else items.get(lk.target_id)
        links_of[lk.issue_id].append({"kind": lk.target_kind, "target_id": lk.target_id, "label": label})
    out = []
    for n in ncrs:
        mine = by_ncr.get(n.id, [])
        update_: dict[str, Any] = {
            "raised_by_name": people.get(n.raised_by_id) if n.raised_by_id else None,
            "responsible_user_name": people.get(n.responsible_user_id) if n.responsible_user_id else None,
            "responsible_contact_name": contacts.get(n.responsible_contact_id) if n.responsible_contact_id else None,
            "responsible_company_name": (companies.get(n.responsible_company_id) if n.responsible_company_id else None),
            "verified_by_name": people.get(n.verified_by_id) if n.verified_by_id else None,
            "template_name": template_names.get(n.template_id) if n.template_id else None,
            "anchor_label": (
                nodes.get(n.anchor_node_id) if n.anchor_node_id else (items.get(n.anchor_item_id) if n.anchor_item_id else None)
            ),
            "location_label": nodes.get(n.location_node_id) if n.location_node_id else None,
            "links": links_of.get(n.id, []),
            "is_open": is_open(n),
            "total_cost": total_cost(n),
            "open_actions": sum(1 for a in mine if a.status in OPEN_ACTION),
            "actions": mine if with_actions else [],
        }
        for key in ("upgraded_from_id", "escalated_from_id", "successor_id"):
            if getattr(n, key) in hidden:
                update_[key] = None
        out.append(NcrRead.model_validate(n).model_copy(update=update_).model_dump(mode="json"))
    return out


async def scope_node_ids(db: AsyncSession, node_ids: list[int] | set[int]) -> set[int]:
    scope: set[int] = set()
    for node_id in node_ids:
        scope |= set(await tree.subtree_ids(db, node_id, with_lineage=True))
    return scope


def in_scope(scope: set[int]) -> Any:
    """Anchored issues whose anchor node, Item's node or work anchor is in the scope."""
    items = select(AssetItem.id).where(AssetItem.node_id.in_(scope))
    return or_(Ncr.anchor_node_id.in_(scope), Ncr.work_anchor_node_id.in_(scope), Ncr.anchor_item_id.in_(items))


def filters(
    project_id: int,
    status: str | None = None,
    severity: str | None = None,
    source: str | None = None,
    trade: str | None = None,
    open_only: bool = False,
    search: str | None = None,
    *,
    issue_type: str | None = None,
    category: str | None = None,
    punch_category: str | None = None,
    origin: str | None = None,
    visibility: str | None = None,
    mdr_effect: str | None = None,
    external: bool = False,
    scope: set[int] | None = None,
    item_id: int | None = None,
    location_node_id: int | None = None,
    linked: tuple[str, int] | None = None,
) -> list[Any]:
    where: list[Any] = [Ncr.project_id == project_id]
    if external:
        where.append(Ncr.visibility == Visibility.CLIENT.value)
    if issue_type:
        where.append(Ncr.issue_type == issue_type)
    if status:
        where.append(Ncr.status == status)
    if severity:
        where.append(Ncr.severity == severity)
    if source:
        where.append(Ncr.source == source)
    if trade:
        where.append(func.lower(Ncr.trade) == trade.lower())
    if category:
        where.append(Ncr.category == category)
    if punch_category:
        where.append(Ncr.punch_category == punch_category)
    if origin:
        where.append(Ncr.origin == origin)
    if visibility:
        where.append(Ncr.visibility == visibility)
    if mdr_effect:
        where.append(Ncr.mdr_effect == mdr_effect)
    if open_only:
        where.append(Ncr.status.not_in(TERMINAL))
    if scope is not None:
        where.append(in_scope(scope))
    if item_id:
        where.append(Ncr.anchor_item_id == item_id)
    if location_node_id:
        where.append(Ncr.location_node_id == location_node_id)
    if linked:
        where.append(
            Ncr.id.in_(select(IssueLink.issue_id).where(IssueLink.target_kind == linked[0], IssueLink.target_id == linked[1]))
        )
    if search:
        like = f"%{search.lower()}%"
        where.append(
            or_(
                func.lower(Ncr.title + " " + Ncr.code).like(like),
                func.lower(func.coalesce(Ncr.location, "")).like(like),
                func.lower(func.coalesce(Ncr.description, "")).like(like),
            )
        )
    return where


# --- raising -----------------------------------------------------------------------------------------


async def _check_node(db: AsyncSession, node_id: int, project_id: int) -> AssetNode:
    node = await tree.get_node(db, node_id, project_id)
    if node.status == NodeStatus.RETIRED:
        raise IssueRuleError("That node is retired; pick its successor.")
    return node


async def _anchor(db: AsyncSession, project_id: int, node_id: int | None, item_id: int | None) -> tuple[str | None, int | None]:
    """(anchor role, work anchor node id) for an anchored issue; 422 when the path has no work anchor."""
    if node_id and item_id:
        raise IssueRuleError("Anchor the issue to a node or an Item, not both.")
    if item_id:
        item = await tree.get_item(db, item_id, project_id)
        if item.status == NodeStatus.RETIRED:
            raise IssueRuleError("That Item is retired.")
        work = item.work_anchor_id or (await tree.work_anchor_for(db, item.node_id)).id
        return "item", work
    if node_id:
        node = await _check_node(db, node_id, project_id)
        level = await db.get(AssetLevel, node.level_id)
        roles = list(level.roles) if level else []
        role = next((r for r in ("work_anchor", "inspection_anchor", "physical") if r in roles), roles[0] if roles else None)
        return role, (await tree.work_anchor_for(db, node.id)).id
    return None, None


async def _has_breakdown(db: AsyncSession, project_id: int) -> bool:
    return await db.scalar(select(AssetLevel.id).where(AssetLevel.project_id == project_id).limit(1)) is not None


async def _check_assignee(db: AsyncSession, project_id: int, visibility: str, user_id: int | None) -> None:
    if user_id and visibility == Visibility.INTERNAL and await user_is_external(db, user_id, project_id):
        raise IssueRuleError("An internal issue can't be assigned to an external account.")


async def create_issue(
    db: AsyncSession,
    *,
    project_id: int,
    title: str,
    raised_by_id: int | None,
    issue_type: IssueType | str | None = None,
    template_id: int | None = None,
    category: str | None = None,
    external: bool = False,
    enforce_anchor: bool = True,
    visibility: str | None = None,
    answers: dict[str, Any] | None = None,
    links: list[dict[str, Any]] | None = None,
    commit: bool = True,
    **fields: Any,
) -> Ncr:
    """Raise a punch or an NCR on its template's latest published revision. For other modules too.

    ``external`` (the raiser is a portal account) forces ``origin = client`` (or ``external_audit`` when the
    template says so) and client visibility. ``enforce_anchor=False`` lets automation raise a project-level
    issue whatever the category. ``visibility`` overrides the template default (upgrades keep the punch's).
    """
    values = {k: (v.value if hasattr(v, "value") else v) for k, v in fields.items() if v is not None}
    template: IssueTemplate | None
    if template_id:
        template = await tpl.get_template(db, template_id, project_id)
        if not template.is_active:
            raise IssueRuleError("That template is not active.")
        if issue_type and str(issue_type) != template.issue_type:
            raise IssueRuleError(f"That template raises a {template.issue_type}, not a {issue_type}.")
    else:
        kind = str(issue_type or IssueType.NCR)
        template = await tpl.default_template(db, project_id, category or "general", kind)
        if template is None:
            raise IssueRuleError(f"There is no {kind} template for this category.")
    revision = await tpl.published(db, template.id)
    if revision is None:
        raise IssueRuleError("That template has no published revision yet.")
    kind = template.issue_type
    cat = await tpl.category_of(db, project_id, template.category)
    if not cat["is_active"]:
        raise IssueRuleError(f"The category {cat['label']} is not active.")

    origin = values.pop("origin", None) or revision.default_origin
    if external:
        origin = Origin.EXTERNAL_AUDIT.value if revision.default_origin == Origin.EXTERNAL_AUDIT else Origin.CLIENT.value
    flags: dict[str, Any] = {
        "visibility": visibility or revision.default_visibility,
        "mdr_effect": revision.default_mdr_effect,
        "completion_effect": revision.completion_effect,
    }
    if origin in LOCKED_ORIGINS:
        flags["visibility"] = Visibility.CLIENT.value
        if flags["mdr_effect"] == MdrEffect.EXCLUDED:
            flags["mdr_effect"] = MdrEffect.REGISTER_ONLY.value

    severity = values.pop("severity", None) or revision.default_severity or "minor"
    punch_category = values.pop("punch_category", None)
    if kind == IssueType.PUNCH:
        punch_category = punch_category or revision.default_punch_category
        if punch_category not in {c.value for c in PunchCategory}:
            raise IssueRuleError("A punch item needs a category: A (hold), B (before handover) or C (information).")
    else:
        punch_category = None

    node_id, item_id = values.pop("anchor_node_id", None), values.pop("anchor_item_id", None)
    role, work_anchor = await _anchor(db, project_id, node_id, item_id)
    location_node_id = values.pop("location_node_id", None)
    if role is None:
        if enforce_anchor and not cat["allows_project_level"] and await _has_breakdown(db, project_id):
            raise IssueRuleError(f"Anchor the issue to a node or Item: {cat['label']} issues can't be raised at project level.")
        if location_node_id:
            await _check_node(db, location_node_id, project_id)
    elif location_node_id:
        raise IssueRuleError("Only a project-level issue takes a location node; this one has an anchor.")

    await _check_assignee(db, project_id, flags["visibility"], values.get("responsible_user_id"))
    checked = await tpl.check_answers(db, project_id, revision.fields, answers or {})
    values.setdefault("raised_on", date.today())
    ncr = Ncr(
        project_id=project_id,
        code=await next_reference(db, "PL" if kind == IssueType.PUNCH else "NCR", project_id),
        title=title[:300],
        issue_type=kind,
        category=template.category,
        template_id=template.id,
        template_revision_id=revision.id,
        answers=checked,
        raised_by_id=raised_by_id,
        origin=origin,
        severity=severity,
        punch_category=punch_category,
        status=S.OPEN.value,
        anchor_node_id=node_id,
        anchor_item_id=item_id,
        anchor_role=role,
        work_anchor_node_id=work_anchor,
        location_node_id=location_node_id,
        **flags,
        **values,
    )
    db.add(ncr)
    await db.flush()
    for link in links or []:
        link_kind, target = str(link["kind"]), int(link["target_id"])
        if link_kind == AnchorKind.NODE:
            await _check_node(db, target, project_id)
        else:
            await tree.get_item(db, target, project_id)
        db.add(IssueLink(issue_id=ncr.id, target_kind=link_kind, target_id=target))
    note = "Raised"
    if (revision.default_visibility, revision.default_mdr_effect) != (ncr.visibility, ncr.mdr_effect):
        note += (
            f" (template defaults {revision.default_visibility}/{revision.default_mdr_effect}, "
            f"effective {ncr.visibility}/{ncr.mdr_effect})"
        )
    await record_transition(db, ENTITY, ncr.id, None, ncr.status, raised_by_id, note=note)
    await notify_responsible(db, ncr, raised_by_id)
    if commit:
        await db.commit()
        await publish_raised(ncr)
    return ncr


async def publish_raised(ncr: Ncr) -> None:
    await publish(
        "ncr.issue.raised",
        {
            "project_id": ncr.project_id,
            "issue_id": ncr.id,
            "code": ncr.code,
            "issue_type": ncr.issue_type,
            "inspection_id": ncr.inspection_id,
            "inspection_item_id": ncr.inspection_item_id,
        },
    )


async def create_ncr(
    db: AsyncSession, *, project_id: int, title: str, raised_by_id: int | None, commit: bool = True, **fields: Any
) -> Ncr:
    """Raise an NCR on the default template of its category (``general`` unless ``category`` is given),
    notify the responsible user, and (by default) commit. Kept for modules that raised NCRs before templates."""
    return await create_issue(
        db,
        project_id=project_id,
        title=title,
        raised_by_id=raised_by_id,
        issue_type=IssueType.NCR,
        category=fields.pop("category", None),
        enforce_anchor=False,
        commit=commit,
        **fields,
    )


async def notify_responsible(db: AsyncSession, ncr: Ncr, actor_id: int | None) -> None:
    if ncr.responsible_user_id:
        kind = (
            f"Cat {ncr.punch_category} punch item" if ncr.issue_type == IssueType.PUNCH else f"{ncr.severity} non-conformance"
        )
        await notify(
            db,
            [ncr.responsible_user_id],
            Category.ASSIGNMENT,
            f"{ncr.code}: {ncr.title}",
            body=f"A {kind} is assigned to you.",
            link=link_of(ncr),
            entity=(ENTITY, ncr.id),
            actor_id=actor_id,
        )


# --- editing -----------------------------------------------------------------------------------------

DISPOSITION_FIELDS = {"disposition", "disposition_notes", "concession_reference"}
ROOT_CAUSE_FIELDS = {"root_cause_category", "root_cause_description"}


async def _revision_fields(db: AsyncSession, issue: Ncr) -> list[dict[str, Any]]:
    if not issue.template_revision_id:
        return []
    rev = await db.get(IssueTemplateRevision, issue.template_revision_id)
    return list(rev.fields) if rev else []


def step_index(issue: Ncr) -> int:
    return STEP_AT[issue.issue_type].get(issue.status, DONE)


async def update_issue(db: AsyncSession, issue: Ncr, changes: dict[str, Any], actor_id: int) -> None:
    """Apply a partial update (details, answers by step, NCR analysis fields while their step is open)."""
    if issue.status == S.VOID:
        raise IssueRuleError("A void issue can't be changed.")
    at = step_index(issue)
    if issue.issue_type == IssueType.NCR:
        if DISPOSITION_FIELDS & changes.keys() and at > STEPS[IssueType.NCR].index("disposition"):
            raise IssueRuleError("The disposition is recorded; it can't change after its step.")
        if ROOT_CAUSE_FIELDS & changes.keys() and at > STEPS[IssueType.NCR].index("root_cause"):
            raise IssueRuleError("The root cause is recorded; it can't change after its step.")
    if "punch_category" in changes:
        if issue.issue_type != IssueType.PUNCH:
            raise IssueRuleError("Only punch items have a Cat A/B/C category.")
        if not is_open(issue):
            raise IssueRuleError("The punch item is no longer open.")
    if "answers" in changes:
        incoming = dict(changes.pop("answers") or {})
        fields = await _revision_fields(db, issue)
        steps = STEPS[issue.issue_type]
        by_key = {f["key"]: f for f in fields}
        for key, value in incoming.items():
            f = by_key.get(key)
            if f and steps.index(f["step"]) < at and issue.answers.get(key) != value:
                raise IssueRuleError(f"{f['label']} belongs to a completed step and is read-only.")
        checked = await tpl.check_answers(db, issue.project_id, fields, incoming)
        issue.answers = {**issue.answers, **checked}
    before = issue.responsible_user_id
    if changes.get("responsible_user_id"):
        await _check_assignee(db, issue.project_id, issue.visibility, changes["responsible_user_id"])
    for key, value in changes.items():
        setattr(issue, key, value.value if hasattr(value, "value") else value)
    if issue.responsible_user_id and issue.responsible_user_id != before:
        await notify_responsible(db, issue, actor_id)
    await db.commit()


# --- workflow ----------------------------------------------------------------------------------------

STEP_PERMISSION: dict[tuple[str, str, str], P] = {
    (IssueType.PUNCH, S.OPEN, S.RECTIFIED): P.TRANSITION,
    (IssueType.PUNCH, S.RECTIFIED, S.VERIFIED): P.VERIFY,
    (IssueType.PUNCH, S.RECTIFIED, S.OPEN): P.VERIFY,
    (IssueType.PUNCH, S.VERIFIED, S.CLOSED): P.VERIFY,
    (IssueType.NCR, S.OPEN, S.DISPOSITION): P.TRANSITION,
    (IssueType.NCR, S.DISPOSITION, S.ROOT_CAUSE): P.VERIFY,
    (IssueType.NCR, S.ROOT_CAUSE, S.CORRECTIVE_ACTION): P.TRANSITION,
    (IssueType.NCR, S.CORRECTIVE_ACTION, S.EFFECTIVENESS): P.TRANSITION,
    (IssueType.NCR, S.EFFECTIVENESS, S.CLOSED): P.VERIFY,
    (IssueType.NCR, S.EFFECTIVENESS, S.CORRECTIVE_ACTION): P.VERIFY,
}


async def transition(
    db: AsyncSession,
    issue: Ncr,
    target: str,
    user: dict[str, Any],
    held: frozenset[str],
    *,
    note: str | None = None,
    attest: bool = False,
    closed_by_inspection_id: int | None = None,
) -> None:
    """Move an issue one step of its type's fixed workflow, enforcing step fields and the separation rules."""
    if not is_open(issue):
        raise IssueRuleError(f"The issue is {issue.status}.")
    assert_transition(FLOWS[issue.issue_type], issue.status, target)
    current, kind, actor = issue.status, issue.issue_type, user["id"]
    require(held, user, STEP_PERMISSION[(kind, current, target)])
    if is_external(user, held) and not (kind == IssueType.PUNCH and current == S.RECTIFIED and issue.origin == Origin.CLIENT):
        raise IssueForbidden("Client accounts may only verify the punch items they raised.")

    backwards = (kind, current, target) in {
        (IssueType.PUNCH, S.RECTIFIED, S.OPEN),
        (IssueType.NCR, S.EFFECTIVENESS, S.CORRECTIVE_ACTION),
    }
    if backwards:
        if not note:
            raise IssueRuleError("Give the reason for sending it back.")
    else:
        steps = STEPS[kind]
        upto = STEP_AT[kind].get(target, DONE)
        completing = {s for i, s in enumerate(steps) if STEP_AT[kind][current] <= i < upto}
        missing = tpl.missing_required(await _revision_fields(db, issue), issue.answers, completing)
        if missing:
            raise IssueRuleError(f"Fill in first: {', '.join(missing)}.")

    if closed_by_inspection_id:
        issue.closed_by_inspection_id = closed_by_inspection_id
    now = datetime.now(UTC)
    chain = [target]
    if kind == IssueType.PUNCH:
        if target == S.RECTIFIED:
            issue.rectified_by_id = actor
        elif target in (S.VERIFIED, S.CLOSED):
            if actor == issue.rectified_by_id:
                raise IssueForbidden("The person who rectified a punch item can't verify or close it.")
            if target == S.VERIFIED:
                issue.verified_by_id, issue.verified_at = actor, now
                if not await _separate_close(db, issue):
                    chain.append(S.CLOSED)
    else:
        if target == S.ROOT_CAUSE:
            if not issue.disposition:
                raise IssueRuleError("Record the disposition first.")
            if issue.disposition in NEEDS_CONCESSION and not issue.concession_reference:
                raise IssueRuleError("A use-as-is or repair disposition needs the client's concession reference.")
            issue.disposition_by_id = actor
        elif target == S.CORRECTIVE_ACTION and current == S.ROOT_CAUSE:
            if not (issue.root_cause_category and issue.root_cause_description):
                raise IssueRuleError("Record the root cause category and statement first.")
        elif target == S.EFFECTIVENESS:
            actions = await _actions(db, issue)
            if not any(a.kind == ActionKind.CORRECTIVE and a.status in ("done", "verified") for a in actions):
                raise IssueRuleError("At least one corrective action must be done.")
            if any(a.status in OPEN_ACTION for a in actions):
                raise IssueRuleError("Every action must be done or cancelled first.")
        elif target == S.CLOSED:
            if not attest:
                raise IssueRuleError("Closing an NCR needs the effectiveness verification sign-off (attest).")
            completers = {a.completed_by_id for a in await _actions(db, issue)}
            if actor == issue.disposition_by_id or actor in completers:
                raise IssueForbidden(
                    "Nobody who recorded the disposition or completed a corrective action may verify effectiveness."
                )
            issue.effectiveness_statement = EFFECTIVENESS_STATEMENT.format(code=issue.code)
            issue.verified_by_id, issue.verified_at = actor, now
            note = (note + " · " if note else "") + "Effectiveness verified (attested)"

    before = current
    for step in chain:
        await record_transition(db, ENTITY, issue.id, before, step, actor, note)
        before = step
    issue.status = chain[-1]
    issue.closed_at = now if issue.status == S.CLOSED else None
    await _notify_status(db, issue, actor, note)
    await db.commit()


async def _separate_close(db: AsyncSession, issue: Ncr) -> bool:
    rev = await db.get(IssueTemplateRevision, issue.template_revision_id) if issue.template_revision_id else None
    return bool(rev and rev.separate_close)


async def _actions(db: AsyncSession, issue: Ncr) -> list[NcrAction]:
    return list((await db.execute(select(NcrAction).where(NcrAction.ncr_id == issue.id))).scalars())


async def _notify_status(db: AsyncSession, issue: Ncr, actor_id: int, note: str | None) -> None:
    watchers = {issue.raised_by_id, issue.responsible_user_id} - {None, actor_id}
    await notify(
        db,
        [w for w in watchers if w],
        Category.STATUS,
        f"{issue.code} is now {issue.status.replace('_', ' ')}",
        body=note or issue.title,
        link=link_of(issue),
        entity=(ENTITY, issue.id),
        actor_id=actor_id,
    )


async def change_status(
    db: AsyncSession, ncr: Ncr, target: str, note: str | None, user: dict[str, Any], held: frozenset[str]
) -> None:
    """The original NCR status route: the same workflow (``attest`` is implied by an explicit close)."""
    await transition(db, ncr, target, user, held, note=note, attest=target == S.CLOSED)


async def void(db: AsyncSession, issue: Ncr, reason: str, actor_id: int) -> None:
    if not is_open(issue):
        raise IssueRuleError(f"The issue is already {issue.status}.")
    before = issue.status
    issue.status = S.VOID.value
    issue.void_reason, issue.voided_by_id, issue.voided_at = reason, actor_id, datetime.now(UTC)
    await record_transition(db, ENTITY, issue.id, before, S.VOID, actor_id, reason)
    await _notify_status(db, issue, actor_id, reason)
    await db.commit()


async def notify_action(db: AsyncSession, ncr: Ncr, action: NcrAction, actor_id: int) -> None:
    if action.responsible_id and action.responsible_id != actor_id:
        await notify(
            db,
            [action.responsible_id],
            Category.ASSIGNMENT,
            f"{ncr.code}: {action.kind} action",
            body=action.description[:300] + (f" (due {action.due_date.isoformat()})" if action.due_date else ""),
            link=link_of(ncr),
            entity=(ENTITY, ncr.id),
            actor_id=actor_id,
        )


async def update_action(db: AsyncSession, ncr: Ncr, action: NcrAction, changes: dict[str, Any], actor_id: int) -> None:
    before_responsible, before_status = action.responsible_id, action.status
    for key, value in changes.items():
        setattr(action, key, value.value if hasattr(value, "value") else value)
    if action.status != before_status:
        now = datetime.now(UTC)
        if action.status == ActionStatus.CANCELLED and not action.cancel_reason:
            raise IssueRuleError("Cancelling an action needs a reason.")
        if action.status in (ActionStatus.DONE, ActionStatus.VERIFIED) and action.completed_at is None:
            action.completed_at, action.completed_by_id = now, actor_id
        if action.status == ActionStatus.VERIFIED:
            action.verified_by_id, action.verified_at = actor_id, now
        elif before_status == ActionStatus.VERIFIED:
            action.verified_by_id, action.verified_at = None, None
        if action.status in OPEN_ACTION:
            action.completed_at, action.completed_by_id = None, None
    if action.responsible_id and action.responsible_id != before_responsible:
        await notify_action(db, ncr, action, actor_id)
    await db.commit()


async def history(db: AsyncSession, ncr: Ncr) -> list[dict[str, Any]]:
    rows = await history_of(db, ENTITY, ncr.id)
    names = await user_names(db, {r["changed_by_id"] for r in rows})
    return [{**r, "changed_by_name": names.get(r["changed_by_id"]) if r["changed_by_id"] else None} for r in rows]


# --- flags -------------------------------------------------------------------------------------------

FLAG_VALUES = {
    Flag.VISIBILITY: {v.value for v in Visibility},
    Flag.MDR_EFFECT: {v.value for v in MdrEffect},
    Flag.COMPLETION_EFFECT: {v.value for v in CompletionEffect},
}


async def qa_authority_ids(db: AsyncSession) -> set[int]:
    """Users whose roles carry ``ncr.manage`` (the QA authority)."""
    rows = await db.execute(
        select(UserRole.user_id)
        .join(RolePermission, RolePermission.role_id == UserRole.role_id)
        .where(RolePermission.permission_name == P.MANAGE.value)
    )
    return set(rows.scalars())


async def override_flag(db: AsyncSession, issue: Ncr, flag: Flag, value: str, reason: str, actor_id: int) -> IssueFlagOverride:
    """Change one flag with the guardrails; audited, and loosening notifies the QA authority."""
    if value not in FLAG_VALUES[flag]:
        raise IssueRuleError(f"{flag.value} must be one of {', '.join(sorted(FLAG_VALUES[flag]))}.")
    if issue.status == S.VOID:
        raise IssueRuleError("A void issue can't be changed.")
    old = getattr(issue, flag.value)
    if old == value:
        raise IssueRuleError(f"{flag.value} is already {value}.")
    loosening = False
    if flag == Flag.VISIBILITY:
        if value == Visibility.CLIENT:
            raise IssueRuleError("Widening to client is not an override: use “Raise external NCR” instead.")
        if issue.origin in LOCKED_ORIGINS:
            raise IssueRuleError("Client and external-audit issues are always client-visible.")
        if issue.client_seen_at:
            raise IssueRuleError("The client has seen this issue; it can't become internal again.")
        loosening = True
    elif flag == Flag.MDR_EFFECT:
        if value == MdrEffect.EXCLUDED and issue.origin in LOCKED_ORIGINS:
            raise IssueRuleError("Client and external-audit issues can't be excluded from the MDR.")
        loosening = MDR_RANK[value] < MDR_RANK[old]
    else:
        loosening = old == CompletionEffect.BLOCKS and value == CompletionEffect.NONE
    setattr(issue, flag.value, value)
    entry = IssueFlagOverride(
        project_id=issue.project_id,
        issue_id=issue.id,
        flag=flag.value,
        old_value=old,
        new_value=value,
        reason=reason,
        loosening=loosening,
        actor_id=actor_id,
    )
    db.add(entry)
    await record_transition(
        db,
        ENTITY,
        issue.id,
        issue.status,
        issue.status,
        actor_id,
        f"{'Loosening' if loosening else 'Tightening'} override: {flag.value} {old} → {value}. {reason}",
    )
    if loosening:
        await notify(
            db,
            await qa_authority_ids(db),
            Category.APPROVAL,
            f"{issue.code}: {flag.value.replace('_', ' ')} loosened to {value.replace('_', ' ')}",
            body=reason,
            link=link_of(issue),
            entity=(ENTITY, issue.id),
            actor_id=actor_id,
        )
    await db.commit()
    return entry


async def overrides_of(db: AsyncSession, issue: Ncr) -> list[dict[str, Any]]:
    rows = list(
        (
            await db.execute(
                select(IssueFlagOverride).where(IssueFlagOverride.issue_id == issue.id).order_by(IssueFlagOverride.id)
            )
        ).scalars()
    )
    names = await user_names(db, {r.actor_id for r in rows})
    return [
        {
            "id": r.id,
            "flag": r.flag,
            "old_value": r.old_value,
            "new_value": r.new_value,
            "reason": r.reason,
            "loosening": r.loosening,
            "actor_id": r.actor_id,
            "actor_name": names.get(r.actor_id) if r.actor_id else None,
            "created_at": r.created_at,
        }
        for r in rows
    ]


# --- upgrade and escalation --------------------------------------------------------------------------


async def _ncr_template(db: AsyncSession, issue: Ncr, template_id: int | None) -> IssueTemplate:
    if template_id:
        template = await tpl.get_template(db, template_id, issue.project_id)
    else:
        found = await tpl.default_template(db, issue.project_id, issue.category, IssueType.NCR)
        if found is None:
            raise IssueRuleError("There is no NCR template for this category.")
        template = found
    if template.issue_type != IssueType.NCR:
        raise IssueRuleError("Pick an NCR template.")
    return template


async def _carry(db: AsyncSession, template: IssueTemplate, answers: dict[str, Any], keys: set[str] | None) -> dict[str, Any]:
    rev = await tpl.published(db, template.id)
    wanted = {f["key"] for f in (rev.fields if rev else [])}
    return {k: v for k, v in answers.items() if k in wanted and (keys is None or k in keys)}


async def _successor_fields(issue: Ncr) -> dict[str, Any]:
    return {
        "anchor_node_id": issue.anchor_node_id,
        "anchor_item_id": issue.anchor_item_id,
        "location_node_id": issue.location_node_id,
        "location": issue.location,
        "trade": issue.trade,
        "spec_reference": issue.spec_reference,
        "source": issue.source,
        "source_reference": issue.source_reference,
        "inspection_id": issue.inspection_id,
        "inspection_item_id": issue.inspection_item_id,
        "responsible_user_id": issue.responsible_user_id,
        "responsible_contact_id": issue.responsible_contact_id,
        "responsible_company_id": issue.responsible_company_id,
    }


async def upgrade(db: AsyncSession, punch: Ncr, template_id: int | None, actor_id: int, note: str | None = None) -> Ncr:
    """A new NCR from a punch: answers copied by key (photos keep their file ids), same visibility; the punch closes as
    ``upgraded``. There is no downgrade."""
    if punch.issue_type != IssueType.PUNCH:
        raise IssueRuleError("Only a punch item can be upgraded; an NCR is never downgraded.")
    if not is_open(punch):
        raise IssueRuleError(f"The punch item is {punch.status}.")
    template = await _ncr_template(db, punch, template_id)
    links = [{"kind": lk.target_kind, "target_id": lk.target_id} for lk in await _links(db, punch)]
    ncr = await create_issue(
        db,
        project_id=punch.project_id,
        title=punch.title,
        raised_by_id=actor_id,
        template_id=template.id,
        description=punch.description,
        origin=punch.origin,
        visibility=punch.visibility,
        answers=await _carry(db, template, punch.answers, None),
        enforce_anchor=False,
        links=links,
        commit=False,
        **await _successor_fields(punch),
    )
    ncr.upgraded_from_id, punch.successor_id = punch.id, ncr.id
    before, punch.status = punch.status, S.UPGRADED.value
    await record_transition(db, ENTITY, punch.id, before, S.UPGRADED, actor_id, f"Upgraded to {ncr.code}. {note or ''}".strip())
    await db.commit()
    await publish_raised(ncr)
    return ncr


async def _links(db: AsyncSession, issue: Ncr) -> list[IssueLink]:
    return list((await db.execute(select(IssueLink).where(IssueLink.issue_id == issue.id))).scalars())


def photo_ids(answers: dict[str, Any]) -> set[int]:
    out: set[int] = set()
    for value in answers.values():
        if isinstance(value, list) and all(isinstance(v, int) and not isinstance(v, bool) for v in value):
            out |= set(value)
    return out


async def raise_external(
    db: AsyncSession,
    issue: Ncr,
    actor_id: int,
    *,
    template_id: int | None,
    title: str | None,
    carry_description: bool,
    carry_answers: list[str],
    carry_photos: list[int],
) -> Ncr:
    """A new client-visible NCR from an internal issue, carrying only what was picked; the source closes as
    ``escalated`` with an internal-only link. Comments, RCA, actions and history never carry over."""
    if issue.visibility != Visibility.INTERNAL:
        raise IssueRuleError("Only an internal issue can be raised as an external NCR.")
    if not is_open(issue):
        raise IssueRuleError(f"The issue is {issue.status}.")
    template = await _ncr_template(db, issue, template_id)
    rev = await tpl.published(db, template.id)
    fields = rev.fields if rev else []
    if set(carry_photos) - photo_ids(issue.answers):
        raise IssueRuleError("Only the issue's own photos can carry over.")
    carried = await _carry(db, template, issue.answers, set(carry_answers))
    carried = {k: ([p for p in v if p in carry_photos] if _is_photo(fields, k) else v) for k, v in carried.items()}
    if carry_photos and not any(_is_photo(fields, k) and v for k, v in carried.items()):
        target = next((f["key"] for f in fields if f["type"] == "photo" and f["step"] == "raise"), None)
        if target is None:
            raise IssueRuleError("The NCR template has no photo field to carry the photos into.")
        carried[target] = list(carry_photos)
    ncr = await create_issue(
        db,
        project_id=issue.project_id,
        title=title or issue.title,
        raised_by_id=actor_id,
        template_id=template.id,
        description=issue.description if carry_description else None,
        origin=issue.origin,
        visibility=Visibility.CLIENT.value,
        answers=carried,
        enforce_anchor=False,
        commit=False,
        **{**await _successor_fields(issue), "responsible_user_id": None},
    )
    ncr.escalated_from_id, issue.successor_id = issue.id, ncr.id
    before, issue.status = issue.status, S.ESCALATED.value
    await record_transition(db, ENTITY, issue.id, before, S.ESCALATED, actor_id, f"Raised as external NCR {ncr.code}")
    await db.commit()
    await publish_raised(ncr)
    return ncr


def _is_photo(fields: list[dict[str, Any]], key: str) -> bool:
    return any(f["key"] == key and f["type"] == "photo" for f in fields)


# --- gates and registers -----------------------------------------------------------------------------


def _fact(i: Ncr) -> dict[str, Any]:
    return {
        "id": i.id,
        "code": i.code,
        "title": i.title,
        "issue_type": i.issue_type,
        "category": i.category,
        "status": i.status,
        "punch_category": i.punch_category,
        "severity": i.severity,
        "visibility": i.visibility,
        "mdr_effect": i.mdr_effect,
        "completion_effect": i.completion_effect,
        "anchor_node_id": i.anchor_node_id,
        "anchor_item_id": i.anchor_item_id,
        "work_anchor_node_id": i.work_anchor_node_id,
        "location_node_id": i.location_node_id,
        "project_level": i.anchor_node_id is None and i.anchor_item_id is None,
    }


async def _dossier_scope(db: AsyncSession, project_id: int, node_ids: list[int] | None) -> Select[tuple[Ncr]]:
    """Issues in an MDR dossier scope: anchored inside it; project-level without a location; or project-level
    whose location is the scope node, inside it or an ancestor of it."""
    base = select(Ncr).where(Ncr.project_id == project_id)
    if not node_ids:
        return base
    scope = await scope_node_ids(db, node_ids)
    ancestors: set[int] = set()
    for node_id in node_ids:
        ancestors |= set(tree.path_ids(await tree.get_node(db, node_id, project_id)))
    project_level = Ncr.anchor_node_id.is_(None) & Ncr.anchor_item_id.is_(None) & Ncr.work_anchor_node_id.is_(None)
    return base.where(
        or_(
            in_scope(scope),
            project_level & (Ncr.location_node_id.is_(None) | Ncr.location_node_id.in_(scope | ancestors)),
        )
    )


async def blocking_issues(db: AsyncSession, project_id: int, node_ids: list[int] | None = None) -> list[dict[str, Any]]:
    """The MDR compile gate: open issues with ``mdr_effect = blocks`` in the dossier scope.

    ``node_ids`` are the dossier's scope nodes (each with its descendants, Items and lineage); empty or None means
    the whole project. Internal issues count too (they block while open, though they are never printed). Each fact
    is ``{id, code, title, issue_type, category, status, punch_category, severity, visibility, mdr_effect,
    completion_effect, anchor_node_id, anchor_item_id, work_anchor_node_id, location_node_id, project_level}``.
    An empty list means the gate is clear.
    """
    query = (await _dossier_scope(db, project_id, node_ids)).where(
        Ncr.status.not_in(TERMINAL), Ncr.mdr_effect == MdrEffect.BLOCKS.value
    )
    return [_fact(i) for i in (await db.execute(query.order_by(Ncr.id))).scalars()]


async def mdr_register(
    db: AsyncSession, project_id: int, node_ids: list[int] | None = None, *, mark_seen: bool = True
) -> list[dict[str, Any]]:
    """The dossier's NCR / concession register: client-visible issues with ``mdr_effect`` blocks or register_only,
    never void, upgraded or escalated. Marks the rows client-seen (channel ``mdr``); the caller commits."""
    query = (await _dossier_scope(db, project_id, node_ids)).where(
        Ncr.visibility == Visibility.CLIENT.value,
        Ncr.mdr_effect != MdrEffect.EXCLUDED.value,
        Ncr.status.not_in((S.VOID.value, S.UPGRADED.value, S.ESCALATED.value)),
    )
    rows = list((await db.execute(query.order_by(Ncr.code))).scalars())
    read = await read_ncrs(db, rows, external=True)
    if mark_seen:
        await mark_client_seen(db, [r.id for r in rows], "mdr")
    return read


async def completion_blockers(db: AsyncSession, project_id: int, node_id: int) -> list[dict[str, Any]]:
    """The work-completion gate: open Cat A punches and open NCRs with ``completion_effect = blocks`` on the
    scope (project-level issues never block completion)."""
    scope = await scope_node_ids(db, [node_id])
    query = select(Ncr).where(
        Ncr.project_id == project_id,
        in_scope(scope),
        Ncr.status.not_in(TERMINAL),
        or_(
            (Ncr.issue_type == IssueType.PUNCH.value) & (Ncr.punch_category == PunchCategory.A.value),
            (Ncr.issue_type == IssueType.NCR.value) & (Ncr.completion_effect == CompletionEffect.BLOCKS.value),
        ),
    )
    return [_fact(i) for i in (await db.execute(query.order_by(Ncr.id))).scalars()]


async def summary(
    db: AsyncSession, project_id: int, *, external: bool, issue_type: str = IssueType.PUNCH, level_key: str | None = None
) -> dict[str, Any]:
    """Counts for the punch list / NCR register: by category, by Cat A/B/C, by area (the anchor's ancestor at
    ``level_key``), with open Cat A (blocking work completion) and open MDR-blocking counts."""
    where = filters(project_id, issue_type=issue_type, external=external)
    rows = list((await db.execute(select(Ncr).where(*where))).scalars())
    node_of: dict[int, int] = {}
    item_nodes = {i.anchor_item_id for i in rows if i.anchor_item_id}
    if item_nodes:
        node_of = dict(
            (await db.execute(select(AssetItem.id, AssetItem.node_id).where(AssetItem.id.in_(item_nodes)))).tuples().all()
        )
    group_of: dict[int, AssetNode] = {}
    if level_key:
        anchor_nodes = {i.anchor_node_id or node_of.get(i.anchor_item_id or 0) for i in rows} - {None}
        nodes = {n.id: n for n in (await db.execute(select(AssetNode).where(AssetNode.id.in_(anchor_nodes)))).scalars()}
        ancestor_ids = {a for n in nodes.values() for a in tree.path_ids(n)}
        at_level = {
            n.id: n
            for n in (
                await db.execute(select(AssetNode).where(AssetNode.id.in_(ancestor_ids), AssetNode.level_key == level_key))
            ).scalars()
        }
        for nid, n in nodes.items():
            match = next((at_level[a] for a in tree.path_ids(n) if a in at_level), None)
            if match:
                group_of[nid] = match

    def bucket() -> dict[str, int]:
        return {"open": 0, "closed": 0, "cat_a_open": 0, "cat_b_open": 0, "cat_c_open": 0, "blocks_mdr": 0}

    by_category: dict[str, dict[str, int]] = {}
    by_area: dict[str, dict[str, Any]] = {}
    totals = bucket()
    for i in rows:
        if i.status == S.VOID:
            continue
        anchor = i.anchor_node_id or node_of.get(i.anchor_item_id or 0)
        area = group_of.get(anchor) if anchor else None
        area_key = str(area.id) if area else ("project" if anchor is None else "other")
        targets = [
            totals,
            by_category.setdefault(i.category, bucket()),
            by_area.setdefault(
                area_key,
                {
                    "node_id": area.id if area else None,
                    "label": (area.display_path or area.code) if area else ("Project level" if anchor is None else "Other"),
                    **bucket(),
                },
            ),
        ]
        for t in targets:
            if is_open(i):
                t["open"] += 1
                if i.punch_category:
                    t[f"cat_{i.punch_category.lower()}_open"] += 1
                if i.mdr_effect == MdrEffect.BLOCKS:
                    t["blocks_mdr"] += 1
            elif i.status == S.CLOSED:
                t["closed"] += 1
    return {
        "issue_type": issue_type,
        "totals": totals,
        "by_category": [{"category": k, **v} for k, v in sorted(by_category.items())],
        "by_area": sorted(by_area.values(), key=lambda a: str(a["label"])),
    }


# --- outputs -----------------------------------------------------------------------------------------


def label(value: str | None) -> str:
    return (value or "").replace("_", " ").capitalize()


async def report_pdf(db: AsyncSession, ncr: Ncr) -> bytes:
    read = (await read_ncrs(db, [ncr], with_actions=True))[0]
    project = await db.get(Project, ncr.project_id)
    kind = "Punch item" if ncr.issue_type == IssueType.PUNCH else "Non-Conformance Report"
    doc = Document(
        title=f"{kind} {ncr.code}",
        subtitle=f"{ncr.title} · {project.code if project else ''} {project.name if project else ''}".strip(),
        footer=f"{ncr.code}",
    )
    responsible = read["responsible_user_name"] or read["responsible_contact_name"] or read["responsible_company_name"] or "-"
    pairs: list[tuple[str, Any]] = [
        ("Status", label(ncr.status)),
        ("Template", read["template_name"] or "-"),
        ("Category", label(ncr.category)),
        (
            "Punch category" if ncr.issue_type == IssueType.PUNCH else "Severity",
            f"Cat {ncr.punch_category}" if ncr.issue_type == IssueType.PUNCH else label(ncr.severity),
        ),
        ("Origin", label(ncr.origin)),
        ("Raised by", read["raised_by_name"] or "-"),
        ("Date raised", ncr.raised_on.isoformat() if ncr.raised_on else "-"),
        ("Anchor", read["anchor_label"] or ("Project" + (f" · {read['location_label']}" if read["location_label"] else ""))),
        ("Location", ncr.location or "-"),
        ("Trade", ncr.trade or "-"),
        ("Responsible party", responsible),
        ("Source", label(ncr.source) + (f" ({ncr.source_reference})" if ncr.source_reference else "")),
        ("Spec / drawing ref.", ncr.spec_reference or "-"),
        ("Visibility / MDR", f"{label(ncr.visibility)} / {label(ncr.mdr_effect)}"),
    ]
    doc.fields(pairs)
    doc.heading("Description")
    doc.paragraph(ncr.description or "-")
    fields = await _revision_fields(db, ncr)
    answered = [
        (f["label"], ncr.answers.get(f["key"]))
        for f in fields
        if f["type"] != "photo" and ncr.answers.get(f["key"]) not in (None, "")
    ]
    if answered:
        doc.heading("Template fields")
        doc.fields([(k, ", ".join(map(str, v)) if isinstance(v, list) else str(v)) for k, v in answered])
    if ncr.issue_type == IssueType.NCR:
        doc.heading("Root cause")
        doc.fields([("Category", label(ncr.root_cause_category) or "-")])
        doc.paragraph(ncr.root_cause_description or "-")
        doc.heading("Disposition")
        disp: list[tuple[str, Any]] = [("Disposition", label(ncr.disposition) or "-")]
        if ncr.concession_reference:
            disp.append(("Concession ref.", ncr.concession_reference))
        doc.fields(disp)
        if ncr.disposition_notes:
            doc.paragraph(ncr.disposition_notes)
        doc.heading("Corrective and preventive actions")
        if read["actions"]:
            doc.table(
                ["Type", "Action", "Responsible", "Due", "Status", "Verified"],
                [
                    [
                        label(a["kind"]),
                        a["description"],
                        a["responsible_name"] or "-",
                        a["due_date"] or "-",
                        label(a["status"]),
                        f"{a['verified_by_name'] or ''} {(a['verified_at'] or '')[:10]}".strip() or "-",
                    ]
                    for a in read["actions"]
                ],
                widths=[0.11, 0.37, 0.16, 0.11, 0.11, 0.14],
            )
        else:
            doc.paragraph("None recorded.")
        if ncr.effectiveness_statement:
            doc.heading("Effectiveness verification")
            doc.paragraph(ncr.effectiveness_statement)
            doc.fields(
                [
                    ("Verified by", read["verified_by_name"] or "-"),
                    ("Verified at", (read["verified_at"] or "")[:16].replace("T", " ") or "-"),
                ]
            )
        doc.heading("Cost impact")
        doc.table(
            ["Rework", "Delay", "Other", "Total", "Days delay"],
            [
                [
                    f"{ncr.rework_cost:.2f}",
                    f"{ncr.delay_cost:.2f}",
                    f"{ncr.other_cost:.2f}",
                    f"{total_cost(ncr):.2f}",
                    ncr.days_delay,
                ]
            ],
            numeric={0, 1, 2, 3, 4},
        )
    elif ncr.verified_by_id:
        doc.fields([("Verified by", read["verified_by_name"] or "-")])
    trail = await history(db, ncr)
    if trail:
        doc.heading("Status history")
        doc.table(
            ["When", "From", "To", "By", "Note"],
            [
                [
                    (r["changed_at"] or "")[:16].replace("T", " "),
                    label(r["from_status"]) or "-",
                    label(r["to_status"]),
                    r["changed_by_name"] or "-",
                    r["note"] or "",
                ]
                for r in trail
            ],
            widths=[0.18, 0.2, 0.2, 0.17, 0.25],
        )
    return render_pdf(doc)


EXPORT_COLUMNS = [
    ("code", "NCR"),
    ("title", "Title"),
    ("status", "Status"),
    ("severity", "Severity"),
    ("raised_on", "Raised"),
    ("raised_by_name", "Raised by"),
    ("location", "Location"),
    ("trade", "Trade"),
    ("source", "Source"),
    ("source_reference", "Source ref."),
    ("spec_reference", "Spec ref."),
    ("responsible", "Responsible"),
    ("root_cause_category", "Root cause"),
    ("disposition", "Disposition"),
    ("rework_cost", "Rework cost"),
    ("delay_cost", "Delay cost"),
    ("other_cost", "Other cost"),
    ("total_cost", "Total cost"),
    ("days_delay", "Days delay"),
    ("open_actions", "Open actions"),
]

PUNCH_COLUMNS = [
    ("code", "Punch"),
    ("title", "Title"),
    ("punch_category", "Cat"),
    ("category", "Category"),
    ("status", "Status"),
    ("anchor", "Anchor"),
    ("location", "Location"),
    ("responsible", "Responsible"),
    ("due_date", "Due"),
    ("raised_on", "Raised"),
    ("raised_by_name", "Raised by"),
    ("origin", "Origin"),
    ("visibility", "Visibility"),
    ("mdr_effect", "MDR effect"),
]

NCR_REGISTER_COLUMNS = [
    ("code", "NCR"),
    ("title", "Title"),
    ("template_name", "Template"),
    ("category", "Category"),
    ("origin", "Origin"),
    ("severity", "Severity"),
    ("status", "Status"),
    ("anchor", "Anchor"),
    ("disposition", "Disposition"),
    ("concession_reference", "Concession"),
    ("root_cause_category", "Root cause"),
    ("raised_on", "Raised"),
    ("closed", "Closed"),
    ("verified_by_name", "Verified by"),
    ("visibility", "Visibility"),
    ("mdr_effect", "MDR effect"),
    ("total_cost", "Total cost"),
]


async def export_rows(db: AsyncSession, where: list[Any], *, external: bool = False) -> list[dict[str, Any]]:
    rows = list((await db.execute(select(Ncr).where(*where).order_by(Ncr.id))).scalars())
    read = await read_ncrs(db, rows, external=external)
    for r in read:
        r["responsible"] = r["responsible_user_name"] or r["responsible_contact_name"] or r["responsible_company_name"]
        r["anchor"] = r["anchor_label"] or ("Project" + (f" · {r['location_label']}" if r["location_label"] else ""))
        r["closed"] = (r["closed_at"] or "")[:10] or None
        for key in ("rework_cost", "delay_cost", "other_cost", "total_cost"):
            r[key] = float(r[key])
    if external:
        await mark_client_seen(db, [r["id"] for r in read], "export")
    return read
