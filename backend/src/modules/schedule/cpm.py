"""The critical path method, pure Python: no database, no FastAPI.

``calculate(activities, links, calendar, ...)`` runs a forward and a backward pass over working-day
indices (see ``calendar``), honouring FS/SS/FF/SF links with positive or negative lags, actual dates,
and four constraints (ASAP, start no earlier than, finish no later than, must start on). It returns
early/late dates, total and free float, the critical flag and the driving predecessors of every
activity, and rolls summary activities up from their children.

The passes themselves (``forward`` / ``backward``) work on plain lists of numbers so Monte Carlo can
reuse them thousands of times with sampled durations.
"""

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import date
from math import ceil

from .calendar import Calendar

FS, SS, FF, SF = "FS", "SS", "FF", "SF"
LINK_TYPES = (FS, SS, FF, SF)
ASAP, SNET, FNLT, MSO = "asap", "snet", "fnlt", "mso"
EPSILON = 1e-9


class CycleError(ValueError):
    """The links loop back on themselves. ``cycle`` lists the activity ids, first repeated at the end."""

    def __init__(self, cycle: list[int]) -> None:
        super().__init__("Dependency cycle: " + " -> ".join(str(i) for i in cycle))
        self.cycle = cycle


@dataclass
class Activity:
    id: int
    duration: int = 0
    parent_id: int | None = None
    summary: bool = False
    constraint: str = ASAP
    constraint_date: date | None = None
    actual_start: date | None = None
    actual_finish: date | None = None
    percent_complete: float = 0.0
    weight: float = 0.0
    """Budget hours, for rolling progress up to a summary (used when every sibling has them)."""


@dataclass(frozen=True)
class Link:
    predecessor: int
    successor: int
    type: str = FS
    lag: int = 0


@dataclass
class Result:
    early_start: date
    early_finish: date
    late_start: date
    late_finish: date
    duration: int
    total_float: int
    free_float: int
    critical: bool
    driving: list[int] = field(default_factory=list)
    percent_complete: float = 0.0


@dataclass
class Schedule:
    activities: dict[int, Result]
    start: date
    finish: date
    critical_path: list[int]


@dataclass
class Network:
    """The task activities in topological order, with links as index lists, ready for repeated passes."""

    ids: list[int]
    preds: list[list[tuple[int, str, float]]]
    succs: list[list[tuple[int, str, float]]]


def build_network(task_ids: Sequence[int], links: Sequence[Link]) -> Network:
    """Order ``task_ids`` so every predecessor comes first; ``CycleError`` when that's impossible."""
    position = {aid: i for i, aid in enumerate(task_ids)}
    n = len(task_ids)
    preds: list[list[tuple[int, str, float]]] = [[] for _ in range(n)]
    succs: list[list[tuple[int, str, float]]] = [[] for _ in range(n)]
    indegree = [0] * n
    for link in links:
        p, s = position.get(link.predecessor), position.get(link.successor)
        if p is None or s is None:
            continue
        if p == s:
            raise CycleError([link.predecessor, link.predecessor])
        preds[s].append((p, link.type, float(link.lag)))
        succs[p].append((s, link.type, float(link.lag)))
        indegree[s] += 1

    order: list[int] = []
    ready = [i for i in range(n) if indegree[i] == 0]
    while ready:
        i = ready.pop()
        order.append(i)
        for s, _, _ in succs[i]:
            indegree[s] -= 1
            if indegree[s] == 0:
                ready.append(s)
    if len(order) < n:
        raise CycleError(_find_cycle([i for i in range(n) if indegree[i] > 0], succs, task_ids))

    # Renumber so position in the list is the topological order.
    renumber = {old: new for new, old in enumerate(order)}
    return Network(
        ids=[task_ids[i] for i in order],
        preds=[[(renumber[p], t, lag) for p, t, lag in preds[i]] for i in order],
        succs=[[(renumber[s], t, lag) for s, t, lag in succs[i]] for i in order],
    )


def _find_cycle(stuck: list[int], succs: list[list[tuple[int, str, float]]], ids: Sequence[int]) -> list[int]:
    """A cycle among the nodes Kahn's algorithm couldn't order. Every one of them reaches a cycle."""
    remaining = set(stuck)
    node = stuck[0]
    seen: dict[int, int] = {}
    path: list[int] = []
    while node not in seen:
        seen[node] = len(path)
        path.append(node)
        node = next(s for s, _, _ in succs[node] if s in remaining)
    loop = path[seen[node] :] + [node]
    return [ids[i] for i in loop]


