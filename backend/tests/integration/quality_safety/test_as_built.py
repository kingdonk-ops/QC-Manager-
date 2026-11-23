"""As-built records: survey, verify (with the automatic workmanship report) and the signed attestation, the edit and
delete rules, permissions, references, listing and the criteria holder rules."""

import re
from typing import Any

import pytest
import pytest_asyncio
from crudauth import get_password_hash
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.infrastructure.audit_ledger import AuditEntry
from src.infrastructure.modules import state
from src.modules.as_built import service
from src.modules.as_built.models import AsBuiltRecord
from src.modules.as_built.rules import attestation_digest, attestation_snapshot
from src.modules.inspections.models import AcceptanceCriterion
from src.modules.ncr.models import Ncr
from src.modules.ncr.templates import IssueRuleError
from src.modules.user.models import User
from tests.fixtures.accounts import reset_password_budget
from tests.integration.quality_safety.site_tree import Tree, build_tree
from tests.integration.rbac.test_user_permissions import _grant, _login

pytestmark = [pytest.mark.asyncio, pytest.mark.usefixtures("fresh_login_lockout")]

API = "/api/v1/as-built"
CRITERIA = "/api/v1/inspections/criteria"
EDITOR = ("projects.read", "asset_tree.read", *(f"as_built.{a}" for a in ("read", "create", "update")))
MANAGER = (
    *EDITOR,
    *(f"as_built.{a}" for a in ("delete", "review", "approve")),
    *(f"inspections.{a}" for a in ("read", "update", "delete")),
)
READER = ("projects.read", "as_built.read")
OUTSIDER = ("as_built.read",)
HEX64 = re.compile(r"[0-9a-f]{64}")


@pytest_asyncio.fixture(autouse=True)
async def fresh_switches():
    state.invalidate()
    yield


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
    await db.commit()
    await reset_password_budget(u.id)
    return {"id": u.id, "name": u.name, "username": username, "password": "Password123!"}


class World:
    def __init__(self, client: AsyncClient, db: AsyncSession, tree: Tree, users: dict[str, dict[str, Any]]):
        self.client, self.db, self.tree, self.users = client, db, tree, users
        self.project = tree.project
        self.headers: dict[str, str] = {}
        self.current: str | None = None

    async def as_(self, who: str) -> "World":
        if self.current != who:
            self.headers = {"X-CSRF-Token": await _login(self.client, self.users[who])}
            self.current = who
        return self

    async def criterion(
        self, code: str, rule: str = "range", lower: str | None = None, upper: str | None = None, project_id: int | None = None
    ) -> AcceptanceCriterion:
        c = AcceptanceCriterion(
            project_id=project_id or self.project.id,
            code=code,
            title=f"Title {code}",
            rule_type=rule,
            lower_limit=lower,
            upper_limit=upper,
        )
        self.db.add(c)
        await self.db.commit()
        return c

    async def record(self, expect: int = 201, **values: Any) -> dict[str, Any]:
        body = {"project_id": self.project.id, "title": "Slab level", **values}
        r = await self.client.post(f"{API}/", json=body, headers=self.headers)
        assert r.status_code == expect, r.text
        return r.json()

    async def act(self, record_id: int, action: str, body: dict[str, Any] | None = None, expect: int = 200) -> Any:
        r = await self.client.post(f"{API}/{record_id}/{action}", json=body or {}, headers=self.headers)
        assert r.status_code == expect, r.text
        return r.json()

    async def patch(self, record_id: int, body: dict[str, Any], expect: int = 200) -> Any:
        r = await self.client.patch(f"{API}/{record_id}", json=body, headers=self.headers)
        assert r.status_code == expect, r.text
        return r.json()

    async def delete(self, record_id: int, expect: int = 200) -> None:
        r = await self.client.delete(f"{API}/{record_id}", headers=self.headers)
        assert r.status_code == expect, r.text

    async def read(self, record_id: int, expect: int = 200) -> dict[str, Any]:
        r = await self.client.get(f"{API}/{record_id}")
        assert r.status_code == expect, r.text
        return r.json()

    async def listed(self, expect: int = 200, **params: Any) -> dict[str, Any]:
        r = await self.client.get(f"{API}/", params={"project_id": self.project.id, **params})
        assert r.status_code == expect, r.text
        return r.json()

    async def surveyed(self, criterion_id: int | None, value: str | None, **extra: Any) -> dict[str, Any]:
        made = await self.record(criterion_id=criterion_id, **extra)
        return await self.act(made["id"], "survey", {"measured_value": value} if value is not None else {})

    async def verified(self, criterion_id: int | None, value: str) -> dict[str, Any]:
        done = await self.surveyed(criterion_id, value)
        return await self.act(done["id"], "verify", {})

    async def ncr(self, ncr_id: int) -> Ncr:
        found = await self.db.scalar(select(Ncr).where(Ncr.id == ncr_id).execution_options(populate_existing=True))
        assert found is not None
        return found

    async def report_count(self) -> int:
        return await self.db.scalar(select(func.count()).select_from(Ncr).where(Ncr.project_id == self.project.id)) or 0

    async def stored(self, record_id: int) -> AsBuiltRecord:
        found = await self.db.scalar(
            select(AsBuiltRecord).where(AsBuiltRecord.id == record_id).execution_options(populate_existing=True)
        )
        assert found is not None
        return found


