# Freight Tiger – Shipping Cost Watch (AI Intern case study)

Flags routes whose cost per tonne-km is rising in a way that looks unjustified, then checks a small
set of context notes (retrieval + strict verification) to say, in plain English, whether there is a
real reason. **Every number, flag and cited note is deterministic; no LLM is called.**

## Run it
```bash
pip install -r requirements.txt          # pandas, numpy, scikit-learn
python run.py                            # -> outputs/output.csv, outputs/cost_log.json
python -m unittest discover -s tests     # 11 unit tests
python eval/run_eval.py                  # 11 trust checks + threshold sensitivity
./scripts/repro_check.sh                 # 3 fresh runs, byte-identical diff
python ask.py "why did Chennai-Bangalore get pricier in March?"   # stretch goal
```

## How it works
```
shipment_records.csv ─► weekly cost/tonne-km per route ─► 2 baselines ─► candidate rows
                                                                              │
context_notes.csv ─► parse each note into facts ─► TF-IDF retrieve top-5 ─► strict verifier ─► CSV
```
1. **Weekly metric** (`costwatch/metrics.py`): group by `route` (origin-destination) and `route_type`,
   Monday-Sunday weeks (`week_of` = Monday), `cost_per_tonne_km = Σcost / Σ(tonnes × km)`.
2. **Baselines, exactly as specified**
   - *vs own history*: mean of the route's weekly values over the trailing 8 calendar weeks **strictly before**
     the current week. If fewer than 8 prior weeks exist, all available prior weeks are used (no padding or
     extrapolation); the row's `reason` then says how many were available. (In this dataset every route has
     all 104 weeks, so this only matters for a week-1..7 row, and none of those are flagged.)
   - *vs similar routes*: same-week mean over the **other** routes with the same `route_type` (self excluded).
3. **Flag rule**: a route-week is reported when it is rising vs its own history (≥ +7%) **and** out of line with
   similar-length routes (≥ +15%). Both must hold: "rising" alone is noisy; "above peers" alone just
   means an expensive route. Only such rows are written to the CSV (the sample output also lists only flagged / justified rows).
4. **Retrieval** (`retrieval.py`): TF-IDF (1-2 grams) cosine similarity between a query built from the
   route + month and each note (note text + `applies_to` + months). It ranks the top 5; ties break on note id.
