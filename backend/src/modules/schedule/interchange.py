"""Reading Primavera P6 (XER and XML) and Microsoft Project XML schedules, and writing MS Project XML.

Every reader returns an ``Imported`` schedule: activities keyed by the source's own id, links between
those keys, WBS summaries as activities with children, and the project calendar's working weekdays
and holidays. Durations and lags arrive in working days (source hours / hours per day).
"""

import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from xml.sax.saxutils import escape

from .calendar import MON_FRI

MAX_ACTIVITIES = 20_000


class ImportFormatError(ValueError):
    pass


@dataclass
class ImportedActivity:
    key: str
    name: str
    code: str | None = None
    parent_key: str | None = None
    type: str = "task"  # task | milestone | summary
    duration: int = 0
    planned_start: date | None = None
    planned_finish: date | None = None
    actual_start: date | None = None
    actual_finish: date | None = None
    percent_complete: float = 0.0
    constraint_type: str = "asap"
    constraint_date: date | None = None
    budget_hours: float | None = None
    notes: str | None = None
    wbs_code: str | None = None
    extra: dict = field(default_factory=dict)
    """P6 facts the mirror keeps: ``guid``, ``task_type``, ``status_code``, ``total_float_hours``,
    ``longest_path``, ``late_finish``, ``codes`` and ``udfs``."""


@dataclass
class ImportedLink:
    predecessor: str
    successor: str
    type: str = "FS"
    lag: int = 0


@dataclass
class Imported:
    format: str
    project_name: str | None = None
    activities: list[ImportedActivity] = field(default_factory=list)
    links: list[ImportedLink] = field(default_factory=list)
    working_days: list[int] = field(default_factory=lambda: list(MON_FRI))
    holidays: list[date] = field(default_factory=list)
    data_date: date | None = None


# --- shared helpers ------------------------------------------------------------------------------


def _date(value: str | None) -> date | None:
    if not value:
        return None
    value = value.strip()
    for fmt, length in (("%Y-%m-%dT%H:%M:%S", 19), ("%Y-%m-%d %H:%M:%S", 19), ("%Y-%m-%d %H:%M", 16), ("%Y-%m-%d", 10)):
        try:
            return datetime.strptime(value[:length], fmt).date()
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(value).date()
    except ValueError:
        return None


def _float(value: str | None, default: float = 0.0) -> float:
    try:
        return float(value) if value not in (None, "") else default  # type: ignore[arg-type]
    except ValueError:
        return default


def _days(hours: float, per_day: float) -> int:
    return round(hours / per_day) if per_day > 0 else round(hours / 8)


def detect(data: bytes) -> str:
    """``xer``, ``p6_xml`` or ``msp_xml`` from the content, whatever the file is called."""
    head = data[:4096].lstrip(b"\xef\xbb\xbf \r\n\t")
    if head.startswith(b"ERMHDR") or b"\n%T\t" in data[:65536] or head.startswith(b"%T"):
        return "xer"
    sample = data[:65536]
    if b"<APIBusinessObjects" in sample or b"Primavera" in sample and b"<Activity" in sample:
        return "p6_xml"
    if b"schemas.microsoft.com/project" in sample or (b"<Project" in sample and b"<Tasks" in sample):
        return "msp_xml"
    raise ImportFormatError("Unrecognised file: upload a Primavera P6 .xer or .xml, or a Microsoft Project .xml.")


def parse(data: bytes) -> Imported:
    kind = detect(data)
    result = {"xer": parse_xer, "p6_xml": parse_p6_xml, "msp_xml": parse_msp_xml}[kind](data)
    if len(result.activities) > MAX_ACTIVITIES:
        raise ImportFormatError(f"More than {MAX_ACTIVITIES} activities.")
    return result


def _xml_root(data: bytes) -> ET.Element:
    # No document type declarations: they're how entity-expansion attacks arrive, and schedules don't need them.
    if re.search(rb"<!(DOCTYPE|ENTITY)", data[:65536], re.IGNORECASE):
        raise ImportFormatError("XML with a DOCTYPE or entity declarations isn't accepted.")
    try:
        root = ET.fromstring(data)
    except ET.ParseError as exc:
        raise ImportFormatError(f"That XML can't be read: {exc}") from exc
    for el in root.iter():
        if isinstance(el.tag, str) and "}" in el.tag:
            el.tag = el.tag.split("}", 1)[1]
    return root


