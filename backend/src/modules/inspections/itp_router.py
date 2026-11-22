"""ITP instances: an ITP template applied to an inspection-anchor node or an Item, with its lines' progress."""

from typing import Annotated, Any

from fastapi import APIRouter, Path, Query
from fastcrud import PaginatedListResponse, compute_offset, paginated_response
from sqlalchemy import or_, select

from ...infrastructure.auth.authorization import require_permissions
from ...infrastructure.auth.deps import CurrentPermissionsDep, CurrentUserDep
from ...infrastructure.dependencies import AsyncSessionDep
from ..common.pagination import MAX_INTEGER_ID, ItemsPerPageDep, PageDep
from ..projects.service import readable_project
from . import anchoring, itp, service
from .models import ItpInstance
from .permissions import InspectionPermissionName as P
from .quality_schemas import ItpInstanceCreate, ItpInstanceRead

router = APIRouter(prefix="/itp", tags=["Quality Inspections: ITP"])

Id = Annotated[int, Path(ge=1, le=MAX_INTEGER_ID)]
ProjectQuery = Annotated[int, Query(ge=1, le=MAX_INTEGER_ID)]


@router.get(
    "/instances/",
    response_model=PaginatedListResponse[ItpInstanceRead],
    summary="List ITP Instances",
    description="A project's applied ITPs with their progress (lines done / total) and open Hold points. `node_id` "
    "narrows to instances anchored on that node, below it, or on its Items.",
    dependencies=[require_permissions(P.READ.value)],
)
async def list_instances(
    db: AsyncSessionDep,
    user: CurrentUserDep,
    held: CurrentPermissionsDep,
    project_id: ProjectQuery,
    page: PageDep = 1,
    items_per_page: ItemsPerPageDep = 50,
    node_id: Annotated[int | None, Query(ge=1, le=MAX_INTEGER_ID)] = None,
    item_id: Annotated[int | None, Query(ge=1, le=MAX_INTEGER_ID)] = None,
    with_lines: bool = False,
) -> Any:
    await readable_project(db, project_id, user["id"], held)
    where: list[Any] = [ItpInstance.project_id == project_id]
    if node_id:
        await anchoring.tree.get_node(db, node_id, project_id)
        nodes, items = await anchoring.anchored_in(db, node_id)
        where.append(or_(ItpInstance.node_id.in_(nodes), ItpInstance.item_id.in_(items or [0])))
    if item_id:
        where.append(ItpInstance.item_id == item_id)
    total = await itp.count_instances(db, where)
    rows = (
        await db.execute(
            select(ItpInstance)
            .where(*where)
            .order_by(ItpInstance.id.desc())
            .offset(compute_offset(page, items_per_page))
            .limit(items_per_page)
        )
    ).scalars()
    data = [await itp.read_instance(db, i, with_lines=with_lines) for i in rows]
    return paginated_response(crud_data={"data": data, "total_count": total}, page=page, items_per_page=items_per_page)


@router.post(
    "/instances",
    response_model=ItpInstanceRead,
    status_code=201,
    summary="Apply an ITP to an Anchor",
    description="Validates the anchor (a node whose level has the `inspection_anchor` role, or an Item of the ITP's "
    "item type) and creates one `kind=itp` record per activity, in order, each with its intervention points and the "
    "checklist of its ITR form.",
    dependencies=[require_permissions(P.CREATE.value)],
)
async def create_instance(
    values: ItpInstanceCreate, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep
) -> Any:
    template = await service.get_template(db, values.template_id)
    await readable_project(db, template.project_id, user["id"], held)
    instance = await itp.instantiate(db, template, values.node_id, values.item_id, user["id"])
    return await itp.read_instance(db, instance)


@router.get(
    "/instances/{instance_id}",
    response_model=ItpInstanceRead,
    summary="An ITP Instance with its Lines",
    description="Each line: status, result, points per party, whether a Hold point before it blocks it, its witness "
    "status and its latest inspection request.",
    dependencies=[require_permissions(P.READ.value)],
)
async def get_instance(instance_id: Id, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep) -> Any:
    instance = await itp.get_instance(db, instance_id)
    await readable_project(db, instance.project_id, user["id"], held)
    return await itp.read_instance(db, instance)
