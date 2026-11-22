"""Client co-sign (KERP TD-219 and TD-592, without device keys or PINs).

- ``portal``: the client signs in their own account (holding ``inspections.respond``): a full co-signature.
- ``on_device``: the client draws a signature on the inspector's device; the inspector names the client's
  account. Provisional until that client confirms in their own account.
- ``scan``: a page the client signed on paper, scanned and attached to the record; same terms as on-device.

A rejection needs a reason and returns a submitted record. While a co-sign is provisional, a record whose
template requires the client's signature can't be approved.
"""

from datetime import UTC, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from ...infrastructure.http_exceptions import ConflictException, ForbiddenException, UnprocessableEntityException
from ...infrastructure.records import record_transition
from ..files.models import StoredFile
from ..notifications.constants import Category
from ..notifications.service import notify
from ..user.models import User
from . import signing
from .constants import CosignMode, InspectionStatus, SignatureRole, SignatureStatus
from .models import Inspection, InspectionSignature
from .permissions import InspectionPermissionName as P
from .service import ENTITY, InspectionNotFoundError, link_of

COSIGNABLE = (
    InspectionStatus.IN_PROGRESS,
    InspectionStatus.REQUESTED,
    InspectionStatus.RETURNED,
    InspectionStatus.SUBMITTED,
)


async def cosign(
    db: AsyncSession, inspection: Inspection, body: dict[str, Any], user: dict[str, Any], held: frozenset[str]
) -> InspectionSignature:
    if inspection.status not in COSIGNABLE:
        raise UnprocessableEntityException(f"A {inspection.status.replace('_', ' ')} record isn't co-signed.")
    if await signing.live_signature(db, inspection, SignatureRole.INSPECTOR) is None:
        raise UnprocessableEntityException("INSPECTOR_SIGNATURE_MISSING: the inspector signs first.")
    if await signing.live_signature(db, inspection, SignatureRole.CLIENT):
        raise ConflictException("This version already carries a client co-signature.")
    mode = str(body["mode"])
    if mode == CosignMode.PORTAL:
        if P.RESPOND not in held:
            raise ForbiddenException("Only the client co-signs in their own account.")
        if user["id"] in (inspection.inspector_id, inspection.submitted_by_id):
            raise ForbiddenException("The inspector can't co-sign for the client.")
        sig = await signing.sign(db, inspection, SignatureRole.CLIENT, user["id"], held=held, mode=mode)
    else:
        client = await db.get(User, body["client_user_id"])
        if client is None or client.is_deleted:
            raise UnprocessableEntityException("That client account doesn't exist.")
        if client.id == user["id"]:
            raise UnprocessableEntityException("Name the client's own account, not yours.")
        if mode == CosignMode.SCAN:
            scan = await db.get(StoredFile, body["scan_file_id"])
            if scan is None or scan.entity_type != ENTITY or scan.entity_id != inspection.id:
                raise UnprocessableEntityException("Upload the scan to this inspection first.")
        sig = await signing.sign(
            db,
            inspection,
            SignatureRole.CLIENT,
            client.id,
            status=SignatureStatus.PROVISIONAL,
            mode=mode,
            recorded_by_id=user["id"],
            signature_image=body.get("signature_image"),
            scan_file_id=body.get("scan_file_id"),
            signer_name_stated=body.get("signer_name"),
        )
        kind = "drawn" if mode == CosignMode.ON_DEVICE else "scanned paper"
        await notify(
            db,
            [client.id],
            Category.APPROVAL,
            f"Confirm your signature on {inspection.code}",
            body=f"{inspection.title}: a {kind} signature was recorded in your name. Confirm or reject it.",
            link=link_of(inspection),
            entity=(ENTITY, inspection.id),
            actor_id=user["id"],
        )
    await db.commit()
    return sig


async def decide(
    db: AsyncSession, inspection: Inspection, signature_id: int, body: dict[str, Any], user: dict[str, Any]
) -> None:
    """The named client confirms a provisional co-sign in their own account, or rejects it."""
    sig = await db.get(InspectionSignature, signature_id)
    if sig is None or sig.inspection_id != inspection.id or sig.role != SignatureRole.CLIENT:
        raise InspectionNotFoundError("No such co-signature")
    if sig.signer_user_id != user["id"]:
        raise ForbiddenException("Only the client named on the signature confirms or rejects it.")
    if sig.status != SignatureStatus.PROVISIONAL:
        raise UnprocessableEntityException(f"The co-signature is {sig.status}.")
    if body["decision"] == "confirm":
        sig.status = SignatureStatus.VALID.value
        sig.confirmed_at = datetime.now(UTC)
        sig.intent_text = signing.intent_text(SignatureRole.CLIENT, user.get("name"), inspection.code)
        title = f"{inspection.code}: client confirmed the co-signature"
    else:
        sig.status = SignatureStatus.REJECTED.value
        sig.rejected_reason = body["reason"]
        if inspection.status == InspectionStatus.SUBMITTED:
            reason = f"Client rejected the co-signature: {body['reason']}"
            await record_transition(db, ENTITY, inspection.id, inspection.status, InspectionStatus.RETURNED, user["id"], reason)
            inspection.status = InspectionStatus.RETURNED.value
            inspection.return_reason = reason
        title = f"{inspection.code}: client rejected the co-signature"
    await notify(
        db,
        [u for u in (sig.recorded_by_id, inspection.inspector_id) if u],
        Category.STATUS,
        title,
        body=body.get("reason"),
        link=link_of(inspection),
        entity=(ENTITY, inspection.id),
        actor_id=user["id"],
    )
    await db.commit()
