"""Grade temporal do universo: meses, anos e ciclos."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date


def month_start(d: date) -> date:
    return date(d.year, d.month, 1)


def add_months(d: date, n: int) -> date:
    total = (d.year * 12 + (d.month - 1)) + n
    return date(total // 12, total % 12 + 1, 1)


def month_end(d: date) -> date:
    return add_months(month_start(d), 1).toordinal() - 1  # type: ignore[return-value]


def end_of_month(d: date) -> date:
    return date.fromordinal(add_months(month_start(d), 1).toordinal() - 1)


def months_between(a: date, b: date) -> int:
    return (b.year * 12 + b.month) - (a.year * 12 + a.month)


@dataclass(frozen=True)
class Calendar:
    start: date
    end: date

    @property
    def months(self) -> list[date]:
        out, cur = [], month_start(self.start)
        last = month_start(self.end)
        while cur <= last:
            out.append(cur)
            cur = add_months(cur, 1)
        return out

    @property
    def n_months(self) -> int:
        return len(self.months)

    @property
    def years(self) -> list[int]:
        return sorted({m.year for m in self.months})
