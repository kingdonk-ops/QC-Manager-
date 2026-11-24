"""The dossier issue override: a manager lets a dossier issue past pending holds with a reason. A documentation report is
raised and linked, the holds stay pending and carry the override's reference, issue goes ahead, and every refusal leaves
no report, record, annotation or audit entry behind."""

from typing import Any

import pytest
import pytest_asyncio
from crudauth import get_password_hash
from httpx import AsyncClient
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.infrastructure.audit_ledger.models import AuditEntry
from src.infrastructure.config.settings import settings
from src.infrastructure.http_exceptions import ConflictException
from src.infrastructure.modules import state
from src.infrastructure.modules.models import ModuleSetting
from src.modules.inspections.models import QualityGate
from src.modules.mdr.models import MdrDossier, MdrOverride
from src.modules.ncr.models import Ncr
from src.modules.ncr.service import create_ncr
from src.modules.user.models import User
from tests.fixtures.accounts import reset_password_budget
from tests.integration.quality_safety.site_tree import Tree, build_tree
from tests.integration.rbac.test_user_permissions import _grant, _login

pytestmark = [pytest.mark.asyncio, pytest.mark.usefixtures("fresh_login_lockout")]

API = "/api/v1/inspections"
MDR = "/api/v1/mdr"
STAFF = (
    "projects.read",
    "files.read",
    "ncr.read",
    "audit.read",
    "asset_tree.read",
    *(f"mdr.{a}" for a in ("read", "create", "update", "delete", "submit", "sign")),
    *(f"inspections.{a}" for a in ("read", "create", "update", "delete", "approve")),
)
MANAGER = (*STAFF, "mdr.override")
OUTSIDER = ("mdr.read", "mdr.override")  # no project visibility
ONE_CHECK = [{"title": "Checks", "items": [{"text": "Surface clean and dry"}]}]
REASON = "The client accepted the risk in writing"
AUDIT_ACTION = "mdr.dossier.overridden"


@pytest_asyncio.fixture(autouse=True)
async def fresh_switches():
    state.invalidate()
    yield
    state.invalidate()


async def _user(db: AsyncSession, username: str) -> dict[str, Any]:
    u = User(
        name=username.capitalize(),
        username=username,
        email=f"{username}@example.com",
        hashed_password=get_password_hash("Password123!"),
        is_superuser=False,
        profile_image_url="https://example.com/x.jpg",
    )
    db.add(u)
    await db.flush()
    user_id, name = u.id, u.name  # plain values: the row expires on commit and must not be reloaded afterwards
    await db.commit()
    await reset_password_budget(user_id)
    return {"id": user_id, "name": name, "username": username, "password": "Password123!"}


