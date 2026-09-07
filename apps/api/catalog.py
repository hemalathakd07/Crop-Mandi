"""Public Coffee, Pepper, and Rice series names for the API.

Coffee and Pepper series are static (fixed grades/markets). Rice series are a
live AGMARKNET market+variety taxonomy, so they are resolved from the database
when a session is available and resolve to an empty tuple without one.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


def normalize_name(value: str) -> str:
    return " ".join(value.replace("_", " ").replace("-", " ").lower().split())


@dataclass(frozen=True)
class SeriesSpec:
    commodity: str
    series_id: str
    display_name: str
    aliases: tuple[str, ...]


COFFEE_SERIES = (
    SeriesSpec(
        "coffee",
        "coffee_arabica_parchment",
        "Arabica Parchment",
        ("arabica parchment", "coffee arabica parchment", "arabica_parchment"),
    ),
    SeriesSpec(
        "coffee",
        "coffee_arabica_cherry",
        "Arabica Cherry",
        ("arabica cherry", "coffee arabica cherry", "arabica_cherry"),
    ),
    SeriesSpec(
        "coffee",
        "coffee_robusta_parchment",
        "Robusta Parchment",
        ("robusta parchment", "coffee robusta parchment", "robusta_parchment"),
    ),
    SeriesSpec(
        "coffee",
        "coffee_robusta_cherry",
        "Robusta Cherry",
        ("robusta cherry", "coffee robusta cherry", "robusta_cherry"),
    ),
)

PEPPER_SERIES = (
    SeriesSpec(
        "pepper",
        "pepper_cochin_garbled",
        "Cochin Garbled",
        ("cochin garbled", "pepper cochin garbled", "garbled"),
    ),
    SeriesSpec(
        "pepper",
        "pepper_cochin_ungarbled",
        "Cochin Ungarbled",
        ("cochin ungarbled", "pepper cochin ungarbled", "ungarbled"),
    ),
    SeriesSpec(
        "pepper",
        "pepper_sirsi",
        "Sirsi",
        ("sirsi", "pepper sirsi"),
    ),
)

RICE_SERIES = ()

SUPPORTED_COMMODITIES = frozenset({"coffee", "pepper", "rice"})


def series_for(commodity: str, session: Any = None) -> tuple[SeriesSpec, ...]:
    if commodity == "coffee":
        return COFFEE_SERIES
    if commodity == "pepper":
        return PEPPER_SERIES
    if commodity == "rice":
        if session is not None:
            from apps.api.rice_data import rice_series_specs

            return rice_series_specs(session)
        return RICE_SERIES
    return ()


def resolve_series(commodity: str, series: str, session: Any = None) -> SeriesSpec | None:
    wanted = normalize_name(series)
    for spec in series_for(commodity, session=session):
        names = {normalize_name(spec.display_name), normalize_name(spec.series_id), *spec.aliases}
        if wanted in names:
            return spec
    return None
