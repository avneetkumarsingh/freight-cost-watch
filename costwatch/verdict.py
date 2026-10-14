"""Stage 2: strict, deterministic verification that a note really explains a cost rise.

A note justifies a flagged route-week ONLY if ALL hold:
  1. scope     - applies to this route (or All Routes)
  2. effect    - the note says costs went UP (not 'unaffected', 'normal', 'absorbed' ...)
  3. window    - the note's time window overlaps the Mon-Sun week
  4. magnitude - if the note states a size, the observed rise is not far larger
                 (and for All-Routes notes the gap vs peers must be that small too,
                 since an all-routes cause also moves the peers).
Otherwise it is NOT justified. No LLM is involved, so the verdict cannot vary.
"""
from dataclasses import dataclass
from datetime import timedelta
from typing import List, Optional

from . import config
from .notes import Note


@dataclass(frozen=True)
class Check:
    ok: bool
    code: str      # scope | effect | window | magnitude | ok
    why: str


def _snip(text: str, n: int = 150) -> str:
    text = text.rstrip(".")
    return text if len(text) <= n else text[: n - 1].rstrip() + "…"


def window_distance_days(note: Note, week_start) -> int:
    """0 if the note's window overlaps the week, else days between them."""
    wk_end = week_start + timedelta(days=6)
    s, e = note.window
    if s <= wk_end and e >= week_start:
        return 0
    return (s - wk_end).days if s > wk_end else (week_start - e).days


def verify(note: Note, route: str, week_start, vs_own: float, vs_peers: float) -> Check:
    week_start = week_start.date() if hasattr(week_start, "date") else week_start
    if not (note.scope_all or note.applies_to.lower() == route.lower()):
        return Check(False, "scope", f"it applies to {note.applies_to}, not {route}")
    if note.effect != "raises":
        what = ("reports no cost rise" if note.effect == "no_cost_effect"
                else "does not describe a cost rise")
        return Check(False, "effect", f'it {what}: "{_snip(note.text)}"')
    if window_distance_days(note, week_start) != 0:
        s, e = note.window
        return Check(False, "window", f"its window ({s} to {e}) does not cover the week of {week_start}")
    if note.magnitude_pct:
        hi = note.magnitude_pct[1] + config.MAGNITUDE_TOLERANCE_PP
        gaps = [vs_own * 100] + ([vs_peers * 100] if note.scope_all else [])
        if max(gaps) > hi:
            lo_, hi_ = note.magnitude_pct
            return Check(False, "magnitude",
                         f"it cites only a ~{lo_:g}-{hi_:g}% rise, far smaller than the observed "
                         f"{vs_own*100:+.1f}% vs own history / {vs_peers*100:+.1f}% vs similar routes")
    return Check(True, "ok", "")


@dataclass(frozen=True)
class Verdict:
    justified: bool
    note_id: Optional[str]
    reason: str


def decide(retrieved: List[Note], all_notes: List[Note], route: str, week_start,
           vs_own: float, vs_peers: float, n_prior: int) -> Verdict:
    """First verified note in retrieval order justifies; otherwise explain what was close."""
    ws = week_start.date() if hasattr(week_start, "date") else week_start
    suffix = (f" (Note: only {n_prior} prior week(s) of history were available.)"
              if n_prior < config.HISTORY_WEEKS else "")
    for n in retrieved:
        if verify(n, route, ws, vs_own, vs_peers).ok:
            s, e = n.window
            return Verdict(True, n.note_id,
                           f"Matches note {n.note_id} dated {n.date} (window {s} to {e}): "
                           f"{_snip(n.text, 220)}. The cost rise has a clear explanation.{suffix}")
    # Unexplained: name the closest in-scope notes, and say exactly why each fails.
    near = []
    for n in retrieved:
        if not (n.scope_all or n.applies_to.lower() == route.lower()):
            continue
        d = window_distance_days(n, ws)
        if d <= config.NEAR_NOTE_DAYS:
            near.append((d, n.note_id, n))
    near.sort(key=lambda x: (x[0], x[1]))
    if not near:
        return Verdict(False, None,
                       "No matching note found for this route or date range. Cost rise looks "
                       f"unexplained and worth a human review.{suffix}")
    parts = []
    for _, _, n in near[:2]:
        c = verify(n, route, ws, vs_own, vs_peers)
        parts.append(f"{n.note_id} ({n.date}): {c.why}")
    return Verdict(False, None,
                   "No genuine justification found; flagged for review. Closest note(s) -- "
                   + "; ".join(parts) + f".{suffix}")