class World:
    def __init__(self, client: AsyncClient, db: AsyncSession, tree: Tree, users: dict[str, dict[str, Any]]):
        self.client, self.db, self.tree, self.users = client, db, tree, users
        # Plain ints only: a refused request rolls the shared session back and expires every loaded row, so reading
        # an attribute of the project afterwards would try to reload it outside the async context.
        self.project_id: int = tree.project.id
        self.headers: dict[str, str] = {}
        self.current: str | None = None

    async def as_(self, who: str) -> "World":
        if self.current != who:
            self.headers = {"X-CSRF-Token": await _login(self.client, self.users[who])}
            self.current = who
        return self

    async def gate(self, **values: Any) -> dict[str, Any]:
        body = {"project_id": self.project_id, "title": "Pre-issue hold", **values}
        r = await self.client.post(f"{API}/gates/", json=body, headers=self.headers)
        assert r.status_code == 201, r.text
        return r.json()

    async def release(self, gate_id: int) -> None:
        r = await self.client.post(f"{API}/gates/{gate_id}/release", json={"authority": "contractor_qa"}, headers=self.headers)
        assert r.status_code == 200, r.text

    async def gates(self) -> dict[str, dict[str, Any]]:
        r = await self.client.get(f"{API}/gates/", params={"project_id": self.project_id, "items_per_page": 100})
        assert r.status_code == 200, r.text
        return {g["number"]: g for g in r.json()["data"]}

    async def dossier(self, *scope: int) -> str:
        body = {"project_id": self.project_id, "title": "Piping turnover", "scope_node_ids": list(scope)}
        r = await self.client.post(f"{MDR}/dossiers/", json=body, headers=self.headers)
        assert r.status_code == 201, r.text
        return f"{MDR}/dossiers/{r.json()['id']}"

    async def check(self, base: str, key: str = "quality_gates") -> dict[str, Any]:
        """One row of the dossier gate, with the overall readiness."""
        gate = (await self.client.get(f"{base}/gate")).json()
        return {**next(c for c in gate["checks"] if c["key"] == key), "ready": gate["ready"], "counts": gate["counts"]}

    async def override(self, base: str, expect: int = 201, **body: Any) -> Any:
        r = await self.client.post(
            f"{base}/override", json={"purpose": "review", "reason": REASON, **body}, headers=self.headers
        )
        assert r.status_code == expect, r.text
        return r.json()

    async def issue(self, base: str, expect: int, purpose: str = "review") -> Any:
        r = await self.client.post(f"{base}/issue", json={"purpose": purpose}, headers=self.headers)
        assert r.status_code == expect, r.text
        return r.json()

    async def stored(self) -> tuple[int, int, int, int]:
        """Everything an override writes: records, reports, audit entries and annotated gates."""
        counts = []
        for query in (
            select(func.count()).select_from(MdrOverride),
            select(func.count()).select_from(Ncr).where(Ncr.project_id == self.project_id),
            select(func.count()).select_from(AuditEntry).where(AuditEntry.action == AUDIT_ACTION),
            select(func.count()).select_from(QualityGate).where(QualityGate.override_id.is_not(None)),
        ):
            counts.append(await self.db.scalar(query) or 0)
        return counts[0], counts[1], counts[2], counts[3]


async def make_world(
    client: AsyncClient, db: AsyncSession, test_user: dict, test_user_2: dict, tmp_path, monkeypatch: pytest.MonkeyPatch
) -> World:
    monkeypatch.setattr(settings, "FILE_STORAGE_DIR", str(tmp_path))
    tree = await build_tree(db, "OV-1")
    users = {"staff": test_user, "manager": test_user_2, "outsider": await _user(db, "ovoutsider")}
    await _grant(db, test_user["id"], "ov_staff", *STAFF)
    await _grant(db, test_user_2["id"], "ov_manager", *MANAGER)
    await _grant(db, users["outsider"]["id"], "ov_outsider", *OUTSIDER)
    return await World(client, db, tree, users).as_("manager")


@pytest_asyncio.fixture
async def world(
    client: AsyncClient, db_session: AsyncSession, test_user: dict, test_user_2: dict, tmp_path, monkeypatch: pytest.MonkeyPatch
) -> World:
    return await make_world(client, db_session, test_user, test_user_2, tmp_path, monkeypatch)


# --- recording an override -------------------------------------------------------------------------------


async def test_overriding_two_holds_raises_a_report_annotates_them_and_lets_the_dossier_issue(world: World):
    w = world
    base = await w.dossier(w.tree.asset)
    first = await w.gate(attachment_kind="node", attachment_id=w.tree.rsw)
    second = await w.gate(attachment_kind="node", attachment_id=w.tree.rsw)
    await w.issue(base, 422)  # blocked before the override

    made = await w.override(base)
    assert made["purpose"] == "review" and made["severity"] == "major" and made["reason"] == REASON
    assert made["gate_numbers"] == [first["number"], second["number"]]
    assert made["created_by_name"] and made["report_id"] and made["report_code"]
    covered = [b["reference"] for b in made["blockers"]]
    assert covered == [first["number"], second["number"]]  # the non-blocking report needs no entry of its own

    gates = await w.gates()
    for raised in (first, second):  # annotated, never closed
        shown = gates[raised["number"]]
        assert shown["status"] == "pending" and shown["blocks_progress"] is True
        assert (shown["override_id"], shown["override_ref"]) == (made["id"], made["reference"])

    quality = await w.check(base)
    assert quality["status"] == "overridden" and quality["ready"] is True
    assert [f["reference"] for f in quality["findings"]] == [first["number"], second["number"]]
    assert quality["counts"] == {"plain_pending_holds": 0, "overridden_pending_holds": 2, "open_reports": 1}

    issued = await w.issue(base, 201)
    stored = next(c for c in issued["gate"] if c["key"] == "quality_gates")
    assert stored["status"] == "overridden"  # the revision keeps the status it was issued with