@pytest_asyncio.fixture
async def world(client: AsyncClient, db_session: AsyncSession, test_user: dict, test_user_2: dict) -> World:
    tree = await build_tree(db_session, "AB-1")
    await _grant(db_session, test_user["id"], "as_built_editor", *EDITOR)
    await _grant(db_session, test_user_2["id"], "as_built_manager", *MANAGER)
    reader = await _user(db_session, "asbuiltreader")
    await _grant(db_session, reader["id"], "as_built_reader", *READER)
    outsider = await _user(db_session, "asbuiltoutsider")
    await _grant(db_session, outsider["id"], "as_built_outsider", *OUTSIDER)
    users = {"editor": test_user, "manager": test_user_2, "reader": reader, "outsider": outsider}
    return await World(client, db_session, tree, users).as_("editor")


# --- survey ----------------------------------------------------------------------------------------------


async def test_a_survey_judges_the_value_against_a_minimum_criterion_and_raises_nothing(world: World):
    w = world
    crit = await w.criterion("MIN-355", "minimum", lower="355")
    results = []
    for value in ("360", "355", "320"):
        made = await w.record(criterion_id=crit.id)
        assert made["status"] == "draft" and made["tolerance_result"] == "not_assessed" and made["surveyed_by_id"] is None
        done = await w.act(made["id"], "survey", {"measured_value": value})
        assert (done["status"], done["measured_value"]) == ("surveyed", value)
        assert done["surveyed_by_id"] == w.users["editor"]["id"] and done["report_id"] is None
        results.append(done["tolerance_result"])
    assert results == ["within", "within", "out_of_tolerance"]
    assert await w.report_count() == 0


async def test_a_range_criterion_is_inclusive_and_a_value_with_a_unit_is_not_assessed(world: World):
    w = world
    crit = await w.criterion("RNG-10-20", "range", lower="10", upper="20")
    cases = [
        ("10", "within"),
        ("20", "within"),
        ("9.99", "out_of_tolerance"),
        ("20.01", "out_of_tolerance"),
        ("15 mm", "not_assessed"),
    ]
    for value, expected in cases:
        assert (await w.surveyed(crit.id, value))["tolerance_result"] == expected, value
    negative = await w.criterion("RNG-NEG", "range", lower="-2.5", upper="2.5")
    assert (await w.surveyed(negative.id, "-1.25"))["tolerance_result"] == "within"
    assert (await w.surveyed(negative.id, "-3"))["tolerance_result"] == "out_of_tolerance"
    maximum = await w.criterion("MAX-50", "maximum", upper="50")
    assert [(await w.surveyed(maximum.id, v))["tolerance_result"] for v in ("50", "60")] == ["within", "out_of_tolerance"]


