"""Dossiers: scope, collection through providers, compile, issue, sign, client decision. No FastAPI imports."""

import io
from datetime import UTC, datetime
from typing import Any

import anyio
from fastapi import UploadFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ...infrastructure.audit_ledger import record_audit
from ...infrastructure.config.settings import settings
from ...infrastructure.dossier import SECTIONS, MdrContext, MdrRecord, providers_for
from ...infrastructure.logging import get_logger
from ...infrastructure.modules.loader import enabled_modules
from ...infrastructure.modules.state import is_enabled
from ...infrastructure.records import record_transition
from ..asset_tree.models import AssetCollection, AssetCollectionMember, AssetNode
from ..asset_tree.service import subtree_ids
from ..common.exceptions import ResourceNotFoundError, ValidationError
from ..files.models import StoredFile
from ..files.storage import storage
from ..notifications.constants import Category
from ..notifications.service import notify
from ..projects.models import Project
from ..team.models import TeamMembership
from ..user.models import User
from . import compiler, signing
from .constants import (
    CAN_ISSUE,
    INTENT_STATEMENT,
    INTENT_VERSION,
    OUTPUT_ENTITY,
    DossierStatus,
    IssuePurpose,
    MdrDecision,
    RevisionKind,
    RevisionStatus,
    revision_label,
)
from .gate import ready, run_checks
from .models import MdrDossier, MdrRevision

logger = get_logger()
_loaded = False


class DossierNotFound(ResourceNotFoundError):
    public_detail = "Dossier not found."


class RevisionNotFound(ResourceNotFoundError):
    public_detail = "Dossier revision not found."


class MdrRuleError(ValidationError):
    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.public_detail = message  # type: ignore[misc]


class GateBlocked(MdrRuleError):
    def __init__(self, checks: list[dict[str, Any]]) -> None:
        failing = [c for c in checks if c["blocking"] and c["status"] == "fail"]
        lines = [f"{c['title']}: " + "; ".join(f["message"] for f in c["findings"][:5]) for c in failing]
        super().__init__("The dossier isn't ready to issue. " + " | ".join(lines))
        self.checks = checks


def ensure_loaded() -> None:
    """Import ``mdr.py`` of every module enabled at startup, once, so their providers and checks register."""
    global _loaded
    if _loaded:
        return
    for module in enabled_modules():
        try:
            module.submodule("mdr")
        except Exception:
            logger.exception("MDR provider failed to load", extra={"module_name": module.manifest.name})
    _loaded = True


def default_sections() -> list[dict[str, Any]]:
    return [{"key": k, "title": v, "enabled": True} for k, v in SECTIONS.items()]