async def test_the_override_links_a_documentation_report_and_writes_one_audit_entry(world: World):
    w = world
    base = await w.dossier(w.tree.asset)
    held = await w.gate(attachment_kind="node", attachment_id=w.tree.rsw)
    made = await w.override(base, severity="critical")

    report = await w.db.get(Ncr, made["report_id"])
    assert report is not None and report.code == made["report_code"]
    assert report.severity == "critical" and report.status == "open"
    assert made["reference"] in report.title
    assert REASON in (report.description or "") and held["number"] in (report.description or "")

    audits = list((await w.db.execute(select(AuditEntry).where(AuditEntry.action == AUDIT_ACTION))).scalars())
    assert len(audits) == 1
    entry = audits[0]
    assert str(base.rsplit("/", 1)[1]) == str(entry.entity_id)
    assert entry.after["report_code"] == made["report_code"] and entry.after["gate_numbers"] == [held["number"]]
    assert made["reference"] in entry.summary

    listed = (await w.client.get(f"{base}/overrides")).json()
    assert [row["id"] for row in listed] == [made["id"]]
    assert listed[0]["reason"] == REASON and listed[0]["created_by_name"]


async def test_a_hold_created_after_the_override_is_plain_pending_and_still_refuses_issue(world: World):
    w = world
    base = await w.dossier(w.tree.asset)
    first = await w.gate(attachment_kind="node", attachment_id=w.tree.rsw)
    second = await w.gate(attachment_kind="node", attachment_id=w.tree.rsw)
    await w.override(base)
    later = await w.gate(attachment_kind="node", attachment_id=w.tree.rsw)

    quality = await w.check(base)
    assert quality["status"] == "fail" and quality["ready"] is False
    assert [f["reference"] for f in quality["findings"]] == [later["number"]]  # only the uncovered one is listed
    assert quality["counts"]["plain_pending_holds"] == 1 and quality["counts"]["overridden_pending_holds"] == 2
    refused = await w.client.post(f"{base}/issue", json={"purpose": "review"}, headers=w.headers)
    assert refused.status_code == 422 and later["number"] in refused.text
    assert first["number"] not in refused.text and second["number"] not in refused.text

    await w.release(later["id"])  # released instead of overridden
    assert (await w.check(base))["status"] == "overridden"
    await w.issue(base, 201)


async def test_a_second_override_covers_a_later_hold_and_a_third_finds_nothing_to_cover(world: World):
    w = world
    base = await w.dossier(w.tree.asset)
    await w.gate(attachment_kind="node", attachment_id=w.tree.rsw)
    first = await w.override(base)
    later = await w.gate(attachment_kind="node", attachment_id=w.tree.rsw)

    second = await w.override(base, reason="A further hold appeared")
    assert second["reference"] != first["reference"] and second["reference"].endswith("-OVR-02")
    assert second["gate_numbers"] == [later["number"]]
    assert (await w.check(base))["ready"] is True

    before = await w.stored()
    nothing = await w.override(base, 409)
    assert "Nothing blocks" in str(nothing)
    assert await w.stored() == before
    history = (await w.client.get(f"{base}/overrides")).json()
    assert [row["id"] for row in history] == [second["id"], first["id"]]  # newest first
    await w.issue(base, 201)


async def test_an_annotated_hold_can_still_be_released_and_the_check_then_passes(world: World):
    w = world
    base = await w.dossier(w.tree.asset)
    held = await w.gate(attachment_kind="node", attachment_id=w.tree.rsw)
    await w.override(base)

    await w.release(held["id"])
    released = (await w.gates())[held["number"]]
    assert released["status"] == "released" and released["override_ref"]  # the annotation stays as history
    assert (await w.check(base))["status"] == "pass"


# --- the documentation report never blocks ----------------------------------------------------------------


async def _ordinary_report(w: World, title: str) -> str:
    """An ordinary report on the default template, raised the way automation does (not committed, then committed)."""
    ncr = await create_ncr(w.db, project_id=w.project_id, title=title, raised_by_id=w.users["manager"]["id"], commit=False)
    code = ncr.code
    await w.db.commit()
    return code