async def test_a_survey_without_a_value_judges_the_stored_one_and_can_be_repeated_while_surveyed(world: World):
    w = world
    crit = await w.criterion("REP-1", "maximum", upper="10")
    made = await w.record(criterion_id=crit.id, measured_value="12", surveyed_by_id=w.users["manager"]["id"])
    first = await w.act(made["id"], "survey", {})
    assert first["tolerance_result"] == "out_of_tolerance" and first["surveyed_by_id"] == w.users["manager"]["id"]
    again = await w.act(made["id"], "survey", {"measured_value": "9", "deviation_value": "1", "notes": "Re-shot"})
    assert (again["status"], again["tolerance_result"], again["deviation_value"], again["notes"]) == (
        "surveyed",
        "within",
        "1",
        "Re-shot",
    )


async def test_what_cannot_be_decided_is_not_assessed_and_verifying_it_raises_no_report(world: World):
    w = world
    free = await w.criterion("FREE-1", "free_text")
    open_min = await w.criterion("MIN-OPEN", "minimum")
    numeric = await w.criterion("NUM-1", "range", lower="10", upper="20")
    cases = [(None, "10"), (free.id, "10"), (open_min.id, "10"), (numeric.id, "abc")]
    done = [await w.surveyed(criterion_id, value) for criterion_id, value in cases]
    assert [d["tolerance_result"] for d in done] == ["not_assessed"] * 4
    await w.as_("manager")
    for d in done:
        verified = await w.act(d["id"], "verify", {})
        assert verified["status"] == "verified" and verified["report_id"] is None and verified["legal_record"] is False
    assert await w.report_count() == 0


async def test_a_survey_needs_a_draft_or_surveyed_record(world: World):
    w = world
    done = await w.surveyed(None, "1")
    await w.as_("manager")
    await w.act(done["id"], "verify", {})
    refused = await w.act(done["id"], "survey", {}, expect=422)
    assert "verified" in str(refused)
    assert (await w.read(done["id"]))["status"] == "verified"


# --- verify ----------------------------------------------------------------------------------------------


async def test_verifying_an_out_of_tolerance_record_raises_a_workmanship_report_that_quotes_it(world: World):
    w = world
    crit = await w.criterion("MIN-355", "minimum", lower="355")
    made = await w.record(
        criterion_id=crit.id,
        capture_method="laser_scan",
        instrument="Scanner S1",
        accuracy_class="survey",
        accuracy_value="2",
        accuracy_unit="mm",
        deviation_value="35",
    )
    await w.act(made["id"], "survey", {"measured_value": "320"})
    await w.as_("manager")
    done = await w.act(made["id"], "verify", {"severity": "minor", "notes": "Re-measure after grouting"})
    assert (done["status"], done["legal_record"], done["verifier_notes"]) == ("verified", False, "Re-measure after grouting")
    report = await w.ncr(done["report_id"])
    assert (report.severity, report.status, report.issue_type, report.source) == ("minor", "open", "ncr", "as_built")
    assert report.source_reference == made["number"] == "ASB-001" and report.inspection_id is None
    text = report.description or ""
    for expected in (
        "Raised automatically from as-built record ASB-001.",
        "Slab level",
        "Capture method: laser scan.",
        "Instrument: Scanner S1.",
        "Accuracy class: survey, value 2 mm.",
        "Deviation value: 35.",
        "Verifier notes: Re-measure after grouting",
        "MIN-355",
        "inclusive lower bound 355",
        "Measured value: 320.",
    ):
        assert expected in text, expected
    data = report.source_data or {}
    assert (data["report_kind"], data["outcome"], data["criterion_id"], data["record_number"]) == (
        "workmanship",
        "out_of_tolerance",
        crit.id,
        "ASB-001",
    )
    entry = await w.db.scalar(
        select(AuditEntry).where(AuditEntry.action == "as_built.record.verified", AuditEntry.entity_id == str(made["id"]))
    )
    assert entry is not None and entry.after["report_id"] == done["report_id"]


