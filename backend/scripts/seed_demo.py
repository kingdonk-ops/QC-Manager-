"""Demo data for local development: roles, a client team, a project with a CVR and a cashflow.

    uv run python -m scripts.seed_demo

Safe to run twice: anything that already exists is left alone. Never run it against production.
"""

import asyncio
from datetime import date
from decimal import Decimal

from sqlalchemy import select

from src.infrastructure.config.settings import EnvironmentOption, settings
from src.infrastructure.database.registry import import_models
from src.infrastructure.database.session import local_session
from src.modules.cvr.models import CashflowPeriod, CostHead
from src.modules.projects.models import Project
from src.modules.role.models import Role, RolePermission
from src.modules.team.models import EntraRoleMapping, Team

ROLES = {
    "Administrator": (
        "QC.Admin",
        [
            "team.read",
            "team.create",
            "team.update",
            "team.delete",
            "team.manage_members",
            "entra.manage",
            "portal.invite",
            "role.read",
            "role.create",
            "role.update",
            "role.assign",
            "projects.read",
            "projects.create",
            "projects.update",
            "projects.delete",
            "cvr.read",
            "cvr.edit",
        ],
    ),
    "Commercial": ("QC.Commercial", ["projects.read", "projects.create", "projects.update", "cvr.read", "cvr.edit"]),
    "Viewer": ("QC.Viewer", ["projects.read", "cvr.read", "team.read"]),
}

COST_HEADS = [
    ("01", "Preliminaries", 420_000, 168_400, 175_000, 418_000, 440_000),
    ("02", "Scaffolding & access", 310_000, 142_900, 131_500, 322_000, 318_000),
    ("03", "Insulation - pipework", 1_250_000, 512_300, 566_000, 1_212_000, 1_340_000),
    ("04", "Insulation - vessels & tanks", 860_000, 301_750, 292_000, 905_000, 880_000),
    ("05", "Cladding & jacketing", 540_000, 120_600, 141_200, 528_000, 572_000),
    ("06", "Refractory", 395_000, 64_200, 58_000, 401_000, 398_000),
    ("07", "Coatings", 228_000, 31_900, 40_500, 219_000, 236_000),
    ("08", "Plant & equipment", 185_000, 92_800, 88_000, 194_000, 186_000),
]


async def main() -> None:
    if settings.ENVIRONMENT == EnvironmentOption.PRODUCTION:
        raise SystemExit("Refusing to seed demo data into production.")
    import_models()

    async with local_session() as db:
        for name, (app_role, permissions) in ROLES.items():
            role = await db.scalar(select(Role).where(Role.name == name))
            if role is None:
                role = Role(name=name, description=f"Granted by the Entra app role {app_role}")
                db.add(role)
                await db.flush()
                db.add_all([RolePermission(role_id=role.id, permission_name=p) for p in permissions])
            if await db.get(EntraRoleMapping, app_role) is None:
                db.add(EntraRoleMapping(app_role_value=app_role, role_id=role.id))

        client = await db.scalar(select(Team).where(Team.name == "Client - Northwind Energy"))
        if client is None:
            client = Team(name="Client - Northwind Energy", description="Client portal users for Northwind")
            db.add(client)
            await db.flush()

        project = await db.scalar(select(Project).where(Project.code == "P-24017"))
        if project is None:
            project = Project(
                code="P-24017",
                name="LNG Train 3 Insulation",
                client_name="Northwind Energy",
                location="Karratha, WA",
                client_team_id=client.id,
            )
            db.add(project)
            await db.flush()
            for order, (code, desc, budget, cost, value, f_cost, f_value) in enumerate(COST_HEADS):
                db.add(
                    CostHead(
                        project_id=project.id,
                        code=code,
                        description=desc,
                        sort_order=order,
                        budget=Decimal(budget),
                        cost_to_date=Decimal(cost),
                        value_to_date=Decimal(value),
                        forecast_cost=Decimal(f_cost),
                        forecast_value=Decimal(f_value),
                    )
                )
            planned = [180, 260, 340, 420, 480, 520, 540, 520, 460, 380, 280, 170]
            for month, k in enumerate(planned):
                period = date(2026, 1 + month, 1)
                actual = month < 6
                db.add(
                    CashflowPeriod(
                        project_id=project.id,
                        period=period,
                        planned_cost=Decimal(k * 1000),
                        planned_value=Decimal(int(k * 1080)),
                        actual_cost=Decimal(int(k * 1000 * (1.04 if month % 2 else 0.97))) if actual else None,
                        actual_value=Decimal(int(k * 1080 * (1.02 if month % 3 else 0.95))) if actual else None,
                    )
                )

        await db.commit()
    print("Demo data is in place: roles, a client team, and project P-24017.")


if __name__ == "__main__":
    asyncio.run(main())
