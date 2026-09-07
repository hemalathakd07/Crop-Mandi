"""Published-session helpers. Targets are market sessions, not calendar days."""

from __future__ import annotations

from datetime import date, timedelta


WEEKDAYS = frozenset(range(5))  # Monday=0 .. Friday=4


def is_weekday(d: date) -> bool:
    return d.weekday() < 5


def filter_weekdays(dates: list[date], prices: list[float]) -> tuple[list[date], list[float]]:
    """Drop Saturday and Sunday. Does not fill gaps or interpolate."""
    if len(dates) != len(prices):
        raise ValueError("dates and prices must be the same length")
    out_d: list[date] = []
    out_p: list[float] = []
    for d, p in zip(dates, prices):
        if is_weekday(d) and p is not None:
            out_d.append(d)
            out_p.append(float(p))
    return out_d, out_p


def next_weekday_session(d: date) -> date:
    """Next Monday–Friday after d. Used when every weekday is a published coffee session."""
    nxt = d + timedelta(days=1)
    while nxt.weekday() >= 5:
        nxt += timedelta(days=1)
    return nxt


def chronological_split_index(n: int, train_fraction: float = 0.7) -> int:
    """First test index. Train is [0, index); test is [index, n). Never shuffled."""
    if n < 2:
        raise ValueError("need at least 2 observations to split")
    if not 0.0 < train_fraction < 1.0:
        raise ValueError("train_fraction must be between 0 and 1")
    idx = int(n * train_fraction)
    idx = max(1, min(n - 1, idx))
    return idx