async def test_the_report_severity_defaults_to_major_and_a_conforming_record_raises_none(world: World):
    w = world
    crit = await w.criterion("RNG-1", "range", lower="10", upper="20")
    out = await w.surveyed(crit.id, "25")
    inside = await w.surveyed(crit.id, "15")
    await w.as_("manager")
    flagged = await w.act(out["id"], "verify", {})
    assert (await w.ncr(flagged["report_id"])).severity == "major"
    assert (await w.act(inside["id"], "verify", {}))["report_id"] is None
    assert await w.report_count() == 1
    await w.act(out["id"], "verify", {}, expect=422)  # already verified: no second report
    assert await w.report_count() == 1
    await w.act((await w.surveyed(crit.id, "30"))["id"], "verify", {"severity": "observation"}, expect=422)


async def test_a_draft_cannot_be_verified_and_the_refusal_says_to_survey_first(world: World):
    w = world
    made = await w.record()
    await w.as_("manager")
    refused = await w.act(made["id"], "verify", {}, expect=422)
    assert "draft" in str(refused) and "survey" in str(refused)
    assert (await w.read(made["id"]))["status"] == "draft"


async def test_if_the_report_cannot_be_created_the_verification_fails_and_nothing_is_stored(
    world: World, monkeypatch: pytest.MonkeyPatch
):
    w = world
    crit = await w.criterion("RB-1", "maximum", upper="10")
    done = await w.surveyed(crit.id, "12")

    async def refuse(*args: Any, **kwargs: Any) -> Ncr:
        raise IssueRuleError("There is no ncr template for this category.")

    monkeypatch.setattr(service, "raise_automatic", refuse)
    await w.as_("manager")
    await w.act(done["id"], "verify", {"notes": "Should not stick"}, expect=422)
    after = await w.read(done["id"])
    assert (after["status"], after["report_id"], after["verifier_notes"]) == ("surveyed", None, None)
    assert await w.report_count() == 0
    entry = await w.db.scalar(select(AuditEntry).where(AuditEntry.action == "as_built.record.verified"))
    assert entry is None


# --- sign ------------------------------------------------------------------------------------------------


async def test_signing_as_valid_records_the_record_with_a_digest_and_locks_it(world: World):
    w = world
    await w.as_("manager")
    crit = await w.criterion("MAX-50", "maximum", upper="50")
    made = await w.verified(crit.id, "40")
    assert made["legal_record"] is False and made["signed_digest"] is None  # verification never sets the flag
    signed = await w.act(made["id"], "sign", {"notes": "Checked on site"})
    manager_id = w.users["manager"]["id"]
    assert (signed["status"], signed["legal_record"], signed["signed_by_id"]) == ("recorded", True, manager_id)
    assert signed["signed_at"] and signed["signed_ip"] and signed["signature_notes"] == "Checked on site"
    expected = attestation_digest(attestation_snapshot(await w.stored(made["id"]), valid=True, signer_id=manager_id))
    assert HEX64.fullmatch(signed["signed_digest"]) and signed["signed_digest"] == expected
    entry = await w.db.scalar(
        select(AuditEntry).where(AuditEntry.action == "as_built.record.signed", AuditEntry.entity_id == str(made["id"]))
    )
    assert entry is not None and entry.after["digest"] == expected

    refused = await w.patch(made["id"], {"title": "Edited"}, expect=422)
    assert "recorded" in str(refused)
    await w.delete(made["id"], expect=409)
    await w.act(made["id"], "sign", {}, expect=422)


