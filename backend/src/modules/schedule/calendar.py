"""A working-day calendar: which weekdays are worked, and which dates are holidays.

Scheduling happens in *working-day indices* counted from an origin date: index 0 is the first
working day on or after the origin, index 1 the next working day, and so on (negative indices count
back). A start is the start of its day; a finish is held *exclusive* (the index after the last day
worked), so an activity of duration ``d`` starting at ``s`` finishes at ``s + d``.
"""

from bisect import bisect_left
from collections.abc import Iterable
from datetime import date, timedelta

MON_FRI = (0, 1, 2, 3, 4)
ONE_DAY = timedelta(days=1)


class Calendar:
    def __init__(self, origin: date, working_days: Iterable[int] = MON_FRI, holidays: Iterable[date] = ()) -> None:
        self.working_days = frozenset(int(d) for d in working_days if 0 <= int(d) <= 6) or frozenset(MON_FRI)
        self.holidays = frozenset(holidays)
        self.origin = origin
        start = origin
        while not self.is_working(start):
            start += ONE_DAY
        self._forward: list[date] = [start]  # index i >= 0
        self._back: list[date] = []  # index -(i+1)

    def is_working(self, day: date) -> bool:
        return day.weekday() in self.working_days and day not in self.holidays

    def _next_working(self, day: date, step: timedelta) -> date:
        day += step
        while not self.is_working(day):
            day += step
        return day

    def _extend_forward(self, until: date) -> None:
        days = self._forward
        while days[-1] < until:
            days.append(self._next_working(days[-1], ONE_DAY))

    def _extend_back(self, until: date) -> None:
        days = self._back
        while (days[-1] if days else self._forward[0]) > until:
            days.append(self._next_working(days[-1] if days else self._forward[0], -ONE_DAY))

    def date_of(self, index: int) -> date:
        """The working day at ``index``."""
        if index >= 0:
            while len(self._forward) <= index:
                self._forward.append(self._next_working(self._forward[-1], ONE_DAY))
            return self._forward[index]
        while len(self._back) < -index:
            self._back.append(self._next_working(self._back[-1] if self._back else self._forward[0], -ONE_DAY))
        return self._back[-index - 1]

    def index_of(self, day: date) -> int:
        """The index of ``day``, or of the next working day when ``day`` isn't worked (a start)."""
        if day >= self._forward[0]:
            self._extend_forward(day)
            return bisect_left(self._forward, day)
        self._extend_back(day)
        # _back is descending: count the working days strictly before the first index that are >= day.
        before = 0
        for d in self._back:
            if d >= day:
                before += 1
            else:
                break
        return -before

    def finish_index(self, day: date) -> int:
        """The exclusive finish index for work that ends on ``day`` (inclusive)."""
        return self.index_of(day + ONE_DAY)

    def finish_date(self, start_index: int, finish_index: int) -> date:
        """The calendar date work finishes on: the last day worked, or the start for a milestone."""
        return self.date_of(finish_index - 1 if finish_index > start_index else start_index)

    def working_days_between(self, start: date, finish: date) -> int:
        """Working days from ``start`` to ``finish``, both inclusive (0 when finish is before start)."""
        return max(0, self.finish_index(finish) - self.index_of(start))

    def add_working_days(self, start: date, days: int) -> date:
        """The date ``days`` working days on from ``start`` (``days`` may be negative)."""
        return self.date_of(self.index_of(start) + days)
