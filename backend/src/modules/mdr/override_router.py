"""Dossier issue override: record one and read the history. Included by the main MDR router."""

from typing import Annotated, Any

from fastapi import APIRouter, Path

from ...infrastructure.auth.authorization import require_permissions
from ...infrastructure.auth.deps import CurrentPermissionsDep, CurrentUserDep
from ...infrastructure.dependencies import AsyncSessionDep
from ..common.pagination import MAX_INTEGER_ID
from ..projects.service import readable_project
from . import override, service
from .models import MdrDossier, MdrOverride
from .override_schemas import OverrideIn, OverrideRead
from .permissions import MdrPermissionName as P

router = APIRouter(tags=["MDR / turnover dossiers"])

Id = Annotated[int, Path(ge=1, le=MAX_INTEGER_ID)]


async def _dossier(db: Any, dossier_id: int, user: dict[str, Any], held: frozenset[str], *, lock: bool = False) -> MdrDossier:
    """The dossier once the caller may see its project (a foreign project answers not-found). ``lock`` re-reads it under
    a row lock, so two overrides on one dossier run one after the other."""
    dossier = await service.get_dossier(db, dossier_id)
    await readable_project(db, dossier.project_id, user["id"], held)
    if lock:
        await db.refresh(dossier, with_for_update=True)
    return dossier


async def _reads(db: Any, rows: list[MdrOverride]) -> list[dict[str, Any]]:
    names = await service.user_names(db, {r.created_by_id for r in rows})
    out = []
    for row in rows:
        read = OverrideRead.model_validate(row).model_copy(update={"created_by_name": names.get(row.created_by_id or 0)})
        out.append(read.model_dump(mode="json"))
    return out


@router.post(
    "/dossiers/{dossier_id}/override",
    response_model=OverrideRead,
    status_code=201,
    summary="Override the Issue Gate",
    description="Lets the dossier issue past outstanding quality holds and open blocking issues. A reason is required. "
    "Raises a documentation non-conformance report listing the blockers and annotates the covered holds, which stay "
    "pending. Only the quality gate and open issues checks are covered (422 names any other failing check or an "
    "unavailable covered check); 409 when nothing blocks. Issue itself is unchanged.",
    dependencies=[require_permissions(P.OVERRIDE.value)],
)
async def record_override(
    dossier_id: Id, values: OverrideIn, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep
) -> Any:
    dossier = await _dossier(db, dossier_id, user, held, lock=True)
    made = await override.record_override(
        db, dossier, purpose=values.purpose.value, reason=values.reason, severity=values.severity, user_id=user["id"]
    )
    return (await _reads(db, [made]))[0]


@router.get(
    "/dossiers/{dossier_id}/overrides",
    response_model=list[OverrideRead],
    summary="Override History",
    description="Every override recorded for the dossier, newest first, with its reason, blockers and report.",
    dependencies=[require_permissions(P.READ.value)],
)
async def overrides(dossier_id: Id, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep) -> Any:
    dossier = await _dossier(db, dossier_id, user, held)
    return await _reads(db, await override.history(db, dossier))
