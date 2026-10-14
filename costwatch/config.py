"""All tunable constants in one place. Nothing here is random."""
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SHIPMENTS_CSV = ROOT / "data" / "shipment_records.csv"
NOTES_CSV = ROOT / "data" / "context_notes.csv"
SAMPLE_OUTPUT_CSV = ROOT / "data" / "sample_output_format_v2.csv"
OUTPUT_CSV = ROOT / "outputs" / "output.csv"
COST_LOG_JSON = ROOT / "outputs" / "cost_log.json"

# Baselines (fixed by the brief).
HISTORY_WEEKS = 8  # trailing weeks, strictly before the current week

# Flag rule: a route-week is a candidate when it is BOTH rising vs its own
# history AND out of line with similar-length routes. Chosen from the data
# distribution (see README, "Threshold choice" + eval/sensitivity).
OWN_RISE_MIN = 0.07   # >= +7% vs own trailing average
PEER_GAP_MIN = 0.15   # >= +15% vs same-type peers in the same week

# Retrieval / verification.
RETRIEVE_TOP_K = 5
NEAR_NOTE_DAYS = 14          # a note this close to the week is worth mentioning
OPEN_ENDED_HORIZON_WEEKS = HISTORY_WEEKS  # a "starting this week" shift stops
#   explaining a rise once it is absorbed into the 8-week baseline.
MAGNITUDE_TOLERANCE_PP = 3.0  # slack (percentage points) over a note's stated max