def forward(
    net: Network, durations: Sequence[float], floor: Sequence[float], fixed: Sequence[float | None]
) -> tuple[list[float], list[float]]:
    """Early start and (exclusive) early finish of each activity in network order."""
    n = len(net.ids)
    es = [0.0] * n
    ef = [0.0] * n
    preds = net.preds
    for i in range(n):
        d = durations[i]
        f = fixed[i]
        if f is not None:
            s = f
        else:
            s = floor[i]
            for p, t, lag in preds[i]:
                if t == FS:
                    v = ef[p] + lag
                elif t == SS:
                    v = es[p] + lag
                elif t == FF:
                    v = ef[p] + lag - d
                else:
                    v = es[p] + lag - d
                if v > s:
                    s = v
        es[i] = s
        ef[i] = s + d
    return es, ef


def backward(
    net: Network,
    durations: Sequence[float],
    finish: float,
    ceiling: Sequence[float | None],
) -> tuple[list[float], list[float]]:
    """Late start and (exclusive) late finish of each activity in network order."""
    n = len(net.ids)
    ls = [0.0] * n
    lf = [0.0] * n
    succs = net.succs
    for i in range(n - 1, -1, -1):
        d = durations[i]
        c = ceiling[i]
        f = finish if c is None or c > finish else c
        for s, t, lag in succs[i]:
            if t == FS:
                v = ls[s] - lag
            elif t == SS:
                v = ls[s] - lag + d
            elif t == FF:
                v = lf[s] - lag
            else:
                v = lf[s] - lag + d
            if v < f:
                f = v
        lf[i] = f
        ls[i] = f - d
    return ls, lf


@dataclass
class Prepared:
    """Durations and bounds of each task activity in network order, after progress and constraints."""

    net: Network
    durations: list[float]
    floor: list[float]
    fixed: list[float | None]
    ceiling: list[float | None]
    started: list[bool]


def prepare(
    tasks: Sequence[Activity],
    links: Sequence[Link],
    calendar: Calendar,
    data_date: date | None = None,
) -> Prepared:
    net = build_network([a.id for a in tasks], links)
    by_id = {a.id: a for a in tasks}
    start_floor = 0 if data_date is None else max(0, calendar.index_of(data_date))
    durations: list[float] = []
    floor: list[float] = []
    fixed: list[float | None] = []
    ceiling: list[float | None] = []
    started: list[bool] = []
    for aid in net.ids:
        a = by_id[aid]
        d = max(0, a.duration)
        lower: float = 0
        pinned: float | None = None
        upper: float | None = None
        if a.actual_start is not None:
            pinned = calendar.index_of(a.actual_start)
            if a.actual_finish is not None:
                d = max(0, calendar.finish_index(a.actual_finish) - int(pinned))
            elif data_date is not None:
                remaining = ceil(d * (1 - min(max(a.percent_complete, 0.0), 100.0) / 100) - EPSILON)
                d = max(start_floor - int(pinned), 0) + max(remaining, 0)
                if d == 0 and a.duration > 0:
                    d = 1
        else:
            lower = start_floor
            if a.constraint == SNET and a.constraint_date is not None:
                lower = max(lower, calendar.index_of(a.constraint_date))
            elif a.constraint == MSO and a.constraint_date is not None:
                pinned = calendar.index_of(a.constraint_date)
        if a.constraint == FNLT and a.constraint_date is not None:
            upper = calendar.finish_index(a.constraint_date)
        if a.constraint == MSO and a.constraint_date is not None and a.actual_start is None:
            upper = calendar.index_of(a.constraint_date) + d
        durations.append(float(d))
        floor.append(float(lower))
        fixed.append(None if pinned is None else float(pinned))
        ceiling.append(None if upper is None else float(upper))
        started.append(a.actual_start is not None)
    return Prepared(net, durations, floor, fixed, ceiling, started)


def _driving(net: Network, i: int, es: list[float], ef: list[float], d: float) -> list[int]:
    out = []
    for p, t, lag in net.preds[i]:
        if t == FS:
            v = ef[p] + lag
        elif t == SS:
            v = es[p] + lag
        elif t == FF:
            v = ef[p] + lag - d
        else:
            v = es[p] + lag - d
        if abs(v - es[i]) < EPSILON:
            out.append(net.ids[p])
    return out


def _free_float(net: Network, i: int, es: list[float], ef: list[float], finish: float) -> float:
    if not net.succs[i]:
        return finish - ef[i]
    slack = float("inf")
    for s, t, lag in net.succs[i]:
        if t == FS:
            v = es[s] - lag - ef[i]
        elif t == SS:
            v = es[s] - lag - es[i]
        elif t == FF:
            v = ef[s] - lag - ef[i]
        else:
            v = ef[s] - lag - es[i]
        slack = min(slack, v)
    return slack


