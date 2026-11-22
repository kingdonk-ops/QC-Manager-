"""A small asset tree for quality and site-access tests: site / area / asset / two RSWs (work anchors)."""

from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from src.modules.asset_tree import service as tree
from src.modules.asset_tree.packs import apply_pack
from src.modules.projects.models import Project


@dataclass
class Tree:
    project: Project
    site: int
    area: int
    asset: int
    rsw: int
    rsw2: int


async def build_tree(db: AsyncSession, code: str = "SC-1") -> Tree:
    project = Project(code=code, name="Coal terminal")
    db.add(project)
    await db.flush()
    await apply_pack(db, project.id, "remediation-rsw")
    site = await tree.create_node(db, project.id, {"level_key": "site", "code": "KAR"})
    area = await tree.create_node(db, project.id, {"level_key": "area", "code": "A1", "parent_id": site.id})
    asset = await tree.create_node(db, project.id, {"level_key": "asset", "code": "101", "parent_id": area.id})
    rsw = await tree.create_node(db, project.id, {"level_key": "rsw", "code": "101.1", "parent_id": asset.id})
    rsw2 = await tree.create_node(db, project.id, {"level_key": "rsw", "code": "101.2", "parent_id": asset.id})
    await db.commit()
    return Tree(project, site.id, area.id, asset.id, rsw.id, rsw2.id)
