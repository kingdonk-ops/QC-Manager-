"""Scheduled reports: when each is next due, and generating and emailing one."""

import calendar
from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ...infrastructure.auth.authorization import load_permissions
from ...infrastructure.logging import get_logger
from ...infrastructure.mail import Attachment, Mail, deliver
from ...infrastructure.modules.state import is_enabled
from ..projects.models import Project
from ..user.models import User
from .builder import build_report
from .models import ReportRun, ReportSchedule, ReportTemplate
from .schemas import TemplateRead
from .service import Viewer

logger = get_logger()


def _matches(day: date, cadence: str, weekday: int | None, day_of_month: int | None) -> bool:
    if cadence == "daily":
        return True
    if cadence == "weekly":
        return day.weekday() == (weekday or 0)
    last = calendar.monthrange(day.year, day.month)[1]
    return day.day == min(day_of_month or 1, last)


def next_run(
    cadence: str,
    time_of_day: str,
    timezone: str,
    after: datetime,
    *,
    weekday: int | None = None,
    day_of_month: int | None = None,
) -> datetime:
    """The first moment strictly after ``after`` that the schedule is due, in UTC.

    Times are wall-clock times in ``timezone``, so a 07:00 report stays at 07:00 across daylight saving.
    A monthly schedule on a day the month doesn't have (31 in April) runs on the month's last day.
    """
    zone = ZoneInfo(timezone)
    hour, minute = (int(x) for x in time_of_day.split(":"))
    local = after.astimezone(zone)
    for offset in range(0, 400):
        day = local.date() + timedelta(days=offset)
        if not _matches(day, cadence, weekday, day_of_month):
            continue
        candidate = datetime.combine(day, time(hour, minute), tzinfo=zone)
        if candidate > after:
            return candidate.astimezone(UTC)
    raise ValueError("No run date within a year")


def schedule_next(schedule: ReportSchedule, after: datetime) -> datetime:
    return next_run(
        schedule.cadence,
        schedule.time_of_day,
        schedule.timezone,
        after,
        weekday=schedule.weekday,
        day_of_month=schedule.day_of_month,
    )


async def recipients_of(db: AsyncSession, schedule: ReportSchedule) -> list[str]:
    emails = set(schedule.recipient_emails or [])
    if schedule.recipient_user_ids:
        emails |= set(
            (
                await db.execute(select(User.email).where(User.id.in_(schedule.recipient_user_ids), User.is_deleted.is_(False)))
            ).scalars()
        )
    return sorted(e for e in emails if e)


async def owner_viewer(db: AsyncSession, schedule: ReportSchedule) -> Viewer | None:
    owner = await db.get(User, schedule.created_by_id) if schedule.created_by_id else None
    if owner is None or owner.is_deleted:
        return None
    held = await load_permissions(db, owner.id, is_superuser=owner.is_superuser)
    return await Viewer.of(db, owner.id, held)


async def run_schedule(
    db: AsyncSession, schedule: ReportSchedule, *, trigger: str = "schedule", triggered_by_id: int | None = None
) -> list[ReportRun]:
    """Generate the report for each of the schedule's projects, with its owner's access, and email it."""
    runs: list[ReportRun] = []
    template = await db.get(ReportTemplate, schedule.template_id)
    viewer = await owner_viewer(db, schedule)
    to = await recipients_of(db, schedule)

    def record(project_id: int | None, status: str, message: str, size: int = 0) -> None:
        run = ReportRun(
            schedule_id=schedule.id,
            template_id=schedule.template_id,
            project_id=project_id,
            status=status,
            trigger=trigger,
            format=schedule.format,
            recipients=to,
            message=message,
            size=size,
            triggered_by_id=triggered_by_id,
        )
        db.add(run)
        runs.append(run)

    for project_id in schedule.project_ids or []:
        if template is None or viewer is None:
            record(project_id, "failed", "The template or the schedule's owner no longer exists.")
            continue
        if not to:
            record(project_id, "failed", "No recipients.")
            continue
        project = await db.get(Project, project_id)
        if project is None or project.id not in viewer.visible:
            record(project_id, "failed", "The schedule's owner can no longer see this project.")
            continue
        try:
            spec = TemplateRead.model_validate(template)
            body, media, filename = await build_report(
                db,
                viewer,
                name=spec.name,
                sections=spec.sections,
                branding=spec.branding,
                wide=spec.landscape,
                project=project,
                fmt=schedule.format,
            )
            await deliver(
                Mail(
                    to=to,
                    subject=f"{spec.name}: {project.code} {project.name}",
                    text=(
                        f"{spec.name} for {project.code} {project.name} is attached.\n\n"
                        f'Sent by the scheduled report "{schedule.name}".'
                    ),
                    attachments=[Attachment(filename, body, media)],
                )
            )
            record(project_id, "success", f"Sent {filename} to {len(to)} recipient(s).", len(body))
        except Exception as exc:
            logger.exception("Scheduled report failed", extra={"schedule_id": schedule.id, "project_id": project_id})
            record(project_id, "failed", f"Could not generate the report: {exc.__class__.__name__}")
    schedule.last_run_at = datetime.now(UTC)
    await db.commit()
    return runs


async def run_due(db: AsyncSession, now: datetime | None = None) -> int:
    """Run every enabled schedule whose time has come, and move it on to its next time."""
    now = now or datetime.now(UTC)
    if not await is_enabled(db, "reporting"):
        return 0
    due = list(
        (
            await db.execute(
                select(ReportSchedule).where(
                    ReportSchedule.enabled.is_(True),
                    ReportSchedule.next_run_at.is_not(None),
                    ReportSchedule.next_run_at <= now,
                )
            )
        ).scalars()
    )
    for schedule in due:
        schedule.next_run_at = schedule_next(schedule, now)
        await db.commit()
        await run_schedule(db, schedule)
    return len(due)
