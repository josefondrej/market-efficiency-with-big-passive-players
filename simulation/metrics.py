"""Derived metrics and summaries on top of a SimulationResult."""
from __future__ import annotations

import numpy as np

from .engine import SimulationResult, TYPES


def summary(r: SimulationResult) -> dict:
    """Headline numbers for the dashboard, using the second half of the run as
    the 'settled' regime."""
    half = r.cfg.n_periods // 2
    out = {
        "avg_mispricing": float(np.mean(r.mispricing[half:])),
        "final_mispricing": float(r.mispricing[-1]),
        "avg_price_value_corr": float(np.mean(r.price_value_corr[half:])),
        "index_total_return": float(r.index_nav[-1] / r.index_nav[0] - 1.0),
        "fair_total_return": float(r.fair_index[-1] / r.fair_index[0] - 1.0),
        "passive_ownership_start": float(r.passive_ownership[0]),
        "passive_ownership_end": float(r.passive_ownership[-1]),
        "n_manipulation_events": len(r.manipulation_events),
    }
    # Index over/under-valuation vs fair value (the cost passive holders pay).
    out["index_vs_fair"] = out["index_total_return"] - out["fair_total_return"]
    return out


def performance_table(r: SimulationResult) -> list[dict]:
    """Final wealth per dollar contributed, per investor type (>1 = made money)."""
    rows = []
    label = {"passive": "Passive index funds", "retail": "Retail / dumb money",
             "active": "Active (sophisticated)", "manipulator": "Manipulators (cheaters)"}
    for t in TYPES:
        contributed = r.contributed_by_type[t][-1]
        wealth = r.wealth_by_type[t][-1]
        if contributed <= 0:
            continue
        rows.append({
            "Investor type": label[t],
            "Wealth per $1 in": wealth / contributed,
            "Total return %": (wealth / contributed - 1.0) * 100.0,
        })
    return rows