async def test_the_override_report_is_open_documentation_classified_and_non_blocking(world: World):
    w = world
    base = await w.dossier(w.tree.asset)
    await w.gate(attachment_kind="node", attachment_id=w.tree.rsw)
    made = await w.override(base)

    report = await w.db.get(Ncr, made["report_id"])
    assert report is not None
    assert (report.category, report.status, report.issue_type) == ("documentation", "open", "ncr")
    assert (report.mdr_effect, report.completion_effect) == ("register_only", "none")
    assert report.source_data is not None and report.source_data["report_kind"] == "documentation"

    categories = (await w.client.get(f"/api/v1/issues/categories?project_id={w.project_id}")).json()
    assert next(c for c in categories if c["key"] == "documentation")["is_active"] is True

    # open and visible in the register, filterable by its category ...
    params = {"project_id": w.project_id, "category": "documentation", "open_only": True}
    listed = (await w.client.get("/api/v1/issues/", params=params)).json()["data"]
    assert [(i["code"], i["status"], i["mdr_effect"]) for i in listed] == [(made["report_code"], "open", "register_only")]
    # ... but the blocking list and the dossier's open-issues check ignore it
    blocking = (await w.client.get("/api/v1/issues/blocking", params={"project_id": w.project_id})).json()
    assert made["report_code"] not in [i["code"] for i in blocking]
    issues_row = await w.check(base, "issues_blocking")
    assert issues_row["status"] == "pass" and issues_row["findings"] == []
    assert issues_row["counts"]["open_reports"] == 1  # still counted as an open record of the override

    await w.issue(base, 201)  # the overridden dossier can be issued
    assert (await w.db.get(Ncr, made["report_id"])).status == "open"  # issuing does not close it


async def test_a_second_dossier_in_the_project_is_not_blocked_by_the_report(world: World):
    w = world
    first = await w.dossier(w.tree.asset)
    held = await w.gate(attachment_kind="node", attachment_id=w.tree.rsw)
    made = await w.override(first)

    second = await w.dossier()  # whole project: the project-level report is in its scope
    row = await w.check(second, "issues_blocking")
    assert row["status"] == "pass" and row["findings"] == []
    assert row["counts"]["open_reports"] == 0  # the report belongs to the first dossier's override only
    assert (await w.check(second))["status"] == "fail"  # the pending hold is not covered for this dossier

    await w.release(held["id"])
    assert (await w.check(second))["ready"] is True
    await w.issue(second, 201)
    assert (await w.db.get(Ncr, made["report_id"])).status == "open"


async def test_ordinary_blocking_reports_still_block_and_only_the_listed_ones_are_covered(world: World):
    w = world
    base = await w.dossier(w.tree.asset)
    await w.gate(attachment_kind="node", attachment_id=w.tree.rsw)
    earlier = await _ordinary_report(w, "Blocking report raised before the override")
    assert (await w.check(base, "issues_blocking"))["status"] == "fail"

    made = await w.override(base)
    assert earlier in [b["reference"] for b in made["blockers"]] and made["report_code"] not in [
        b["reference"] for b in made["blockers"]
    ]
    assert (await w.check(base, "issues_blocking"))["status"] == "overridden"
    stored = await w.db.scalar(select(Ncr).where(Ncr.project_id == w.project_id, Ncr.code == earlier))
    assert stored is not None and (stored.status, stored.mdr_effect) == ("open", "blocks")  # covered, not closed

    later = await _ordinary_report(w, "Blocking report raised after the override")
    row = await w.check(base, "issues_blocking")
    assert row["status"] == "fail" and [f["reference"] for f in row["findings"]] == [later]  # only the uncovered one
    refused = await w.client.post(f"{base}/issue", json={"purpose": "review"}, headers=w.headers)
    assert refused.status_code == 422 and later in refused.text
    assert made["report_code"] not in refused.text and earlier not in refused.text


# --- refusals: nothing is written ------------------------------------------------------------------------


