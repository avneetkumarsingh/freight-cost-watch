"""Stretch goal: ask plain-English questions about the findings.

Answers ONLY from outputs/output.csv (the assistant's own results). It parses
route / month / year / verdict intent from the question, filters the rows and
quotes them. If nothing matches it says so; it never invents a cause.
"""
import re

import pandas as pd

from . import config

_MONTHS = ["january", "february", "march", "april", "may", "june", "july",
           "august", "september", "october", "november", "december"]


def _route_hits(question: str, routes):
    q = question.lower()
    hits = [r for r in routes if r.lower() in q or r.lower().replace("-", " to ") in q]
    if hits:
        return hits
    cities = [r for r in routes if any(c.lower() in q for c in r.split("-"))]
    return cities


def answer(question: str, results: pd.DataFrame, all_routes=None) -> str:
    q = question.lower()
    df = results.copy()
    df["_dt"] = pd.to_datetime(df["week_of"])
    routes = sorted(set(df.route) | set(all_routes or []))
    scope = []
    hits = _route_hits(question, routes)
    if hits:
        df = df[df.route.isin(hits)]
        scope.append("/".join(hits))
    for i, m in enumerate(_MONTHS, 1):
        if re.search(rf"\b{m}\b|\b{m[:3]}\b", q):
            df = df[df["_dt"].dt.month == i]
            scope.append(m.title())
            break
    y = re.search(r"\b(20\d\d)\b", q)
    if y:
        df = df[df["_dt"].dt.year == int(y[1])]
        scope.append(y[1])
    if re.search(r"unexplained|unjustified|suspicious|no reason|not justified", q):
        df = df[df.flagged == "Yes"]
        scope.append("unexplained only")
    elif re.search(r"justified|explained|real reason", q):
        df = df[df.flagged != "Yes"]
        scope.append("justified only")
    label = ", ".join(scope) or "all routes and weeks"
    if df.empty:
        return (f"I found no flagged week for [{label}] in my results. That means my checks did not "
                "see an unusual cost rise there (or the question is outside what I analysed); "
                "I can't offer a cause I haven't found.")
    lines = [f"{len(df)} flagged week(s) for [{label}]:"]
    for r in df.itertuples():
        verdict = "UNEXPLAINED" if r.flagged == "Yes" else f"justified by {r.matched_note_id}"
        lines.append(f"- {r.route}, week of {r.week_of}: {r.cost_per_tonne_km} INR/tonne-km "
                     f"({r.vs_own_history}; {r.vs_similar_routes}) -> {verdict}. {r.reason}")
    return "\n".join(lines)


def load_results(path=config.OUTPUT_CSV) -> pd.DataFrame:
    return pd.read_csv(path, keep_default_na=False)
