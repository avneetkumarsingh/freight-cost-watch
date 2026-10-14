"""Eval harness: why we trust the output. Run:  python eval/run_eval.py

Checks (each prints PASS/FAIL; exit code 1 if any fail):
  1. Output contract      - columns/order identical to sample_output_format_v2.csv
  2. Independent numbers  - pure-Python re-implementation (no pandas) must equal the pipeline
  3. Labeled verdicts     - hand-labeled rows (eval/labels_outputs.csv) vs pipeline
  4. Exhaustive note sweep- every note x every route x every week vs hand-read validity
                            (eval/labels_notes.csv): nothing justified that shouldn't be, nothing missed
  5. Leave-one-out        - remove a cited note -> verdict must flip to unexplained
  6. Threshold sensitivity- how the flag set moves with the thresholds
"""
import csv
import sys
from collections import defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from costwatch import config, metrics, pipeline  # noqa: E402
from costwatch.notes import load_notes  # noqa: E402
from costwatch.verdict import verify  # noqa: E402

RESULTS = []


def check(name, ok, detail=""):
    RESULTS.append(ok)
    print(f"[{'PASS' if ok else 'FAIL'}] {name}" + (f" -- {detail}" if detail else ""))


def pure_python_metrics():
    """Re-derive weekly cost/tonne-km, own baseline, peer baseline with plain dicts."""
    cost, tk, rtype = defaultdict(float), defaultdict(float), {}
    for r in csv.DictReader(open(config.SHIPMENTS_CSV)):
        d = datetime.strptime(r["shipment_date"], "%Y-%m-%d").date()
        wk = d - timedelta(days=d.weekday())
        k = (r["origin"] + "-" + r["destination"], wk)
        cost[k] += float(r["freight_cost_inr"])
        tk[k] += float(r["quantity_tonnes"]) * float(r["distance_km"])
        rtype[k[0]] = r["route_type"]
    cpt = {k: cost[k] / tk[k] for k in cost}
    out = {}
    for (route, wk), v in cpt.items():
        prior = [cpt[(route, wk - timedelta(weeks=i))] for i in range(1, 9)
                 if (route, wk - timedelta(weeks=i)) in cpt]
        peers = [cpt[(r2, wk)] for r2 in rtype if r2 != route and rtype[r2] == rtype[route] and (r2, wk) in cpt]
        out[(route, wk)] = (v, v / (sum(prior) / len(prior)) - 1 if prior else None,
                            v / (sum(peers) / len(peers)) - 1 if peers else None)
    return out