async def test_refusals_leave_no_report_record_annotation_or_audit_entry(world: World):
    w = world
    base = await w.dossier(w.tree.asset)
    await w.gate(attachment_kind="node", attachment_id=w.tree.rsw)
    before = await w.stored()

    for reason in ("", "   ", None):  # an empty, blank or missing reason is a validation failure
        body = {"purpose": "review", **({} if reason is None else {"reason": reason})}
        refused = await w.client.post(f"{base}/override", json=body, headers=w.headers)
        assert refused.status_code == 422, refused.text
    bad = await w.client.post(
        f"{base}/override", json={"purpose": "review", "reason": REASON, "severity": "blocker"}, headers=w.headers
    )
    assert bad.status_code == 422

    await w.as_("staff")  # holds no override permission
    await w.override(base, 403)
    await w.as_("outsider")  # cannot see the project: the dossier is not found
    await w.override(base, 404)
    await w.as_("manager")

    final_only = await w.override(base, 422, purpose="final")  # a draft dossier cannot take a final issue
    assert "final" in str(final_only)
    assert await w.stored() == before

    dossier_id = int(base.rsplit("/", 1)[1])
    await w.db.execute(update(MdrDossier).where(MdrDossier.id == dossier_id).values(status="final"))
    await w.db.commit()
    await w.override(base, 422)  # already final: no review issue is possible
    await w.db.execute(update(MdrDossier).where(MdrDossier.id == dossier_id).values(status="draft"))
    await w.db.commit()
    assert await w.stored() == before


async def test_a_clear_dossier_is_a_conflict_and_raises_no_report(world: World):
    w = world
    base = await w.dossier(w.tree.asset)
    before = await w.stored()
    nothing = await w.override(base, 409)
    assert "Nothing blocks" in str(nothing)
    assert await w.stored() == before


@pytest.mark.parametrize("module", ["inspections", "ncr"])
async def test_a_covered_check_that_is_not_available_refuses_the_override(world: World, module: str):
    w = world
    base = await w.dossier(w.tree.asset)
    await w.gate(attachment_kind="node", attachment_id=w.tree.rsw)
    before = await w.stored()

    w.db.add(ModuleSetting(name=module, enabled=False))
    await w.db.commit()
    state.invalidate()
    refused = await w.override(base, 422)
    assert "not available" in str(refused)
    assert await w.stored() == before


async def test_a_failing_check_that_is_never_overridden_refuses_and_names_it(world: World):
    w = world
    pid = w.project_id
    base = await w.dossier(w.tree.asset)
    await w.gate(attachment_kind="node", attachment_id=w.tree.rsw)
    body = {"project_id": pid, "name": "Open check", "area": "qa_itp", "sections": ONE_CHECK}
    template = (await w.client.post(f"{API}/templates/", json=body, headers=w.headers)).json()
    made = await w.client.post(
        f"{API}/", json={"project_id": pid, "template_id": template["id"], "node_id": w.tree.rsw}, headers=w.headers
    )
    assert made.status_code == 201, made.text
    before = await w.stored()

    refused = await w.override(base, 422)
    assert "Every inspection in scope is complete" in str(refused)
    assert await w.stored() == before
    assert (await w.check(base, "inspections_complete"))["status"] == "fail"  # still failing, not overridden
    # The readiness answer says which checks can never be overridden, so the client can tell them apart.
    assert (await w.check(base, "inspections_complete"))["overridable"] is False
    assert (await w.check(base, "quality_gates"))["overridable"] is True


# --- one unit of work: a failure rolls everything back ----------------------------------------------------


@pytest.mark.parametrize(
    "target",
    ["src.modules.ncr.auto.raise_automatic", "src.modules.inspections.gates.annotate_pending"],
    ids=["report fails", "annotation fails after the report was raised"],
)
async def test_a_failure_while_raising_the_report_or_annotating_rolls_everything_back(
    world: World, monkeypatch: pytest.MonkeyPatch, target: str
):
    w = world
    base = await w.dossier(w.tree.asset)
    await w.gate(attachment_kind="node", attachment_id=w.tree.rsw)
    before = await w.stored()

    async def fail(*args: Any, **kwargs: Any) -> Any:
        raise ConflictException("injected failure")

    module, name = target.rsplit(".", 1)
    monkeypatch.setattr(__import__(module, fromlist=[name]), name, fail)
    refused = await w.override(base, 409)
    assert "injected failure" in str(refused)
    assert await w.stored() == before  # no orphan report, record, annotation or audit entry
    assert (await w.check(base))["status"] == "fail"
