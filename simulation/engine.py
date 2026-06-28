"""Simulation engine: the period-by-period market-clearing loop.

Each period:
  1. Fundamentals advance; a fundamental shock may become public. Insiders were
     allowed to see it one period early.
  2. External capital flows in (mostly to passive funds).
  3. Manipulators advance their schemes and emit hype / spoof / wash signals.
  4. Agents fix their per-period signals (momentum weights, value estimates).
  5. The market **clears**: the price vector is moved by tatonnement to the level
     where total desired holdings equal the fixed share supply. Because supply is
     fixed and demand is price-dependent, prices settle at supply=demand instead
     of drifting. Price-insensitive passive money bids prices up until value
     investors are willing to short enough to clear -- so the balance between
     "dumb"/passive flow and informed capital determines how far prices sit from
     fundamentals.
  6. Agents settle to their demand at the clearing price; history and efficiency
     metrics are recorded.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List

import numpy as np

from .config import SimulationConfig
from .fundamentals import Fundamentals
from .agents import (
    Agent, MarketView, PassiveIndexFund, RetailTrader, ActiveInvestor,
    Manipulator, CorporateAnchor, build_population,
)

TYPES = ["passive", "retail", "active", "manipulator"]


@dataclass
class SimulationResult:
    cfg: SimulationConfig
    prices: np.ndarray
    intrinsic: np.ndarray
    cap_weights: np.ndarray
    volume: np.ndarray
    wealth_by_type: Dict[str, np.ndarray] = field(default_factory=dict)
    contributed_by_type: Dict[str, np.ndarray] = field(default_factory=dict)
    ownership_by_type: Dict[str, np.ndarray] = field(default_factory=dict)
    mispricing: np.ndarray = None
    price_value_corr: np.ndarray = None
    index_nav: np.ndarray = None
    fair_index: np.ndarray = None
    passive_ownership: np.ndarray = None
    manipulation_events: List[dict] = field(default_factory=list)


def _clear_price(agents, view, start_price, shares_out, cfg,
                 iters=40, eta=0.5, max_move=None):
    """Find a price vector where aggregate demand ~ fixed supply (tatonnement)."""
    if max_move is None:
        max_move = cfg.max_daily_move
    price = start_price.copy()
    log_anchor = np.log(np.maximum(start_price, 1e-9))
    for _ in range(iters):
        demand = np.zeros_like(price)
        for a in agents:
            demand += a.desired_shares(view, price)
        excess = (demand - shares_out) / np.maximum(shares_out, 1e-9)
        step = np.clip(eta * excess, -0.15, 0.15)
        price = price * np.exp(step)
        # Bound the total per-period move (a soft circuit breaker).
        log_move = np.clip(np.log(price) - log_anchor, -max_move, max_move)
        price = np.exp(log_anchor + log_move)
        if np.max(np.abs(step)) < 1e-4:
            break
    return np.maximum(price, 0.01)


def run_simulation(cfg: SimulationConfig) -> SimulationResult:
    rng = np.random.default_rng(cfg.seed)
    n = cfg.n_companies
    T = cfg.n_periods

    fund = Fundamentals(cfg, rng)
    prices = fund.intrinsic.copy()
    shares_out = fund.shares_outstanding

    total_float_value = float(prices @ shares_out)
    total_capital = total_float_value * cfg.initial_capital_multiple
    agents = build_population(cfg, rng, total_capital)
    _seed_holdings(cfg, agents, prices, shares_out, rng)
    # The corporate/insider valuation anchor participates in clearing but is not
    # one of the reported investor archetypes.
    agents.append(CorporateAnchor(cfg, rng, 0.0))

    px_hist = np.zeros((T + 1, n)); px_hist[0] = prices
    iv_hist = np.zeros((T + 1, n)); iv_hist[0] = fund.intrinsic
    cw_hist = np.zeros((T + 1, n))
    vol_hist = np.zeros((T + 1, n))
    wealth_hist = {t: np.zeros(T + 1) for t in TYPES}
    contrib_hist = {t: np.zeros(T + 1) for t in TYPES}
    own_hist = {t: np.zeros(T + 1) for t in TYPES}
    misprice = np.zeros(T + 1)
    pv_corr = np.zeros(T + 1)
    index_nav = np.zeros(T + 1)
    fair_index = np.zeros(T + 1)
    passive_own = np.zeros(T + 1)
    events: List[dict] = []

    momentum = np.zeros(n)
    last_returns = np.zeros(n)
    market_cap = prices * shares_out
    cap_weights = market_cap / market_cap.sum()

    manipulators = [a for a in agents if isinstance(a, Manipulator)]
    passives = [a for a in agents if isinstance(a, PassiveIndexFund)]

    def record(t):
        cw = (prices * shares_out)
        cw = cw / cw.sum()
        cw_hist[t] = cw
        index_nav[t] = float(cw @ prices)
        fair_index[t] = float(cw @ fund.intrinsic)
        misprice[t] = float(cw @ (np.abs(prices - fund.intrinsic) /
                                  np.maximum(fund.intrinsic, 1e-6)))
        if np.std(prices) > 0 and np.std(fund.intrinsic) > 0:
            pv_corr[t] = float(np.corrcoef(prices, fund.intrinsic)[0, 1])
        for typ in TYPES:
            members = [a for a in agents if a.type_name == typ]
            wealth_hist[typ][t] = sum(a.wealth(prices) for a in members)
            contrib_hist[typ][t] = sum(a.contributed for a in members)
            held = sum((a.shares for a in members), np.zeros(n)) if members else np.zeros(n)
            own_hist[typ][t] = float(np.sum(np.clip(held, 0, None)) / np.sum(shares_out))
        passive_own[t] = own_hist["passive"][t]

    record(0)

    for t in range(1, T + 1):
        pending = fund.pending_shock.copy()
        fund.step()

        # External inflows (mostly to passive funds).
        total_wealth = sum(a.wealth(prices) for a in agents)
        inflow = cfg.net_inflow_rate * total_wealth
        if inflow != 0 and passives:
            passive_amt = inflow * cfg.passive_inflow_share
            for a in passives:
                a.receive_flow(passive_amt / len(passives))
            rest = inflow - passive_amt
            others = [a for a in agents if not isinstance(a, PassiveIndexFund)]
            for a in others:
                a.cash += rest / len(others)
                a.contributed += rest / len(others)

        # Manipulators advance schemes and emit signals.
        hype = np.zeros(n); spoof = np.zeros(n); wash = np.zeros(n)
        for m in manipulators:
            m._insider_shock = pending if cfg.enable_insider else None
        base_view = MarketView(last_returns.copy(), momentum.copy(),
                               fund.intrinsic.copy(), shares_out,
                               hype, spoof, wash, t)
        for m in manipulators:
            m.manipulation(base_view)
            hype += m.emit_hype
            spoof += m.emit_spoof
            wash += m.emit_wash
            if m.scheme is not None and m.scheme.phase in ("pump", "dump"):
                events.append({"period": t, "stock": int(m.scheme.stock),
                               "phase": m.scheme.phase})

        view = MarketView(last_returns.copy(), momentum.copy(),
                          fund.intrinsic.copy(), shares_out, hype, spoof, wash, t)

        # Fix per-period signals for retail / active before clearing.
        for a in agents:
            if isinstance(a, RetailTrader):
                a.new_period(view)
            elif isinstance(a, ActiveInvestor):
                a.new_period(view)

        # Clear the market.
        new_prices = _clear_price(agents, view, prices, shares_out, cfg)
        # Idiosyncratic noise (drift-corrected so it adds no systematic bias).
        v = cfg.idiosyncratic_vol
        new_prices *= np.exp(v * rng.normal(0, 1, n) - 0.5 * v ** 2)
        new_prices = np.maximum(new_prices, 0.01)

        # Settle every agent to its demand at the clearing price.
        gross_volume = np.zeros(n)
        for a in agents:
            target = a.desired_shares(view, new_prices)
            target = np.nan_to_num(target, nan=0.0, posinf=0.0, neginf=0.0)
            if not a.can_short:
                target = np.clip(target, 0.0, None)
            trade = target - a.shares
            gross_volume += np.abs(trade)
            a.cash -= float(trade @ new_prices)
            a.cash -= cfg.transaction_cost * float(np.abs(trade) @ new_prices)
            a.shares = target

        gross_volume += wash * 0.05 * shares_out  # wash trades inflate apparent volume

        prices = new_prices
        ret = prices / px_hist[t - 1] - 1.0
        last_returns = ret
        momentum = 0.8 * momentum + 0.2 * ret
        market_cap = prices * shares_out

        px_hist[t] = prices
        iv_hist[t] = fund.intrinsic
        vol_hist[t] = gross_volume
        record(t)

    return SimulationResult(
        cfg=cfg, prices=px_hist, intrinsic=iv_hist, cap_weights=cw_hist,
        volume=vol_hist, wealth_by_type=wealth_hist,
        contributed_by_type=contrib_hist, ownership_by_type=own_hist,
        mispricing=misprice, price_value_corr=pv_corr, index_nav=index_nav,
        fair_index=fair_index, passive_ownership=passive_own,
        manipulation_events=events,
    )


def _seed_holdings(cfg, agents, prices, shares_out, rng):
    """Distribute the existing float among agents according to their style."""
    n = cfg.n_companies
    cap_weights = (prices * shares_out) / (prices * shares_out).sum()
    remaining = shares_out.copy().astype(float)
    total_capital = sum(a.cash for a in agents)

    for a in agents:
        if a.type_name == "passive":
            tilt = cap_weights
        elif a.type_name == "active":
            tilt = cap_weights * rng.uniform(0.7, 1.3, n)
        elif a.type_name == "manipulator":
            tilt = cap_weights * rng.uniform(0.8, 1.2, n)
        else:
            tilt = (np.ones(n) / n) * rng.uniform(0.5, 1.5, n)
        tilt = tilt / tilt.sum()
        invest = 0.9 * a.cash
        target_shares = np.minimum((invest * tilt) / prices, remaining)
        remaining -= target_shares
        a.shares = target_shares
        a.cash -= float(target_shares @ prices)
