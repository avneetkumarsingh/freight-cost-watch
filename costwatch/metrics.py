"""Weekly cost-per-tonne-km and the two baselines the brief defines exactly."""
import pandas as pd

from . import config

REQUIRED = ["origin", "destination", "route_type", "quantity_tonnes",
            "distance_km", "freight_cost_inr", "shipment_date"]


def load_shipments(path=config.SHIPMENTS_CSV) -> pd.DataFrame:
    df = pd.read_csv(path, parse_dates=["shipment_date"])
    missing = [c for c in REQUIRED if c not in df.columns]
    if missing:
        raise ValueError(f"shipment file missing columns: {missing}")
    bad = (df.quantity_tonnes <= 0) | (df.distance_km <= 0) | (df.freight_cost_inr < 0)
    if bad.any():
        raise ValueError(f"{int(bad.sum())} shipment rows have non-positive quantity/distance or negative cost")
    df = df.copy()
    df["route"] = df["origin"].str.strip() + "-" + df["destination"].str.strip()
    # Monday of the week containing the shipment (weeks run Mon-Sun).
    df["week_of"] = df["shipment_date"].dt.normalize() - pd.to_timedelta(
        df["shipment_date"].dt.weekday, unit="D")
    df["tonne_km"] = df["quantity_tonnes"] * df["distance_km"]
    return df


def weekly_costs(df: pd.DataFrame) -> pd.DataFrame:
    """One row per (route, week): total cost / total (tonnes x km)."""
    g = (df.groupby(["route", "route_type", "week_of"], sort=True)
           .agg(n_shipments=("freight_cost_inr", "size"),
                cost=("freight_cost_inr", "sum"),
                tonne_km=("tonne_km", "sum"))
           .reset_index())
    g["cost_per_tonne_km"] = g["cost"] / g["tonne_km"]
    return g.sort_values(["route", "week_of"]).reset_index(drop=True)


def add_own_history(weekly: pd.DataFrame) -> pd.DataFrame:
    """Trailing 8-week mean of weekly cost/tonne-km, strictly before this week.

    Uses a calendar index so 'trailing 8 weeks' means the 8 calendar weeks
    before; weeks with no shipments are skipped (not padded). With fewer than
    8 prior weeks, all prior weeks available are used (n_prior_weeks says how many).
    """
    out = []
    for route, g in weekly.groupby("route", sort=True):
        s = g.set_index("week_of")["cost_per_tonne_km"]
        full = s.reindex(pd.date_range(s.index.min(), s.index.max(), freq="7D"))
        prior = full.shift(1).rolling(config.HISTORY_WEEKS, min_periods=1)
        g = g.copy()
        g["own_baseline"] = prior.mean().reindex(g["week_of"]).to_numpy()
        g["n_prior_weeks"] = prior.count().reindex(g["week_of"]).to_numpy()
        out.append(g)
    res = pd.concat(out).sort_values(["route", "week_of"]).reset_index(drop=True)
    res["vs_own"] = res["cost_per_tonne_km"] / res["own_baseline"] - 1
    return res


def add_peer_baseline(weekly: pd.DataFrame) -> pd.DataFrame:
    """Same-week mean over the OTHER routes sharing route_type (self excluded)."""
    w = weekly.copy()
    key = ["route_type", "week_of"]
    tot = w.groupby(key)["cost_per_tonne_km"].transform("sum")
    cnt = w.groupby(key)["cost_per_tonne_km"].transform("count")
    w["n_peers"] = cnt - 1
    w["peer_baseline"] = (tot - w["cost_per_tonne_km"]) / w["n_peers"].where(w["n_peers"] > 0)
    w["vs_peers"] = w["cost_per_tonne_km"] / w["peer_baseline"] - 1
    return w


def build_weekly_table(df: pd.DataFrame) -> pd.DataFrame:
    return add_peer_baseline(add_own_history(weekly_costs(df)))


def candidates(table: pd.DataFrame) -> pd.DataFrame:
    """Rising vs own history AND out of line with similar-length routes."""
    m = (table["vs_own"] >= config.OWN_RISE_MIN) & (table["vs_peers"] >= config.PEER_GAP_MIN)
    return table[m].sort_values(["week_of", "route"]).reset_index(drop=True)