def _text(el: ET.Element, tag: str) -> str | None:
    child = el.find(tag)
    return child.text.strip() if child is not None and child.text else None


def _number_wbs(activities: list[ImportedActivity]) -> None:
    """Give every activity a dotted WBS code from its position under its parent, unless it has one."""
    children: dict[str | None, list[ImportedActivity]] = {}
    keys = {a.key for a in activities}
    for a in activities:
        parent = a.parent_key if a.parent_key in keys else None
        a.parent_key = parent
        children.setdefault(parent, []).append(a)

    def walk(parent: str | None, prefix: str, depth: int) -> None:
        if depth > 50:
            return
        for n, a in enumerate(children.get(parent, []), start=1):
            a.wbs_code = f"{prefix}{n}"
            walk(a.key, f"{a.wbs_code}.", depth + 1)

    walk(None, "", 0)


# --- Primavera P6 XER ------------------------------------------------------------------------------

XER_LINK = {"PR_FS": "FS", "PR_SS": "SS", "PR_FF": "FF", "PR_SF": "SF"}
XER_CONSTRAINT = {
    "CS_MSO": "mso",
    "CS_MANDSTART": "mso",
    "CS_MSOA": "snet",
    "CS_MEOB": "fnlt",
    "CS_MANDFIN": "fnlt",
}
P6_DAY = {1: 6, 2: 0, 3: 1, 4: 2, 5: 3, 6: 4, 7: 5}
"""P6 numbers days Sunday=1 .. Saturday=7; Python Monday=0 .. Sunday=6."""
EXCEL_EPOCH = date(1899, 12, 30)


def read_xer_tables(text: str) -> dict[str, list[dict[str, str]]]:
    tables: dict[str, list[dict[str, str]]] = {}
    current: str | None = None
    fields: list[str] = []
    for line in text.splitlines():
        if line.startswith("%T\t") or line == "%T":
            current = line[3:].strip()
            tables.setdefault(current, [])
            fields = []
        elif line.startswith("%F\t"):
            fields = line[3:].split("\t")
        elif line.startswith("%R\t") and current is not None:
            values = line[3:].split("\t")
            tables[current].append(dict(zip(fields, values + [""] * (len(fields) - len(values)), strict=False)))
    return tables


def parse_xer_calendar(clndr_data: str) -> tuple[list[int], list[date]]:
    """Working weekdays and non-working exception dates from a P6 ``clndr_data`` blob."""
    compact = re.sub(r"[\s\x7f]", "", clndr_data)
    week_at = compact.find("DaysOfWeek")
    ends = [i for i in (compact.find("Exceptions"), compact.find("VIEW")) if i > week_at]
    section = compact[week_at : min(ends)] if week_at >= 0 and ends else compact[max(week_at, 0) :]
    working = [P6_DAY[int(m.group(1))] for m in re.finditer(r"\(0\|\|([1-7])\(\)(\(\(0\|\|\d+\(s\|)?", section) if m.group(2)]
    holidays: list[date] = []
    exceptions_at = compact.find("Exceptions")
    if exceptions_at >= 0:
        for m in re.finditer(r"\(0\|\|\d+\(d\|(\d+)\)\(\)\)", compact[exceptions_at:]):
            holidays.append(EXCEL_EPOCH + timedelta(days=int(m.group(1))))
    return sorted(set(working)) or list(MON_FRI), sorted(holidays)


