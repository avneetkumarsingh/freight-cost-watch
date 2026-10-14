"""Turn a free-text note into structured, checkable facts: scope, window, effect, magnitude.

Deterministic regex/lexicon extraction (no LLM). Anything we cannot parse
falls back to the CONSERVATIVE reading, so a note can only fail to justify,
never justify by accident.
"""
import re
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Optional, Tuple

import pandas as pd

from . import config

_MONTHS = {m: i for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], 1)}

# Phrases saying costs were NOT pushed up (checked first; any hit wins).
NO_EFFECT = [
    r"not (?:significantly )?affected", r"no (?:major|significant) disruptions?",
    r"without a rate change", r"returned to normal", r"remained (?:stable|normal)",
    r"improved road conditions", r"not part of this dataset",
]
# Phrases saying costs went UP.
RAISES = [
    r"higher (?:trip )?costs?", r"surcharge", r"pushing up", r"costs? (?:rose|increased)",
    r"prices? rose",
]
_RANGE = re.compile(r"from ([A-Z][a-z]{2}) (\d{1,2}) to ([A-Z][a-z]{2}) (\d{1,2})")
_PCT = re.compile(r"(\d+(?:\.\d+)?)\s*(?:-|to)\s*(\d+(?:\.\d+)?)\s*%")
_PCT1 = re.compile(r"(\d+(?:\.\d+)?)\s*%")


@dataclass(frozen=True)
class Note:
    note_id: str
    date: date
    applies_to: str
    text: str
    scope_all: bool
    effect: str                     # "raises" | "no_cost_effect" | "unknown"
    window: Tuple[date, date]       # inclusive
    window_basis: str               # how the window was derived
    magnitude_pct: Optional[Tuple[float, float]]


def monday(d: date) -> date:
    return d - timedelta(days=d.weekday())


def _classify_effect(text: str) -> str:
    t = text.lower()
    if any(re.search(p, t) for p in NO_EFFECT):
        return "no_cost_effect"
    if any(re.search(p, t) for p in RAISES):
        return "raises"
    return "unknown"


def _parse_window(text: str, d: date):
    m = _RANGE.search(text)
    if m:
        s = date(d.year, _MONTHS[m[1].lower()], int(m[2]))
        e = date(d.year, _MONTHS[m[3].lower()], int(m[4]))
        if e < s:
            e = e.replace(year=e.year + 1)
        return s, e, "explicit date range in text"
    if re.search(r"starting this week", text, re.I):
        s = monday(d)
        e = s + timedelta(weeks=config.OPEN_ENDED_HORIZON_WEEKS) - timedelta(days=1)
        return s, e, f"open-ended shift from note week, capped at {config.OPEN_ENDED_HORIZON_WEEKS} weeks"
    s = monday(d)
    return s, s + timedelta(days=6), "note's own week (conservative default)"


def _parse_magnitude(text: str):
    m = _PCT.search(text)
    if m:
        return float(m[1]), float(m[2])
    m = _PCT1.search(text)
    return (float(m[1]), float(m[1])) if m else None


def parse_note(row) -> Note:
    d = pd.Timestamp(row["date"]).date()
    text = str(row["note"]).strip()
    s, e, basis = _parse_window(text, d)
    return Note(
        note_id=str(row["note_id"]).strip(), date=d,
        applies_to=str(row["applies_to"]).strip(), text=text,
        scope_all=str(row["applies_to"]).strip().lower() == "all routes",
        effect=_classify_effect(text), window=(s, e), window_basis=basis,
        magnitude_pct=_parse_magnitude(text),
    )


def load_notes(path=config.NOTES_CSV):
    df = pd.read_csv(path)
    return [parse_note(r) for _, r in df.iterrows()]