5. **Verification** (`verdict.py`): a note justifies a rise only if **all four** hold:
   scope (applies to this route / All Routes) → effect (note says costs went *up*) → window (note's dates
   overlap the Mon-Sun week) → magnitude (if the note states a size, the observed rise must not be far
   larger; an All-Routes cause also moves peers, so a large gap vs peers isn't explained by it).
   Otherwise the row is `Yes` (unexplained) with a reason that names the closest notes and exactly why
   each one fails; with no nearby note it says "No matching note found…". It never guesses.
6. **Note parsing** (`notes.py`): regex/lexicon extraction of window, effect ("raises" vs "no cost effect"
   e.g. *not significantly affected, returned to normal, absorbed, not part of this dataset*) and
   magnitude. Anything unparseable falls back to the conservative reading, so a note can fail to justify
   but not justify by accident. "Starting this week" (diesel, N003) is treated as an open-ended shift that
   stops explaining a rise after 8 weeks, when it has been absorbed into the trailing baseline.

## Results (this dataset)
13 rows: 3 justified, 10 unexplained.

| Route | Week(s) | Verdict | Why |
|---|---|---|---|
| Delhi-Jaipur | 2024-11-11, 11-18 | Unexplained | no note covers it |
| Ahmedabad-Mumbai | 2025-01-20 | Justified, N002 | festival-week surcharge, same week |
| Chennai-Bangalore | 2025-02-24, 03-03 | Justified, N001 | flood window Feb 24-Mar 8 |
| Chennai-Bangalore | 2025-03-10, 03-17 | Unexplained | flood over; N009 says back to normal, yet cost stays ~+14-22% |
| Mumbai-Pune | 2025-09-15 → 12-08 (6 weeks) | Unexplained | slow creep; only nearby notes (N006, N010) say *no* cost effect |

Decoys handled: N004 (toll plaza, routes not in dataset), N005/N006/N007/N008/N010 (say no cost effect),
N009 (conditions normal), N003 (diesel +5-7% cannot explain a +25-35% jump).

## How I convinced myself it is right (`eval/run_eval.py`)
| Check | Result |
|---|---|
| Output columns/order identical to `sample_output_format_v2.csv`; `matched_note_id` blank iff unexplained | pass |
| Independent pure-Python (no pandas) recomputation of all 728 route-weeks vs the pipeline | max diff 9e-16 |
| First three sample rows (Delhi-Jaipur 4.17 / +35.5% / +21.0%, etc.) reproduce the sample's numbers | pass |
| 8 hand-labeled output rows (labels written from reading the notes, `eval/labels_outputs.csv`) | 8/8 |
| **Exhaustive sweep**: every note × 7 routes × 104 weeks vs a hand-read table of where each note is valid (`labels_notes.csv`) | 0 false justifications, 0 missed (small-rise and large-rise scenarios) |
| Leave-one-out: delete the cited note → verdict flips to unexplained | 3/3 |
| Retrieval top-5 loses no verifiable note vs checking all notes (4b) | pass |
| Delete all *non-cited* notes → no verdict changes | pass |
| Unit tests: week boundaries, formula, strict-prior history, 8-week cap, peer exclusion, wrong-route / wrong-window / "no effect" notes / magnitude | 11/11 |

**Threshold choice and sensitivity.** The 7 core anomaly rows (Delhi-Jaipur ×2, Ahmedabad, Chennai ×4) are
the weeks with ≥ +13% vs own history, the clearly separated tail (own-history deviations have std ≈ 4%,
see below). Mumbai-Pune is different: a *slow creep*, so the 8-week average chases it and its rise vs
own history is only +7-9% while the gap vs peers grows to +39%. The 7%/15% thresholds were chosen to
catch it without flagging the route's ordinary noise (its weekly values have ~8% std). **This is tuned on
this dataset**; the eval prints the flag count at other thresholds (5%/10% → 23 rows, 10%/20% → 6 rows,
15%/20% → 5 rows). The 3 justified verdicts are identical at every threshold.

## Reproducibility
`scripts/repro_check.sh` runs the program 3 times in separate processes. All three outputs are
byte-identical (same SHA-256, see `outputs/repro/checksums.txt`) – flags, numbers, cited notes **and**
reason text, since nothing is random or LLM-generated. Sorting is explicit at every step (rows by week/route,
retrieval ties by note id) so there is no dependence on hash or iteration order.

## Cost of running it (`outputs/cost_log.json`)
| LLM calls | Input tokens | Output tokens | Cost |
|---|---|---|---|
| 0 | 0 | 0 | $0.00 (< 1 s of CPU; TF-IDF is local) |

## Design trade-offs and honest limitations
- **Why no LLM.** The brief's hardest tests are reproducibility and "no confident wrong reason". With 10 notes
  the verdict is a checkable function of scope, effect, window and magnitude, so code does it more reliably,
  at zero cost. The retrieval stage is classic IR (TF-IDF), not a neural vector DB: simple, offline, deterministic.
- **Where an LLM would plug in:** (a) replace the regex note parser with a temperature-0 extractor emitting
  the same structured fields (cached per note → ~10 calls total, not per row), and (b) rephrase `reason`
  text. The verifier would still gate the verdict, so cited note/verdict/numbers could not change.
  A neural embedding model would replace TF-IDF in `retrieval.py` only; check 4b in the eval confirms top-5 loses no verifiable note on this data.
- **Parser is lexicon-based.** It is accurate on these 10 notes (verified by the sweep) but a new phrasing
  ("costs climbed") would be classed "unknown" → conservatively *not* justifying. That fails safe, but it can
  miss a real explanation.
- **Labels are mine.** The hand labels were written by the same person who wrote the code (from reading the
  notes), so the eval catches implementation bugs, not a mistaken reading of a note. Independent labels would be stronger.
- **Open-ended diesel window** (8 weeks) and the +3pp magnitude tolerance are judgment calls, documented in `config.py`.
- **Direction matters:** routes are directional (Mumbai-Pune ≠ Pune-Mumbai), as in the data.
- Weeks with no shipments are skipped, not zero-filled (none occur in this data).

## Layout
```
run.py  ask.py  requirements.txt  README.md
costwatch/  config.py metrics.py notes.py retrieval.py verdict.py pipeline.py qa.py
tests/      test_metrics.py test_verdict.py
eval/       run_eval.py labels_outputs.csv labels_notes.csv
data/       shipment_records.csv context_notes.csv sample_output_format_v2.csv
outputs/    output.csv cost_log.json repro/ (3 runs + checksums)
scripts/    repro_check.sh
```