def parse_xer(data: bytes) -> Imported:
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        text = data.decode("cp1252", errors="replace")
    tables = read_xer_tables(text)
    if "TASK" not in tables:
        raise ImportFormatError("The XER file has no TASK table.")
    out = Imported(format="xer")

    projects = tables.get("PROJECT", [])
    project = projects[0] if projects else {}
    out.project_name = project.get("proj_short_name") or None
    out.data_date = _date(project.get("last_recalc_date"))
    proj_id = project.get("proj_id")

    calendars = {c.get("clndr_id"): c for c in tables.get("CALENDAR", [])}
    per_day = 8.0
    cal = calendars.get(project.get("clndr_id")) or next((c for c in calendars.values() if c.get("default_flag") == "Y"), None)
    if cal:
        per_day = _float(cal.get("day_hr_cnt"), 8.0) or 8.0
        if cal.get("clndr_data"):
            out.working_days, out.holidays = parse_xer_calendar(cal["clndr_data"])

    wbs_rows = [w for w in tables.get("PROJWBS", []) if not proj_id or w.get("proj_id") == proj_id]
    root_ids = {w["wbs_id"] for w in wbs_rows if w.get("proj_node_flag") == "Y"}
    for w in wbs_rows:
        if w["wbs_id"] in root_ids:
            continue
        parent = w.get("parent_wbs_id")
        out.activities.append(
            ImportedActivity(
                key=f"wbs:{w['wbs_id']}",
                name=w.get("wbs_name") or w.get("wbs_short_name") or "WBS",
                code=w.get("wbs_short_name") or None,
                parent_key=None if parent in root_ids or not parent else f"wbs:{parent}",
                type="summary",
            )
        )

    codes = _xer_codes(tables)
    udfs = _xer_udfs(tables)

    def day_hours(clndr_id: str | None) -> float:
        """Hours in a working day on this calendar (P6 durations, float and lags are hours); else the project's."""
        c = calendars.get(clndr_id)
        return (_float(c.get("day_hr_cnt"), per_day) or per_day) if c else per_day

    task_day: dict[str, float] = {}
    for t in tables["TASK"]:
        if proj_id and t.get("proj_id") not in (None, "", proj_id):
            continue
        task_type = t.get("task_type", "")
        hours = _float(t.get("target_drtn_hr_cnt"))
        t_day = task_day[t["task_id"]] = day_hours(t.get("clndr_id"))
        status = t.get("status_code", "")
        pct = _float(t.get("phys_complete_pct"))
        if status == "TK_Complete":
            pct = 100.0
        wbs = t.get("wbs_id")
        out.activities.append(
            ImportedActivity(
                key=f"task:{t['task_id']}",
                name=t.get("task_name") or t.get("task_code") or "Activity",
                code=t.get("task_code") or None,
                parent_key=f"wbs:{wbs}" if wbs and wbs not in root_ids else None,
                type="milestone" if task_type in ("TT_Mile", "TT_FinMile") else "task",
                duration=0 if task_type in ("TT_Mile", "TT_FinMile") else _days(hours, t_day),
                planned_start=_date(t.get("target_start_date") or t.get("early_start_date")),
                planned_finish=_date(t.get("target_end_date") or t.get("early_end_date")),
                actual_start=_date(t.get("act_start_date")),
                actual_finish=_date(t.get("act_end_date")),
                percent_complete=pct,
                constraint_type=XER_CONSTRAINT.get(t.get("cstr_type", ""), "asap"),
                constraint_date=_date(t.get("cstr_date")),
                budget_hours=_float(t.get("target_work_qty")) or None,
                extra={
                    "guid": t.get("guid") or None,
                    "task_type": task_type,
                    "status_code": status,
                    "total_float_hours": _float(t["total_float_hr_cnt"]) if t.get("total_float_hr_cnt") else None,
                    "longest_path": t.get("driving_path_flag") == "Y",
                    "late_finish": (lf.isoformat() if (lf := _date(t.get("late_end_date"))) else None),
                    "day_hours": t_day,
                    "codes": codes.get(t["task_id"], {}),
                    "udfs": udfs.get(t["task_id"], {}),
                },
            )
        )

    keys = {a.key for a in out.activities}
    for r in tables.get("TASKPRED", []):
        pred, succ = f"task:{r.get('pred_task_id')}", f"task:{r.get('task_id')}"
        if pred in keys and succ in keys:
            out.links.append(
                ImportedLink(
                    pred,
                    succ,
                    XER_LINK.get(r.get("pred_type", ""), "FS"),
                    # P6's default: a lag runs on the predecessor's calendar.
                    _days(_float(r.get("lag_hr_cnt")), task_day.get(r.get("pred_task_id") or "", per_day)),
                )
            )
    # Base calendars often carry decades of old holidays; keep those from a year before the programme on.
    starts = [a.planned_start for a in out.activities if a.planned_start]
    if starts and out.holidays:
        cutoff = min(starts) - timedelta(days=366)
        out.holidays = [h for h in out.holidays if h >= cutoff]
    _number_wbs(out.activities)
    return out