def calculate(
    activities: Sequence[Activity],
    links: Sequence[Link],
    calendar: Calendar,
    data_date: date | None = None,
) -> Schedule:
    """Schedule every activity. Summary activities (flagged, or with children) take their children's span."""
    parents = {a.parent_id for a in activities if a.parent_id is not None}
    summaries = [a for a in activities if a.summary or a.id in parents]
    summary_ids = {a.id for a in summaries}
    tasks = [a for a in activities if a.id not in summary_ids]
    task_links = [lk for lk in links if lk.predecessor not in summary_ids and lk.successor not in summary_ids]

    prep = prepare(tasks, task_links, calendar, data_date)
    net = prep.net
    es, ef = forward(net, prep.durations, prep.floor, prep.fixed)
    finish = max(ef, default=0.0)
    ls, lf = backward(net, prep.durations, finish, prep.ceiling)

    results: dict[int, Result] = {}
    spans: dict[int, tuple[int, int, int, int]] = {}
    by_id = {a.id: a for a in activities}
    for i, aid in enumerate(net.ids):
        s, f, lstart, lfinish = int(es[i]), int(ef[i]), int(ls[i]), int(lf[i])
        spans[aid] = (s, f, lstart, lfinish)
        tf = lstart - s
        a = by_id[aid]
        done = a.actual_finish is not None
        results[aid] = Result(
            early_start=calendar.date_of(s),
            early_finish=calendar.finish_date(s, f),
            late_start=calendar.date_of(lstart),
            late_finish=calendar.finish_date(lstart, lfinish),
            duration=f - s,
            total_float=tf,
            free_float=int(_free_float(net, i, es, ef, finish)),
            critical=tf <= 0 and not done,
            driving=_driving(net, i, es, ef, prep.durations[i]),
            percent_complete=100.0 if done else float(a.percent_complete),
        )

    _roll_up(summaries, by_id, results, spans, calendar)

    project_start = min((sp[0] for sp in spans.values()), default=0)
    critical_path = [aid for aid in net.ids if results[aid].critical]
    return Schedule(
        activities=results,
        start=calendar.date_of(project_start),
        # The latest finish date shown on any activity (a closing milestone sits on its own day).
        finish=max((results[aid].early_finish for aid in net.ids), default=calendar.date_of(0)),
        critical_path=critical_path,
    )


def _roll_up(
    summaries: list[Activity],
    by_id: dict[int, Activity],
    results: dict[int, Result],
    spans: dict[int, tuple[int, int, int, int]],
    calendar: Calendar,
) -> None:
    children: dict[int, list[int]] = {}
    for a in by_id.values():
        if a.parent_id is not None and a.parent_id in by_id:
            children.setdefault(a.parent_id, []).append(a.id)

    # Progress rolls up by budget hours when every child has them, otherwise by duration.
    hours: dict[int, float] = {}
    days: dict[int, float] = {}
    progress: dict[int, float] = {}
    for aid, r in results.items():
        a = by_id[aid]
        hours[aid] = max(a.weight, 0.0)
        days[aid] = float(max(r.duration, 1))
        progress[aid] = r.percent_complete

    visiting: set[int] = set()

    def resolve(sid: int) -> None:
        if sid in spans or sid in visiting:
            return
        visiting.add(sid)
        kids = children.get(sid, [])
        for k in kids:
            resolve(k)
        known = [k for k in kids if k in spans]
        if not known:
            spans[sid] = (0, 0, 0, 0)
            hours[sid] = days[sid] = 0.0
            progress[sid] = 0.0
            results[sid] = Result(
                calendar.date_of(0), calendar.date_of(0), calendar.date_of(0), calendar.date_of(0), 0, 0, 0, False
            )
            return
        s = min(spans[k][0] for k in known)
        f = max(spans[k][1] for k in known)
        lstart = min(spans[k][2] for k in known)
        lfinish = max(spans[k][3] for k in known)
        spans[sid] = (s, f, lstart, lfinish)
        hours[sid] = sum(hours[k] for k in known) if all(hours[k] > 0 for k in known) else 0.0
        days[sid] = sum(days[k] for k in known)
        weights = hours if hours[sid] > 0 else days
        total_weight = sum(weights[k] for k in known)
        pct = sum(progress[k] * weights[k] for k in known) / total_weight if total_weight else 0.0
        progress[sid] = pct
        tf = min(results[k].total_float for k in known)
        results[sid] = Result(
            early_start=calendar.date_of(s),
            early_finish=calendar.finish_date(s, f),
            late_start=calendar.date_of(lstart),
            late_finish=calendar.finish_date(lstart, lfinish),
            duration=f - s,
            total_float=tf,
            free_float=min(results[k].free_float for k in known),
            critical=any(results[k].critical for k in known),
            percent_complete=round(pct, 2),
        )

    for a in summaries:
        resolve(a.id)
