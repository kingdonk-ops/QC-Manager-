"""Seeding a project from a P6 programme, with sample records tied to the RSWs it creates.

The programme is a small synthetic XER, never client data.
"""

from datetime import date, timedelta

import pytest
from crudauth import get_password_hash
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

import scripts.seed_p6_project as seed
from src.modules.asset_tree.models import AssetNode
from src.modules.inspections.models import ItpInstance
from src.modules.planner.models import WorkPlan
from src.modules.projects.models import Project
from src.modules.rfi.models import Rfi
from src.modules.scaffolds.models import Scaffold
from src.modules.tasks.models import Task
from src.modules.user.models import User
from tests.integration.modules.test_schedule_p6 import xer

pytestmark = [pytest.mark.asyncio, pytest.mark.usefixtures("through_the_test_database")]

MONDAY = date.today() - timedelta(days=date.today().weekday())


@pytest.fixture
def through_the_test_database(monkeypatch, db_session: AsyncSession):
    """The script opens its own session, which outside a test is the app's engine."""
    monkeypatch.setattr(
        seed, "local_session", async_sessionmaker(bind=db_session.bind, class_=AsyncSession, expire_on_commit=False)
    )


@pytest.fixture
async def admin(db_session: AsyncSession) -> User:
    user = User(
        name="Admin",
        username="admin",
        email="admin@example.com",
        hashed_password=get_password_hash("Unused-Pw1!"),
        is_superuser=True,
    )
    db_session.add(user)
    await db_session.commit()
    return user


@pytest.fixture
def programme(tmp_path, monkeypatch):
    """Activities named ``<asset> / <type> / <RSW>`` under SITE > SHUT, running this week and next."""
    offset = (MONDAY - date(2026, 3, 2)).days
    tasks = [
        {"code": f"A{n}", "name": f"CV-0{n % 3} / {kind} / {700 + n}", "shift": offset + n % 9}
        for n, kind in enumerate(["SCA Erect", "Insulation", "Cladding", "SCA Erect", "Insulation", "Cladding"] * 3)
    ]
    path = tmp_path / "programme.xer"
    path.write_bytes(xer(tasks))
    for name, value in {
        "SEED_DATA": "true",
        "SEED_P6_XER": str(path),
        "SEED_PROJECT_CODE": "P6-TEST",
        "SEED_P6_WBS_SITE_DEPTH": "1",
        "SEED_P6_WBS_AREA_DEPTH": "2",
        "ADMIN_USERNAME": "admin",
    }.items():
        monkeypatch.setenv(name, value)
    return path


async def _count(db: AsyncSession, model, project_id: int) -> int:
    return await db.scalar(select(func.count()).select_from(model).where(model.project_id == project_id)) or 0


async def test_it_imports_the_programme_and_adds_sample_records_once(db_session, admin, programme):
    await seed.main()
    project = await db_session.scalar(select(Project).where(Project.code == "P6-TEST"))
    assert project is not None

    rsws = await db_session.scalar(
        select(func.count()).select_from(AssetNode).where(AssetNode.project_id == project.id, AssetNode.level_key == "rsw")
    )
    first = {m.__name__: await _count(db_session, m, project.id) for m in (WorkPlan, Scaffold, Task, Rfi, ItpInstance)}
    assert rsws == 18
    assert first["WorkPlan"] == 2
    assert all(first.values()), first
    notes = (await db_session.scalars(select(Scaffold.notes).where(Scaffold.project_id == project.id))).all()
    assert all(n.startswith(seed.MARK) for n in notes)

    project_id = project.id
    await seed.main()
    again = {m.__name__: await _count(db_session, m, project_id) for m in (WorkPlan, Scaffold, Task, Rfi, ItpInstance)}
    assert again == first


async def test_without_a_programme_it_prepares_the_project_and_waits(db_session, admin, programme, monkeypatch):
    monkeypatch.setenv("SEED_P6_XER", str(programme.with_name("missing.xer")))

    await seed.main()

    project = await db_session.scalar(select(Project).where(Project.code == "P6-TEST"))
    assert project is not None
    assert await _count(db_session, Scaffold, project.id) == 0


async def test_it_does_nothing_unless_switched_on(db_session, admin, programme, monkeypatch):
    monkeypatch.setenv("SEED_DATA", "false")

    await seed.main()

    assert await db_session.scalar(select(func.count()).select_from(Project)) == 0