def _xer_codes(tables: dict[str, list[dict[str, str]]]) -> dict[str, dict[str, str]]:
    """``{task_id: {activity code type: value}}`` from TASKACTV, ACTVCODE and ACTVTYPE."""
    types = {r.get("actv_code_type_id"): r.get("actv_code_type") or "" for r in tables.get("ACTVTYPE", [])}
    values = {
        r.get("actv_code_id"): (types.get(r.get("actv_code_type_id"), ""), r.get("short_name") or r.get("actv_code_name") or "")
        for r in tables.get("ACTVCODE", [])
    }
    out: dict[str, dict[str, str]] = {}
    for r in tables.get("TASKACTV", []):
        kind, value = values.get(r.get("actv_code_id"), ("", ""))
        if kind:
            out.setdefault(r.get("task_id") or "", {})[kind] = value
    return out


def _xer_udfs(tables: dict[str, list[dict[str, str]]]) -> dict[str, dict[str, str]]:
    """``{task_id: {UDF label: value}}`` for the UDFs defined on activities."""
    labels = {
        r.get("udf_type_id"): r.get("udf_type_label") or r.get("udf_type_name") or ""
        for r in tables.get("UDFTYPE", [])
        if r.get("table_name") in (None, "", "TASK")
    }
    out: dict[str, dict[str, str]] = {}
    for r in tables.get("UDFVALUE", []):
        label = labels.get(r.get("udf_type_id"))
        if not label:
            continue
        value = r.get("udf_text") or r.get("udf_number") or r.get("udf_date") or r.get("udf_code_id") or ""
        out.setdefault(r.get("fk_id") or "", {})[label] = value
    return out


# --- Primavera P6 XML ----------------------------------------------------------------------------

P6_XML_LINK = {"Finish to Start": "FS", "Start to Start": "SS", "Finish to Finish": "FF", "Start to Finish": "SF"}
P6_XML_CONSTRAINT = {
    "Start On": "mso",
    "Mandatory Start": "mso",
    "Start On or After": "snet",
    "Finish On or Before": "fnlt",
    "Mandatory Finish": "fnlt",
}
P6_XML_TYPE = {
    "Task Dependent": "TT_Task",
    "Resource Dependent": "TT_Rsrc",
    "Level of Effort": "TT_LOE",
    "Start Milestone": "TT_Mile",
    "Finish Milestone": "TT_FinMile",
    "WBS Summary": "TT_WBS",
}
P6_XML_STATUS = {"Not Started": "TK_NotStart", "In Progress": "TK_Active", "Completed": "TK_Complete"}
WEEKDAY_NAMES = {"Monday": 0, "Tuesday": 1, "Wednesday": 2, "Thursday": 3, "Friday": 4, "Saturday": 5, "Sunday": 6}