async def test_declining_the_attestation_keeps_the_record_verified_and_the_flag_false(world: World):
    w = world
    await w.as_("manager")
    made = await w.verified(None, "1")
    declined = await w.act(made["id"], "sign", {"valid": False, "notes": "Wrong level"})
    assert (declined["status"], declined["legal_record"], declined["signature_notes"]) == ("verified", False, "Wrong level")
    assert HEX64.fullmatch(declined["signed_digest"]) and declined["signed_by_id"] == w.users["manager"]["id"]
    valid_digest = attestation_digest(
        attestation_snapshot(await w.stored(made["id"]), valid=True, signer_id=w.users["manager"]["id"])
    )
    assert declined["signed_digest"] != valid_digest  # the validity decision is part of what is signed
    assert (await w.act(made["id"], "sign", {}))["status"] == "recorded"


async def test_signing_needs_a_verified_record(world: World):
    w = world
    draft = await w.record()
    surveyed = await w.surveyed(None, "1")
    await w.as_("manager")
    for record_id, state_name in ((draft["id"], "draft"), (surveyed["id"], "surveyed")):
        refused = await w.act(record_id, "sign", {}, expect=422)
        assert state_name in str(refused) and "verified" in str(refused)
        assert (await w.read(record_id))["legal_record"] is False


# --- edits, supersede, delete ------------------------------------------------------------------------------


async def test_an_ordinary_edit_cannot_set_surveyed_verified_or_recorded(world: World):
    w = world
    made = await w.record(measured_value="12")
    for target in ("surveyed", "verified", "recorded"):
        refused = await w.patch(made["id"], {"status": target}, expect=409)
        assert "action" in str(refused)
    assert (await w.read(made["id"]))["status"] == "draft"


async def test_a_draft_edits_freely_and_a_surveyed_value_and_criterion_change_only_by_a_new_survey(world: World):
    w = world
    crit = await w.criterion("RNG-E", "range", lower="10", upper="20")
    other = await w.criterion("RNG-F", "range", lower="1", upper="2")
    made = await w.record(criterion_id=crit.id, measured_value="12")
    edited = await w.patch(made["id"], {"measured_value": "15", "title": "Slab level B", "criterion_id": other.id})
    assert (edited["measured_value"], edited["criterion_id"], edited["tolerance_result"]) == ("15", other.id, "not_assessed")
    await w.patch(made["id"], {"criterion_id": crit.id})
    assert (await w.act(made["id"], "survey", {}))["tolerance_result"] == "within"

    refused = await w.patch(made["id"], {"measured_value": "18"}, expect=409)
    assert "survey" in str(refused)
    await w.patch(made["id"], {"criterion_id": other.id}, expect=409)
    same = await w.patch(made["id"], {"measured_value": "15", "criterion_id": crit.id, "title": "Edge"})
    assert (same["title"], same["measured_value"], same["status"]) == ("Edge", "15", "surveyed")
    assert (await w.act(made["id"], "survey", {"measured_value": "25"}))["tolerance_result"] == "out_of_tolerance"


async def test_a_verified_record_is_superseded_not_rewritten_or_deleted(world: World):
    w = world
    await w.as_("manager")
    made = await w.verified(None, "1")
    await w.patch(made["id"], {"title": "Edited"}, expect=409)
    await w.patch(made["id"], {"status": "void"}, expect=422)
    await w.patch(made["id"], {"status": "draft"}, expect=422)
    await w.delete(made["id"], expect=409)
    superseded = await w.patch(made["id"], {"status": "superseded"})
    assert superseded["status"] == "superseded"
    await w.patch(made["id"], {"title": "Edited"}, expect=409)
    await w.patch(made["id"], {"status": "void"}, expect=422)
    await w.delete(made["id"], expect=409)
    entry = await w.db.scalar(
        select(AuditEntry).where(AuditEntry.action == "as_built.record.superseded", AuditEntry.entity_id == str(made["id"]))
    )
    assert entry is not None


