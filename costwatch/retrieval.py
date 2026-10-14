"""Stage 1 of the RAG step: rank notes by relevance to a flagged route-week.

TF-IDF cosine similarity (scikit-learn): deterministic, offline, free, no
model download. Ranking only proposes candidates; verdict.py decides.
"""
from typing import List

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer

from . import config
from .notes import Note

_MONTH_NAMES = ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"]


def _doc(n: Note) -> str:
    months = {_MONTH_NAMES[n.date.month - 1], _MONTH_NAMES[n.window[0].month - 1],
              _MONTH_NAMES[n.window[1].month - 1]}
    return f"{n.applies_to} {n.text} {' '.join(sorted(months))} {n.date.year}"


class NoteRetriever:
    def __init__(self, notes: List[Note]):
        self.notes = sorted(notes, key=lambda n: n.note_id)
        self.vec = TfidfVectorizer(lowercase=True, ngram_range=(1, 2), sublinear_tf=True)
        self.matrix = self.vec.fit_transform([_doc(n) for n in self.notes])

    def query_text(self, route: str, week_of) -> str:
        origin, dest = route.split("-", 1)
        m = _MONTH_NAMES[week_of.month - 1]
        return (f"{route} {origin} {dest} all routes cost rise increase surcharge "
                f"disruption diesel toll flood festival {m} {week_of.year}")

    def top_k(self, route: str, week_of, k: int = config.RETRIEVE_TOP_K) -> List[Note]:
        q = self.vec.transform([self.query_text(route, week_of)])
        sims = (self.matrix @ q.T).toarray().ravel()
        # Stable order: score desc, then note_id asc -> identical across runs.
        order = sorted(range(len(self.notes)), key=lambda i: (-round(float(sims[i]), 12), self.notes[i].note_id))
        return [self.notes[i] for i in order[:k]]