def parse_p6_xml(data: bytes) -> Imported:
    root = _xml_root(data)
    out = Imported(format="p6_xml")
    project = root.find(".//Project")
    if project is not None:
        out.project_name = _text(project, "Id") or _text(project, "Name")
        out.data_date = _date(_text(project, "DataDate"))

    per_day = 8.0
    calendars = root.findall(".//Calendar")
    if calendars:
        cal = next((c for c in calendars if _text(c, "IsDefault") == "1"), calendars[0])
        per_day = _float(_text(cal, "HoursPerDay"), 8.0) or 8.0
        working = []
        for hours in cal.findall(".//StandardWorkHours"):
            day = WEEKDAY_NAMES.get(_text(hours, "DayOfWeek") or "")
            if day is not None and hours.find("WorkTime") is not None:
                working.append(day)
        if working:
            out.working_days = sorted(set(working))
        out.holidays = sorted(d for d in (_date(_text(h, "Date")) for h in cal.findall(".//HolidayException")) if d is not None)

    for w in root.iter("WBS"):
        oid = _text(w, "ObjectId")
        if not oid:
            continue
        parent = _text(w, "ParentObjectId")
        out.activities.append(
            ImportedActivity(
                key=f"wbs:{oid}",
                name=_text(w, "Name") or _text(w, "Code") or "WBS",
                code=_text(w, "Code"),
                parent_key=f"wbs:{parent}" if parent else None,
                type="summary",
            )
        )

    for a in root.iter("Activity"):
        oid = _text(a, "ObjectId")
        if not oid:
            continue
        kind = _text(a, "Type") or ""
        milestone = "Milestone" in kind
        pct = _float(_text(a, "PercentComplete") or _text(a, "PhysicalPercentComplete"))
        if 0 < pct <= 1 and "." in (_text(a, "PercentComplete") or ""):
            pct *= 100
        if (_text(a, "Status") or "") == "Completed":
            pct = 100.0
        wbs = _text(a, "WBSObjectId")
        out.activities.append(
            ImportedActivity(
                key=f"task:{oid}",
                name=_text(a, "Name") or _text(a, "Id") or "Activity",
                code=_text(a, "Id"),
                parent_key=f"wbs:{wbs}" if wbs else None,
                type="milestone" if milestone else "task",
                duration=0 if milestone else _days(_float(_text(a, "PlannedDuration")), per_day),
                planned_start=_date(_text(a, "PlannedStartDate") or _text(a, "StartDate")),
                planned_finish=_date(_text(a, "PlannedFinishDate") or _text(a, "FinishDate")),
                actual_start=_date(_text(a, "ActualStartDate")),
                actual_finish=_date(_text(a, "ActualFinishDate")),
                percent_complete=pct,
                constraint_type=P6_XML_CONSTRAINT.get(_text(a, "PrimaryConstraintType") or "", "asap"),
                constraint_date=_date(_text(a, "PrimaryConstraintDate")),
                budget_hours=_float(_text(a, "PlannedTotalUnits")) or None,
                notes=_text(a, "Notes"),
                extra={
                    "guid": _text(a, "GUID"),
                    "task_type": P6_XML_TYPE.get(kind, kind),
                    "status_code": P6_XML_STATUS.get(_text(a, "Status") or "", _text(a, "Status") or ""),
                    "total_float_hours": _float(_text(a, "TotalFloat")) if _text(a, "TotalFloat") else None,
                    "longest_path": (_text(a, "IsLongestPath") or "").lower() in ("1", "true"),
                    "late_finish": (lf.isoformat() if (lf := _date(_text(a, "LateFinishDate"))) else None),
                    "codes": {},
                    "udfs": {},
                },
            )
        )

    keys = {x.key for x in out.activities}
    for r in root.iter("Relationship"):
        pred, succ = f"task:{_text(r, 'PredecessorActivityObjectId')}", f"task:{_text(r, 'SuccessorActivityObjectId')}"
        if pred in keys and succ in keys:
            out.links.append(
                ImportedLink(pred, succ, P6_XML_LINK.get(_text(r, "Type") or "", "FS"), _days(_float(_text(r, "Lag")), per_day))
            )
    _number_wbs(out.activities)
    return out


# --- Microsoft Project XML -----------------------------------------------------------------------

MSP_LINK = {"0": "FF", "1": "FS", "2": "SF", "3": "SS"}
MSP_LINK_CODE = {v: k for k, v in MSP_LINK.items()}
MSP_CONSTRAINT = {"2": "mso", "4": "snet", "7": "fnlt"}
MSP_CONSTRAINT_CODE = {"asap": "0", "mso": "2", "snet": "4", "fnlt": "7"}
MSP_DAY = {1: 6, 2: 0, 3: 1, 4: 2, 5: 3, 6: 4, 7: 5}
"""MS Project's DayType: Sunday=1 .. Saturday=7."""
MSP_DAY_CODE = {v: k for k, v in MSP_DAY.items()}


def _iso_hours(value: str | None) -> float:
    """Hours in an ISO 8601 duration such as ``PT40H0M0S`` or ``P5DT0H``."""
    if not value:
        return 0.0
    m = re.fullmatch(r"-?P(?:(\d+(?:\.\d+)?)D)?(?:T(?:(\d+(?:\.\d+)?)H)?(?:(\d+(?:\.\d+)?)M)?(?:(\d+(?:\.\d+)?)S)?)?", value)
    if not m:
        return 0.0
    d, h, mi, s = (float(g) if g else 0.0 for g in m.groups())
    return d * 24 + h + mi / 60 + s / 3600