async def test_an_unjudged_record_can_be_voided_then_it_is_locked_but_can_be_deleted(world: World):
    w = world
    made = await w.record()
    assert (await w.patch(made["id"], {"status": "void"}))["status"] == "void"
    await w.patch(made["id"], {"title": "Edited"}, expect=422)
    await w.act(made["id"], "survey", {}, expect=422)
    await w.as_("manager")
    await w.delete(made["id"])
    await w.read(made["id"], expect=404)


async def test_a_draft_and_a_surveyed_record_can_be_deleted_by_a_manager_only(world: World):
    w = world
    draft = await w.record()
    surveyed = await w.surveyed(None, "1")
    await w.delete(draft["id"], expect=403)
    await w.as_("manager")
    await w.delete(draft["id"])
    await w.delete(surveyed["id"])
    assert (await w.listed())["total_count"] == 0


# --- permissions, references -------------------------------------------------------------------------------


async def test_permissions_separate_editing_reviewing_and_signing(world: World):
    w = world
    made = await w.record()
    await w.act(made["id"], "survey", {"measured_value": "1"})
    await w.act(made["id"], "verify", {}, expect=403)
    await w.act(made["id"], "sign", {}, expect=403)
    await w.as_("reader")
    await w.record(expect=403)
    await w.act(made["id"], "survey", {}, expect=403)
    assert (await w.read(made["id"]))["status"] == "surveyed"
    assert (await w.listed())["total_count"] == 1
    await w.as_("outsider")
    await w.read(made["id"], expect=404)
    await w.listed(expect=404)


async def test_foreign_and_missing_references_answer_not_found(world: World, db_session: AsyncSession):
    w = world
    other = await build_tree(db_session, "AB-2")
    foreign = await w.criterion("F-1", project_id=other.project.id)
    await w.record(expect=404, criterion_id=foreign.id)
    await w.record(expect=404, criterion_id=999999)
    await w.record(expect=404, node_id=other.rsw)
    await w.record(expect=404, item_id=999999)
    made = await w.record(node_id=w.tree.rsw)
    assert made["node_id"] == w.tree.rsw
    await w.patch(made["id"], {"criterion_id": foreign.id}, expect=404)
    await w.patch(made["id"], {"node_id": other.rsw}, expect=404)
    assert (await w.read(made["id"]))["criterion_id"] is None


# --- numbering, listing, criteria holder ---------------------------------------------------------------------


async def test_records_are_numbered_per_project_and_listed_newest_first_with_filters(world: World):
    w = world
    crit = await w.criterion("LST-1", "maximum", upper="10")
    first = await w.record(criterion_id=crit.id)
    second = await w.surveyed(crit.id, "12")
    third = await w.surveyed(crit.id, "5")
    assert (first["number"], second["number"], third["number"]) == ("ASB-001", "ASB-002", "ASB-003")
    listed = await w.listed()
    assert [r["id"] for r in listed["data"]] == [third["id"], second["id"], first["id"]] and listed["total_count"] == 3
    assert [r["id"] for r in (await w.listed(status="draft"))["data"]] == [first["id"]]
    out = await w.listed(status="surveyed", tolerance_result="out_of_tolerance")
    assert [r["id"] for r in out["data"]] == [second["id"]] and out["total_count"] == 1
    paged = await w.listed(items_per_page=1, page=2)
    assert [r["id"] for r in paged["data"]] == [second["id"]] and paged["total_count"] == 3


async def test_a_criterion_judged_by_an_as_built_record_is_frozen_and_not_deleted(world: World):
    w = world
    crit = await w.criterion("HLD-1", "range", lower="10", upper="20")
    await w.record(criterion_id=crit.id)
    await w.as_("manager")
    url = f"{CRITERIA}/{crit.id}"
    frozen = await w.client.patch(url, json={"upper_limit": "25"}, headers=w.headers)
    assert frozen.status_code == 409 and "judged" in frozen.text
    assert (await w.client.patch(url, json={"title": "Renamed"}, headers=w.headers)).status_code == 200
    refused = await w.client.delete(url, headers=w.headers)
    assert refused.status_code == 409 and "as-built records" in refused.text