def main():
    out, table = pipeline.run()
    notes = load_notes()

    # 1. contract
    check("1. output columns match sample_output_format_v2.csv exactly",
          list(out.columns) == pipeline.expected_columns())
    check("1b. flagged values only 'Yes' / 'No (justified)'", set(out.flagged) <= {"Yes", "No (justified)"})
    check("1c. matched_note_id blank iff flagged == Yes",
          all((r.flagged == "Yes") == (r.matched_note_id == "") for r in out.itertuples()))

    # 2. independent recomputation
    ref = pure_python_metrics()
    worst = 0.0
    for r in table.itertuples():
        v, o, p = ref[(r.route, r.week_of.date())]
        worst = max(worst, abs(v - r.cost_per_tonne_km))
        if o is not None:
            worst = max(worst, abs(o - r.vs_own))
        if p is not None:
            worst = max(worst, abs(p - r.vs_peers))
    check("2. pipeline numbers == independent pure-Python recomputation", worst < 1e-9,
          f"{len(table)} route-weeks, max abs diff {worst:.2e}")

    # 3. labeled output rows
    lab = pd.read_csv(ROOT / "eval" / "labels_outputs.csv", keep_default_na=False)
    got = {(r.route, r.week_of): r for r in out.itertuples()}
    miss = []
    for l in lab.itertuples():
        g = got.get((l.route, l.week_of))
        if g is None or g.flagged != l.expected_flagged or g.matched_note_id != l.expected_note_id:
            miss.append((l.route, l.week_of))
    check("3. hand-labeled verdicts", not miss, f"{len(lab)-len(miss)}/{len(lab)} correct {miss or ''}")
    cited = out[out.matched_note_id != ""]
    check("3b. every justified row cites a note whose id appears in its reason",
          all(r.matched_note_id in r.reason for r in cited.itertuples()))

    # 4. exhaustive sweep: note x route x week vs hand-read validity
    nl = pd.read_csv(ROOT / "eval" / "labels_notes.csv", keep_default_na=False)
    truth = set()
    weeks = sorted(table.week_of.unique())
    routes = sorted(table.route.unique())
    for l in nl.itertuples():
        if l.can_justify_a_rise != "yes":
            continue
        a, b = date.fromisoformat(l.valid_from), date.fromisoformat(l.valid_to)
        for rt in routes:
            if l.scope not in ("All Routes", rt):
                continue
            for w in weeks:
                wd = pd.Timestamp(w).date()
                if wd <= b and wd + timedelta(days=6) >= a:
                    truth.add((l.note_id, rt, wd))
    for label, own, peer in [("small rise (+6%/+6%)", 0.06, 0.06), ("large rise (+30%/+30%)", 0.30, 0.30)]:
        pred = {(n.note_id, rt, pd.Timestamp(w).date()) for n in notes for rt in routes for w in weeks
                if verify(n, rt, pd.Timestamp(w), own, peer).ok}
        # With a large rise the diesel note (5-7%) must NOT explain it; N001/N002 have no size cap.
        expect = truth if own < 0.1 else {t for t in truth if t[0] != "N003"}
        check(f"4. exhaustive sweep, {label}", pred == expect,
              f"{len(pred)} (note,route,week) justifications; false+={len(pred-expect)} missed={len(expect-pred)}")

    # 4b. retrieval recall: no note that would verify is lost by the top-K cutoff
    from costwatch.retrieval import NoteRetriever
    rt = NoteRetriever(notes)
    lost = []
    for r in metrics.candidates(table).itertuples():
        full = {n.note_id for n in notes if verify(n, r.route, r.week_of, r.vs_own, r.vs_peers).ok}
        topk = {n.note_id for n in rt.top_k(r.route, r.week_of) if verify(n, r.route, r.week_of, r.vs_own, r.vs_peers).ok}
        if full != topk:
            lost.append((r.route, str(r.week_of.date())))
    check("4b. retrieval top-K loses no verifiable note (recall vs checking all notes)", not lost, str(lost or ""))

    # 5. leave-one-out
    flips = []
    for r in cited.itertuples():
        reduced = [n for n in notes if n.note_id != r.matched_note_id]
        out2, _ = pipeline.run(notes=reduced)
        row = out2[(out2.route == r.route) & (out2.week_of == r.week_of)].iloc[0]
        flips.append(row.flagged == "Yes" and row.matched_note_id == "")
    check("5. removing the cited note flips every justified row to unexplained", all(flips),
          f"{sum(flips)}/{len(flips)}")
    others = out[out.matched_note_id != ""]
    keep = [n for n in notes if n.note_id in set(others.matched_note_id)]
    out3, _ = pipeline.run(notes=keep)
    check("5b. removing all NON-cited notes changes no verdict (no spurious dependence)",
          out3[["route", "week_of", "flagged", "matched_note_id"]].equals(
              out[["route", "week_of", "flagged", "matched_note_id"]]))

    # 6. threshold sensitivity (informational)
    print("\n6. Threshold sensitivity (own-rise >=, peer-gap >=) -> rows flagged / unexplained / justified")
    core = set(zip(out.route, out.week_of))
    saved = (config.OWN_RISE_MIN, config.PEER_GAP_MIN)
    try:
        for o, p in [(0.05, 0.10), (0.07, 0.15), (0.10, 0.20), (0.15, 0.20), (0.20, 0.20)]:
            config.OWN_RISE_MIN, config.PEER_GAP_MIN = o, p
            o2, _ = pipeline.run()
            n_y = int((o2.flagged == "Yes").sum())
            keepers = len([k for k in zip(o2.route, o2.week_of) if k in core])
            print(f"   own>={o:.0%} peer>={p:.0%}: {len(o2):2d} rows | unexplained {n_y:2d} | "
                  f"justified {len(o2)-n_y} | overlap with chosen set {keepers}")
    finally:
        config.OWN_RISE_MIN, config.PEER_GAP_MIN = saved

    print(f"\n{sum(RESULTS)}/{len(RESULTS)} checks passed")
    sys.exit(0 if all(RESULTS) else 1)


if __name__ == "__main__":
    main()