def parse_msp_xml(data: bytes) -> Imported:
    root = _xml_root(data)
    out = Imported(format="msp_xml")
    out.project_name = _text(root, "Name") or _text(root, "Title")
    out.data_date = _date(_text(root, "StatusDate"))
    minutes_per_day = _float(_text(root, "MinutesPerDay"), 480.0) or 480.0
    per_day = minutes_per_day / 60

    cal_uid = _text(root, "CalendarUID")
    calendars = root.findall("./Calendars/Calendar")
    cal = next((c for c in calendars if _text(c, "UID") == cal_uid), calendars[0] if calendars else None)
    if cal is not None:
        working: list[int] = []
        holidays: list[date] = []
        for wd in cal.findall("./WeekDays/WeekDay"):
            kind = int(_float(_text(wd, "DayType"), -1))
            if kind == 0:
                if _text(wd, "DayWorking") == "0":
                    start = _date(_text(wd, "TimePeriod/FromDate"))
                    end = _date(_text(wd, "TimePeriod/ToDate")) or start
                    while start is not None and end is not None and start <= end and len(holidays) < 5000:
                        holidays.append(start)
                        start += timedelta(days=1)
            elif kind in MSP_DAY and _text(wd, "DayWorking") == "1":
                working.append(MSP_DAY[kind])
        for ex in cal.findall("./Exceptions/Exception"):
            if _text(ex, "DayWorking") == "0":
                start = _date(_text(ex, "TimePeriod/FromDate"))
                end = _date(_text(ex, "TimePeriod/ToDate")) or start
                while start is not None and end is not None and start <= end and len(holidays) < 5000:
                    holidays.append(start)
                    start += timedelta(days=1)
        if working:
            out.working_days = sorted(set(working))
        out.holidays = sorted(set(holidays))

    parents: list[tuple[int, str]] = []  # stack of (outline level, key)
    for t in root.findall("./Tasks/Task"):
        uid = _text(t, "UID")
        if uid is None or uid == "0" or _text(t, "IsNull") == "1":
            continue
        level = int(_float(_text(t, "OutlineLevel"), 1))
        while parents and parents[-1][0] >= level:
            parents.pop()
        key = f"task:{uid}"
        summary = _text(t, "Summary") == "1"
        milestone = _text(t, "Milestone") == "1"
        out.activities.append(
            ImportedActivity(
                key=key,
                name=_text(t, "Name") or "Task",
                code=_text(t, "ID"),
                parent_key=parents[-1][1] if parents else None,
                type="summary" if summary else "milestone" if milestone else "task",
                duration=0 if milestone else _days(_iso_hours(_text(t, "Duration")), per_day),
                planned_start=_date(_text(t, "Start")),
                planned_finish=_date(_text(t, "Finish")),
                actual_start=_date(_text(t, "ActualStart")),
                actual_finish=_date(_text(t, "ActualFinish")),
                percent_complete=_float(_text(t, "PercentComplete")),
                constraint_type=MSP_CONSTRAINT.get(_text(t, "ConstraintType") or "0", "asap"),
                constraint_date=_date(_text(t, "ConstraintDate")),
                budget_hours=_iso_hours(_text(t, "Work")) or None,
                notes=_text(t, "Notes"),
                wbs_code=_text(t, "WBS") or _text(t, "OutlineNumber"),
            )
        )
        parents.append((level, key))
        for link in t.findall("PredecessorLink"):
            pred = _text(link, "PredecessorUID")
            if pred is None:
                continue
            # LinkLag is in tenths of a minute.
            lag_minutes = _float(_text(link, "LinkLag")) / 10
            out.links.append(
                ImportedLink(
                    f"task:{pred}", key, MSP_LINK.get(_text(link, "Type") or "1", "FS"), round(lag_minutes / minutes_per_day)
                )
            )

    keys = {a.key for a in out.activities}
    out.links = [lk for lk in out.links if lk.predecessor in keys and lk.successor in keys]
    if any(a.wbs_code is None for a in out.activities):
        _number_wbs(out.activities)
    return out