def normalise_sections(sections: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    if sections is None:
        return default_sections()
    seen: set[str] = set()
    out = []
    for s in sections:
        if s["key"] not in SECTIONS:
            raise MdrRuleError(f"Unknown section '{s['key']}'")
        if s["key"] in seen:
            raise MdrRuleError(f"Section '{s['key']}' is listed twice")
        seen.add(s["key"])
        out.append(
            {"key": s["key"], "title": (s.get("title") or SECTIONS[s["key"]]).strip(), "enabled": bool(s.get("enabled", True))}
        )
    return out


async def check_scope(db: AsyncSession, project_id: int, node_ids: list[int], collection_ids: list[int]) -> None:
    if node_ids:
        found = set(
            (
                await db.execute(select(AssetNode.id).where(AssetNode.project_id == project_id, AssetNode.id.in_(node_ids)))
            ).scalars()
        )
        if missing := set(node_ids) - found:
            raise MdrRuleError(f"Asset nodes not in this project: {sorted(missing)}")
    if collection_ids:
        found = set(
            (
                await db.execute(
                    select(AssetCollection.id).where(
                        AssetCollection.project_id == project_id, AssetCollection.id.in_(collection_ids)
                    )
                )
            ).scalars()
        )
        if missing := set(collection_ids) - found:
            raise MdrRuleError(f"Collections not in this project: {sorted(missing)}")


async def get_dossier(db: AsyncSession, dossier_id: int) -> MdrDossier:
    dossier = await db.get(MdrDossier, dossier_id)
    if dossier is None:
        raise DossierNotFound(str(dossier_id))
    return dossier


async def scope_nodes(db: AsyncSession, dossier: MdrDossier) -> list[int] | None:
    """The scope's nodes with their subtrees and lineage, or ``None`` for the whole project."""
    roots = {int(n) for n in dossier.scope_node_ids}
    if dossier.scope_collection_ids:
        roots |= set(
            (
                await db.execute(
                    select(AssetCollectionMember.node_id).where(
                        AssetCollectionMember.collection_id.in_([int(c) for c in dossier.scope_collection_ids])
                    )
                )
            ).scalars()
        )
    elif not roots:
        return None
    ids: set[int] = set()
    for node_id in roots:
        try:
            ids |= set(await subtree_ids(db, node_id, with_lineage=True))
        except ResourceNotFoundError:
            continue
    return sorted(ids)


async def scope_labels(db: AsyncSession, dossier: MdrDossier) -> list[str]:
    labels = []
    if dossier.scope_node_ids:
        labels += [
            p or c
            for c, p in (
                await db.execute(select(AssetNode.code, AssetNode.display_path).where(AssetNode.id.in_(dossier.scope_node_ids)))
            ).tuples()
        ]
    if dossier.scope_collection_ids:
        labels += [
            f"{k} {c}"
            for k, c in (
                await db.execute(
                    select(AssetCollection.kind, AssetCollection.code).where(
                        AssetCollection.id.in_(dossier.scope_collection_ids)
                    )
                )
            ).tuples()
        ]
    return labels


async def context(db: AsyncSession, dossier: MdrDossier) -> MdrContext:
    project = await db.get(Project, dossier.project_id)
    assert project is not None
    return MdrContext(
        project_id=project.id,
        project_code=project.code,
        project_name=project.name,
        dossier_id=dossier.id,
        node_ids=await scope_nodes(db, dossier),
    )


async def _module_on(db: AsyncSession, module: str, project_id: int) -> bool:
    return module in {m.manifest.name for m in enabled_modules()} and await is_enabled(db, module, project_id)


async def catalogue(db: AsyncSession, project_id: int) -> list[dict[str, Any]]:
    ensure_loaded()
    out = []
    for key, title in SECTIONS.items():
        modules = sorted({p.module for p in providers_for(key) if await _module_on(db, p.module, project_id)})
        out.append({"key": key, "title": title, "providers": modules, "generated": key == "index"})
    return out


async def collect(db: AsyncSession, dossier: MdrDossier, ctx: MdrContext) -> list[compiler.SectionIn]:
    ensure_loaded()
    out = []
    number = 0
    for section in dossier.sections or default_sections():
        if not section.get("enabled", True) or section["key"] == "index":
            continue
        number += 1
        records: list[MdrRecord] = []
        notes: list[str] = []
        providers = [p for p in providers_for(section["key"]) if await _module_on(db, p.module, dossier.project_id)]
        for provider in providers:
            try:
                records += await provider.fn(db, ctx)
            except Exception:
                logger.exception("MDR provider failed", extra={"section": section["key"], "module_name": provider.module})
                notes.append(f"Not available: the {provider.module} module failed to provide its records.")
        if not providers:
            notes.append("Not available: no module provides this section.")
        out.append(compiler.SectionIn(section["key"], number, section["title"], records, " ".join(notes) or None))
    return out


async def _blobs(db: AsyncSession, sections: list[compiler.SectionIn]) -> dict[int, compiler.Blob]:
    ids = {fid for s in sections for r in s.records for fid in r.file_ids}
    if not ids:
        return {}
    out = {}
    store = storage()
    for f in (await db.execute(select(StoredFile).where(StoredFile.id.in_(ids)))).scalars():
        data = None
        if f.content_type == "application/pdf" or f.name.lower().endswith(".pdf"):
            try:
                data = await anyio.Path(store.path(f.storage_key)).read_bytes()
            except (OSError, ValueError):
                data = None
        out[f.id] = compiler.Blob(f.id, f.name, f.sha256, f.content_type, data)
    return out


async def _store(db: AsyncSession, dossier: MdrDossier, data: bytes, name: str, user_id: int) -> StoredFile:
    """Save output bytes as the next revision of the dossier's output file chain."""
    previous = await db.scalar(
        select(StoredFile).where(
            StoredFile.entity_type == OUTPUT_ENTITY, StoredFile.entity_id == dossier.id, StoredFile.is_latest.is_(True)
        )
    )
    key, size, digest = await storage().save(
        UploadFile(file=io.BytesIO(data), filename=name), max(len(data) + 1, settings.FILE_MAX_UPLOAD_MB * 1024 * 1024)
    )
    stored = StoredFile(
        name=name,
        content_type="application/pdf",
        size=size,
        sha256=digest,
        storage_key=key,
        uploaded_by_id=user_id,
        project_id=dossier.project_id,
        entity_type=OUTPUT_ENTITY,
        entity_id=dossier.id,
        category="report",
        tags=["mdr"],
        revision=previous.revision + 1 if previous else 1,
        supersedes_id=previous.id if previous else None,
    )
    if previous:
        previous.is_latest = False
    db.add(stored)
    await db.flush()
    return stored


async def _compile(
    db: AsyncSession, dossier: MdrDossier, *, revision: str | None, purpose: str, findings: list[str]
) -> compiler.Result:
    ctx = await context(db, dossier)
    sections = await collect(db, dossier, ctx)
    blobs = await _blobs(db, sections)
    label = f"{dossier.code} Rev {revision}" if revision else f"{dossier.code} DRAFT"
    scope = ", ".join(await scope_labels(db, dossier)) or "Whole project"
    cover = compiler.Cover(
        title=dossier.title,
        project=f"{ctx.project_code} {ctx.project_name}",
        code=dossier.code,
        revision=revision,
        purpose=purpose,
        scope=scope,
        date=datetime.now(UTC).strftime("%d %b %Y %H:%M UTC"),
        draft=revision is None,
        findings=findings,
    )
    return await anyio.to_thread.run_sync(compiler.compile_pdf, cover, sections, blobs, label)


def _findings_text(checks: list[dict[str, Any]]) -> list[str]:
    return [f"{c['title']}: {f['message']}" for c in checks if c["status"] == "fail" for f in c["findings"]]


async def gate(db: AsyncSession, dossier: MdrDossier, purpose: str | None) -> list[dict[str, Any]]:
    ensure_loaded()
    return await run_checks(db, await context(db, dossier), purpose)


async def compile_draft(db: AsyncSession, dossier: MdrDossier, user_id: int) -> MdrRevision:
    """Compile regardless of open findings (printed on the cover); keep only the latest draft."""
    checks = await gate(db, dossier, None)
    result = await _compile(db, dossier, revision=None, purpose="Draft for internal checking", findings=_findings_text(checks))
    stored = await _store(db, dossier, result.pdf, f"{dossier.code}-DRAFT.pdf", user_id)
    draft = await db.scalar(
        select(MdrRevision).where(MdrRevision.dossier_id == dossier.id, MdrRevision.kind == RevisionKind.DRAFT.value)
    )
    if draft is None:
        draft = MdrRevision(dossier_id=dossier.id, kind=RevisionKind.DRAFT.value)
        db.add(draft)
    draft.status = RevisionStatus.DRAFT.value
    draft.file_id, draft.sha256, draft.page_count = stored.id, stored.sha256, result.page_count
    draft.gate, draft.manifest, draft.compiled_by_id = checks, result.manifest, user_id
    await db.flush()
    return draft


async def issue(db: AsyncSession, dossier: MdrDossier, purpose: str, note: str | None, user_id: int) -> MdrRevision:
    """Run the gate, allocate the revision, compile and stamp. The revision then waits for its signature."""
    if dossier.status not in CAN_ISSUE[purpose]:
        raise MdrRuleError(
            f"A {purpose} revision can't be issued while the dossier is {dossier.status.replace('_', ' ')}."
            + (" The client must accept a review revision first." if purpose == IssuePurpose.FINAL else "")
        )
    pending = await db.scalar(
        select(MdrRevision.id).where(
            MdrRevision.dossier_id == dossier.id, MdrRevision.status == RevisionStatus.PENDING_SIGNATURE.value
        )
    )
    if pending:
        raise MdrRuleError("A revision is waiting for its signature: sign it before issuing another.")
    checks = await gate(db, dossier, purpose)
    if not ready(checks):
        raise GateBlocked(checks)
    kind = RevisionKind.REVIEW.value if purpose == IssuePurpose.REVIEW else RevisionKind.FINAL.value
    count = len(
        (await db.execute(select(MdrRevision.id).where(MdrRevision.dossier_id == dossier.id, MdrRevision.kind == kind))).all()
    )
    label = revision_label(kind, count)
    words = "Issued for client review" if kind == RevisionKind.REVIEW else "Final issue for turnover"
    result = await _compile(db, dossier, revision=label, purpose=words, findings=[])
    stored = await _store(db, dossier, result.pdf, f"{dossier.code}-Rev{label}-unsigned.pdf", user_id)
    revision = MdrRevision(
        dossier_id=dossier.id,
        kind=kind,
        revision=label,
        status=RevisionStatus.PENDING_SIGNATURE.value,
        file_id=stored.id,
        unsigned_file_id=stored.id,
        sha256=stored.sha256,
        page_count=result.page_count,
        gate=checks,
        manifest=result.manifest,
        note=note,
        compiled_by_id=user_id,
        issued_at=datetime.now(UTC),
    )
    db.add(revision)
    await db.flush()
    await record_audit(
        db,
        "mdr.revision.issued",
        "mdr_revision",
        revision.id,
        actor_id=user_id,
        project_id=dossier.project_id,
        summary=f"{dossier.code} Rev {label} compiled for {purpose} ({result.page_count} pages)",
        after={"dossier_id": dossier.id, "revision": label, "kind": kind, "content_sha256": stored.sha256},
    )
    return revision


async def get_revision(db: AsyncSession, revision_id: int) -> tuple[MdrRevision, MdrDossier]:
    revision = await db.get(MdrRevision, revision_id)
    if revision is None:
        raise RevisionNotFound(str(revision_id))
    return revision, await get_dossier(db, revision.dossier_id)


async def _client_users(db: AsyncSession, project_id: int) -> list[int]:
    project = await db.get(Project, project_id)
    if project is None or project.client_team_id is None:
        return []
    return list(
        (await db.execute(select(TeamMembership.user_id).where(TeamMembership.team_id == project.client_team_id))).scalars()
    )


async def sign(
    db: AsyncSession, revision: MdrRevision, dossier: MdrDossier, user: dict[str, Any], ip: str | None
) -> MdrRevision:
    """Stamp -> sign -> hash: append the attestation to the stamped file and store the SHA-256 of the final bytes."""
    if revision.status != RevisionStatus.PENDING_SIGNATURE.value:
        raise MdrRuleError("Only a revision waiting for its signature can be signed.")
    unsigned = await db.get(StoredFile, revision.unsigned_file_id) if revision.unsigned_file_id else None
    if unsigned is None:
        raise MdrRuleError("The compiled file is missing; issue the revision again.")
    stamped = await anyio.Path(storage().path(unsigned.storage_key)).read_bytes()
    now = datetime.now(UTC)
    attestation = {
        "signer_id": user["id"],
        "signer_name": user.get("name") or user.get("username") or str(user["id"]),
        "signer_email": user.get("email") or "",
        "authority": "mdr.sign",
        "signed_at": now.isoformat(timespec="seconds"),
        "intent_statement": INTENT_STATEMENT,
        "intent_version": INTENT_VERSION,
        "method": "attestation+sha256",
        "ip": ip,
        "content_sha256": unsigned.sha256,
    }
    label = f"{dossier.code} Rev {revision.revision}"
    final = await anyio.to_thread.run_sync(signing.attest, stamped, attestation, label)
    stored = await _store(db, dossier, final, f"{dossier.code}-Rev{revision.revision}.pdf", user["id"])
    assert stored.sha256 == signing.sha256(final)
    for older in (
        await db.execute(
            select(MdrRevision).where(
                MdrRevision.dossier_id == dossier.id,
                MdrRevision.id != revision.id,
                MdrRevision.status == RevisionStatus.ISSUED.value,
            )
        )
    ).scalars():
        older.status = RevisionStatus.SUPERSEDED.value
    revision.status = RevisionStatus.ISSUED.value
    revision.file_id, revision.sha256 = stored.id, stored.sha256
    revision.page_count = compiler.page_count(final)
    revision.signed_by_id, revision.signed_at, revision.signature = user["id"], now, attestation
    old_status = dossier.status
    dossier.status = DossierStatus.IN_REVIEW.value if revision.kind == RevisionKind.REVIEW else DossierStatus.FINAL.value
    dossier.current_revision = revision.revision
    await record_transition(
        db, "mdr_dossier", dossier.id, old_status, dossier.status, user["id"], f"Rev {revision.revision} signed"
    )
    await record_audit(
        db,
        "mdr.revision.signed",
        "mdr_revision",
        revision.id,
        actor_id=user["id"],
        project_id=dossier.project_id,
        summary=f"{label} signed; SHA-256 {stored.sha256}",
        before={"status": RevisionStatus.PENDING_SIGNATURE.value, "content_sha256": unsigned.sha256},
        after={"status": revision.status, "sha256": stored.sha256, "file_id": stored.id},
    )
    link = f"/mdr?project={dossier.project_id}&id={dossier.id}"
    if revision.kind == RevisionKind.REVIEW:
        await notify(
            db,
            await _client_users(db, dossier.project_id),
            Category.APPROVAL,
            f"{label} is ready for your review",
            body=dossier.title,
            link=link,
            entity=("mdr_dossier", dossier.id),
            actor_id=user["id"],
        )
    await notify(
        db,
        [i for i in (dossier.created_by_id, revision.compiled_by_id) if i],
        Category.STATUS,
        f"{label} signed",
        link=link,
        entity=("mdr_dossier", dossier.id),
        actor_id=user["id"],
    )
    return revision


async def decide(
    db: AsyncSession, revision: MdrRevision, dossier: MdrDossier, decision: str, note: str | None, user_id: int
) -> MdrRevision:
    """The client's acceptance or rejection of a signed review revision."""
    if revision.kind != RevisionKind.REVIEW or revision.status != RevisionStatus.ISSUED.value:
        raise MdrRuleError("Only the current signed review revision can be accepted or rejected.")
    accepted = decision == MdrDecision.ACCEPTED
    revision.status = RevisionStatus.ACCEPTED.value if accepted else RevisionStatus.REJECTED.value
    revision.decided_by_id, revision.decided_at, revision.decision_note = user_id, datetime.now(UTC), note
    old_status = dossier.status
    dossier.status = DossierStatus.ACCEPTED.value if accepted else DossierStatus.RETURNED.value
    await record_transition(db, "mdr_dossier", dossier.id, old_status, dossier.status, user_id, note)
    await record_audit(
        db,
        f"mdr.revision.{revision.status}",
        "mdr_revision",
        revision.id,
        actor_id=user_id,
        project_id=dossier.project_id,
        summary=f"{dossier.code} Rev {revision.revision} {revision.status} by the client" + (f": {note}" if note else ""),
        before={"status": RevisionStatus.ISSUED.value},
        after={"status": revision.status, "sha256": revision.sha256},
    )
    await notify(
        db,
        [i for i in (dossier.created_by_id, revision.compiled_by_id, revision.signed_by_id) if i],
        Category.APPROVAL,
        f"{dossier.code} Rev {revision.revision} {revision.status}",
        body=note,
        link=f"/mdr?project={dossier.project_id}&id={dossier.id}",
        entity=("mdr_dossier", dossier.id),
        actor_id=user_id,
    )
    return revision


async def verify_hash(db: AsyncSession, dossier: MdrDossier, sha: str) -> dict[str, Any]:
    """Whether a copy's SHA-256 (computed in the browser) matches a stored output of this dossier."""
    sha = sha.lower()
    stored = await db.scalar(
        select(StoredFile).where(
            StoredFile.entity_type == OUTPUT_ENTITY, StoredFile.entity_id == dossier.id, StoredFile.sha256 == sha
        )
    )
    if stored is None:
        return {"match": False}
    revision = await db.scalar(
        select(MdrRevision).where(
            MdrRevision.dossier_id == dossier.id,
            (MdrRevision.file_id == stored.id) | (MdrRevision.unsigned_file_id == stored.id),
        )
    )
    return {
        "match": True,
        "file_id": stored.id,
        "revision_id": revision.id if revision else None,
        "revision": revision.revision if revision else None,
        "kind": revision.kind if revision else None,
        "signed": bool(revision and revision.file_id == stored.id and revision.signed_at),
    }


async def user_names(db: AsyncSession, ids: set[int | None]) -> dict[int, str]:
    wanted = {i for i in ids if i}
    if not wanted:
        return {}
    return dict((await db.execute(select(User.id, User.name).where(User.id.in_(wanted)))).tuples().all())
