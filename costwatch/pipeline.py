"""End to end: shipments -> weekly metrics -> candidates -> retrieve -> verify -> CSV."""
import json
import time

import pandas as pd

from . import config, metrics
from .notes import load_notes
from .retrieval import NoteRetriever
from .verdict import decide

FLAG_YES = "Yes"
FLAG_JUSTIFIED = "No (justified)"


def expected_columns():
    return list(pd.read_csv(config.SAMPLE_OUTPUT_CSV, nrows=0).columns)


def run(shipments_path=config.SHIPMENTS_CSV, notes_path=config.NOTES_CSV, notes=None):
    df = metrics.load_shipments(shipments_path)
    table = metrics.build_weekly_table(df)
    cand = metrics.candidates(table)
    notes = notes if notes is not None else load_notes(notes_path)
    retriever = NoteRetriever(notes)

    rows = []
    for r in cand.itertuples(index=False):
        retrieved = retriever.top_k(r.route, r.week_of)
        v = decide(retrieved, notes, r.route, r.week_of, r.vs_own, r.vs_peers, int(r.n_prior_weeks))
        rows.append({
            "route": r.route,
            "week_of": r.week_of.strftime("%Y-%m-%d"),
            "cost_per_tonne_km": round(r.cost_per_tonne_km, 2),
            "vs_own_history": f"{r.vs_own*100:+.1f}% vs this route's past average",
            "vs_similar_routes": f"{r.vs_peers*100:+.1f}% vs similar-length routes this week",
            "flagged": FLAG_JUSTIFIED if v.justified else FLAG_YES,
            "matched_note_id": v.note_id or "",
            "reason": v.reason,
        })
    out = pd.DataFrame(rows, columns=expected_columns())
    return out, table


def write(out: pd.DataFrame, path=config.OUTPUT_CSV):
    path.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(path, index=False, lineterminator="\n")


def write_cost_log(n_candidates: int, seconds: float, path=config.COST_LOG_JSON):
    log = {
        "llm_calls": 0, "input_tokens": 0, "output_tokens": 0, "estimated_cost_usd": 0.0,
        "model": "none (no LLM used)",
        "retrieval": "TF-IDF (scikit-learn), local, no API, no model download",
        "retrieval_queries": n_candidates,
        "runtime_seconds": round(seconds, 2),
        "note": "Verdicts, numbers and explanations are produced by deterministic code; "
                "see README for the trade-off and how an LLM could be added.",
    }
    path.write_text(json.dumps(log, indent=2) + "\n")
    return log


def main():
    t0 = time.perf_counter()
    out, _ = run()
    write(out)
    log = write_cost_log(len(out), time.perf_counter() - t0)
    print(out[["route", "week_of", "cost_per_tonne_km", "flagged", "matched_note_id"]].to_string(index=False))
    print(f"\n{len(out)} rows -> {config.OUTPUT_CSV}  |  LLM calls: {log['llm_calls']}, cost: ${log['estimated_cost_usd']}")