@dataclass
class ExportActivity:
    uid: int
    wbs_code: str
    name: str
    outline_level: int
    summary: bool
    milestone: bool
    duration: int
    start: date
    finish: date
    percent_complete: float
    constraint_type: str
    constraint_date: date | None
    actual_start: date | None
    actual_finish: date | None
    notes: str | None
    predecessors: list[tuple[int, str, int]]  # (uid, type, lag days)


def write_msp_xml(
    name: str, start: date, activities: list[ExportActivity], working_days: list[int], holidays: list[date]
) -> bytes:
    def dt(d: date | None, end: bool = False) -> str:
        return f"{d.isoformat()}T{'17:00:00' if end else '08:00:00'}" if d else ""

    lines = [
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>',
        '<Project xmlns="http://schemas.microsoft.com/project">',
        f"<Name>{escape(name)}</Name>",
        f"<StartDate>{dt(start)}</StartDate>",
        "<MinutesPerDay>480</MinutesPerDay>",
        "<CalendarUID>1</CalendarUID>",
        "<Calendars><Calendar><UID>1</UID><Name>Standard</Name><IsBaseCalendar>1</IsBaseCalendar><WeekDays>",
    ]
    for py_day in range(7):
        code = MSP_DAY_CODE[py_day]
        if py_day in working_days:
            lines.append(
                f"<WeekDay><DayType>{code}</DayType><DayWorking>1</DayWorking><WorkingTimes>"
                "<WorkingTime><FromTime>08:00:00</FromTime><ToTime>12:00:00</ToTime></WorkingTime>"
                "<WorkingTime><FromTime>13:00:00</FromTime><ToTime>17:00:00</ToTime></WorkingTime>"
                "</WorkingTimes></WeekDay>"
            )
        else:
            lines.append(f"<WeekDay><DayType>{code}</DayType><DayWorking>0</DayWorking></WeekDay>")
    lines.append("</WeekDays><Exceptions>")
    for h in holidays:
        lines.append(
            "<Exception><EnteredByOccurrences>0</EnteredByOccurrences>"
            f"<TimePeriod><FromDate>{h.isoformat()}T00:00:00</FromDate><ToDate>{h.isoformat()}T23:59:00</ToDate></TimePeriod>"
            "<Occurrences>1</Occurrences><Type>1</Type><DayWorking>0</DayWorking></Exception>"
        )
    lines.append("</Exceptions></Calendar></Calendars><Tasks>")
    for a in activities:
        parts = [
            "<Task>",
            f"<UID>{a.uid}</UID><ID>{a.uid}</ID>",
            f"<Name>{escape(a.name)}</Name>",
            f"<WBS>{escape(a.wbs_code)}</WBS><OutlineNumber>{escape(a.wbs_code)}</OutlineNumber>",
            f"<OutlineLevel>{a.outline_level}</OutlineLevel>",
            f"<Start>{dt(a.start)}</Start><Finish>{dt(a.finish, end=True)}</Finish>",
            f"<Duration>PT{a.duration * 8}H0M0S</Duration><DurationFormat>7</DurationFormat>",
            f"<Milestone>{int(a.milestone)}</Milestone><Summary>{int(a.summary)}</Summary>",
            f"<PercentComplete>{round(a.percent_complete)}</PercentComplete>",
            f"<ConstraintType>{MSP_CONSTRAINT_CODE.get(a.constraint_type, '0')}</ConstraintType>",
        ]
        if a.constraint_date and a.constraint_type != "asap":
            parts.append(f"<ConstraintDate>{dt(a.constraint_date)}</ConstraintDate>")
        if a.actual_start:
            parts.append(f"<ActualStart>{dt(a.actual_start)}</ActualStart>")
        if a.actual_finish:
            parts.append(f"<ActualFinish>{dt(a.actual_finish, end=True)}</ActualFinish>")
        if a.notes:
            parts.append(f"<Notes>{escape(a.notes)}</Notes>")
        for uid, kind, lag in a.predecessors:
            parts.append(
                f"<PredecessorLink><PredecessorUID>{uid}</PredecessorUID><Type>{MSP_LINK_CODE.get(kind, '1')}</Type>"
                f"<LinkLag>{lag * 4800}</LinkLag><LagFormat>7</LagFormat></PredecessorLink>"
            )
        parts.append("</Task>")
        lines.append("".join(parts))
    lines.append("</Tasks></Project>")
    return "\n".join(lines).encode("utf-8")
