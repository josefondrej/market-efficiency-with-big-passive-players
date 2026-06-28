"""Market participants.

Each agent holds cash plus a vector of share holdings (one entry per company).
The market uses a **clearing** mechanism: every period the price moves to the
level where total desired holdings equal the (fixed) shares outstanding. So each
agent exposes a price-dependent demand, ``desired_shares(view, price)`` -- the
number of shares it wants to hold at a hypothetical price vector. The engine
searches for the clearing price, then settles every agent to its demand at that
price. Because share supply is fixed and demand is price-dependent, prices
cannot drift without bound: they sit where supply meets demand.

Four archetypes:

* ``PassiveIndexFund`` - holds the whole market by capitalisation weight, fully
  price-insensitive. It buys a stock simply because money came in and the stock
  is in the index. This is the "big passive player".
* ``RetailTrader`` - "dumb money": targets dollar weights driven by momentum,
  noise and panic, and is the prey of manipulation (hype / spoof / wash signals).
* ``ActiveInvestor`` - sophisticated value investor: estimates intrinsic value
  (with noise) and wants more of a stock the cheaper it is relative to value.
  Its downward-sloping demand is what anchors prices to fundamentals.
* ``Manipulator`` - a sophisticated player that also cheats: pump-and-dump,
  spoofing, insider trading and wash trading.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

import numpy as np

from .config import SimulationConfig


@dataclass
class MarketView:
    """Signals fixed at the start of a period (do not depend on the trial price
    during clearing)."""
    last_returns: np.ndarray        # most recent realised return per stock
    momentum: np.ndarray            # smoothed trailing return per stock
    intrinsic: np.ndarray           # the true value (active/manipulators estimate it)
    shares_out: np.ndarray          # shares outstanding per stock (fixed supply)
    hype_signal: np.ndarray         # manipulation-induced retail demand per stock
    fake_flow: np.ndarray           # spoofed order-flow signal per stock
    volume_signal: np.ndarray       # wash-trade-inflated apparent volume per stock
    period: int


class Agent:
    type_name = "agent"
    can_short = False

    def __init__(self, cfg: SimulationConfig, rng: np.random.Generator, capital: float):
        self.cfg = cfg
        self.rng = rng
        n = cfg.n_companies
        self.cash = capital
        self.shares = np.zeros(n)
        self.initial_capital = capital
        self.contributed = capital  # external capital put in (for honest PnL)

    def wealth(self, prices: np.ndarray) -> float:
        return self.cash + float(self.shares @ prices)

    def desired_shares(self, view: MarketView, price: np.ndarray) -> np.ndarray:
        """Shares the agent wants to hold at the given trial price."""
        return self.shares.copy()

    def manipulation(self, view: MarketView):
        return None


# ---------------------------------------------------------------------------
class PassiveIndexFund(Agent):
    type_name = "passive"

    def __init__(self, cfg, rng, capital):
        super().__init__(cfg, rng, capital)
        self.cash_buffer = 0.02

    def receive_flow(self, amount: float):
        self.cash += amount
        self.contributed += amount

    def desired_shares(self, view, price):
        wealth = self.wealth(price)
        if wealth <= 0:
            return np.zeros(self.cfg.n_companies)
        mcap = price * view.shares_out
        total = mcap.sum()
        if total <= 0:
            return np.zeros(self.cfg.n_companies)
        # Cap-weighted dollars -> shares. Price-insensitive: it holds the index.
        investable = wealth * (1.0 - self.cash_buffer)
        return investable * view.shares_out / total


# ---------------------------------------------------------------------------
class RetailTrader(Agent):
    type_name = "retail"

    def __init__(self, cfg, rng, capital):
        super().__init__(cfg, rng, capital)
        self.momentum = cfg.retail_momentum * rng.uniform(0.5, 1.5)
        self.noise_amp = cfg.retail_noise * rng.uniform(0.5, 1.5)
        self.hype = cfg.retail_hype_susceptibility * rng.uniform(0.4, 1.6)
        self._weights = None

    def _target_weights(self, view: MarketView) -> np.ndarray:
        cfg = self.cfg
        # Computed once per period (signals are price-independent within clearing).
        trend = self.momentum * view.momentum * (1.0 + 0.5 * view.volume_signal)
        panic = -cfg.retail_panic * np.clip(-view.last_returns - 0.04, 0, None)
        manip = self.hype * (view.hype_signal + view.fake_flow)
        noise = self.noise_amp * self.rng.normal(0, 1, cfg.n_companies)
        signal = trend + panic + manip + noise
        raw = np.clip(1.0 + 0.6 * signal, 0.0, None)
        s = raw.sum()
        return raw / s if s > 0 else np.ones(cfg.n_companies) / cfg.n_companies

    def new_period(self, view: MarketView):
        self._weights = self._target_weights(view)

    def desired_shares(self, view, price):
        if self._weights is None:
            self._weights = self._target_weights(view)
        wealth = max(self.wealth(price), 0.0)
        invested = 0.95 * wealth  # small cash reserve
        target_value = invested * self._weights
        return target_value / np.maximum(price, 1e-6)


# ---------------------------------------------------------------------------
class ActiveInvestor(Agent):
    type_name = "active"
    can_short = True

    def __init__(self, cfg, rng, capital):
        super().__init__(cfg, rng, capital)
        self.aggr = cfg.active_aggressiveness * rng.uniform(0.7, 1.3)
        self.estimate_bias = rng.normal(0, cfg.active_value_noise)
        self._value = None

    def new_period(self, view: MarketView):
        noise = self.rng.normal(0, self.cfg.active_value_noise, self.cfg.n_companies)
        self._value = view.intrinsic * (1.0 + self.estimate_bias + noise)

    def value_estimate(self, view):
        if self._value is None:
            self.new_period(view)
        return self._value

    def desired_shares(self, view, price):
        cfg = self.cfg
        wealth = max(self.wealth(price), 1e-6)
        value = self.value_estimate(view)
        # Downward-sloping demand: cheaper vs value -> want more (and short when
        # expensive). This elasticity is what pins prices to fundamentals.
        edge = (value - price) / np.maximum(price, 1e-6)
        edge = np.clip(edge, -1.0, 1.0)
        desired_value = self.aggr * edge * wealth
        # Risk management: cap exposure to any single name (diversification),
        # which keeps a lucky concentrated bet from compounding without bound.
        name_cap = cfg.active_max_position * wealth
        desired_value = np.clip(desired_value, -name_cap, name_cap)
        gross = np.abs(desired_value).sum()
        cap = wealth * cfg.active_max_leverage
        if gross > cap and gross > 0:
            desired_value *= cap / gross
        return desired_value / np.maximum(price, 1e-6)


# ---------------------------------------------------------------------------
@dataclass
class PumpScheme:
    stock: int
    phase: str           # "accumulate" | "pump" | "dump" | "cooldown"
    timer: int


class Manipulator(ActiveInvestor):
    """A sophisticated value investor that also cheats."""
    type_name = "manipulator"
    can_short = True

    def __init__(self, cfg, rng, capital):
        super().__init__(cfg, rng, capital)
        self.scheme: Optional[PumpScheme] = None
        self.cooldown = int(rng.integers(0, max(cfg.pump_cooldown_periods, 1)))
        self.emit_hype = np.zeros(cfg.n_companies)
        self.emit_spoof = np.zeros(cfg.n_companies)
        self.emit_wash = np.zeros(cfg.n_companies)
        self._insider_shock = None
        self._pump_target_shares = 0.0

    def manipulation(self, view: MarketView):
        cfg = self.cfg
        n = cfg.n_companies
        self.emit_hype = np.zeros(n)
        self.emit_spoof = np.zeros(n)
        self.emit_wash = np.zeros(n)

        if not cfg.enable_pump_and_dump:
            return

        if self.scheme is None:
            if self.cooldown > 0:
                self.cooldown -= 1
                return
            target = int(self.rng.integers(0, n))
            self.scheme = PumpScheme(target, "accumulate", cfg.pump_accumulate_periods)
            self._pump_target_shares = 0.0
            return

        s = self.scheme
        s.timer -= 1
        if s.phase == "accumulate":
            if cfg.enable_spoofing:
                self.emit_spoof[s.stock] = cfg.spoof_strength
            if s.timer <= 0:
                s.phase, s.timer = "pump", cfg.pump_periods
        elif s.phase == "pump":
            self.emit_hype[s.stock] = cfg.pump_hype_strength
            if cfg.enable_spoofing:
                self.emit_spoof[s.stock] = cfg.spoof_strength
            if cfg.enable_wash_trading:
                self.emit_wash[s.stock] = cfg.wash_trade_intensity
            if s.timer <= 0:
                s.phase, s.timer = "dump", cfg.dump_periods
        elif s.phase == "dump":
            # Hype lingers so retail keeps buying while the manipulator sells out.
            self.emit_hype[s.stock] = 0.5 * cfg.pump_hype_strength
            if cfg.enable_wash_trading:
                self.emit_wash[s.stock] = 0.5 * cfg.wash_trade_intensity
            if s.timer <= 0:
                s.phase, s.timer = "cooldown", cfg.pump_cooldown_periods
        elif s.phase == "cooldown":
            if s.timer <= 0:
                self.scheme = None

    def desired_shares(self, view, price):
        cfg = self.cfg
        base = super().desired_shares(view, price)
        wealth = max(self.wealth(price), 1e-6)

        # Insider front-running of the pending (not-yet-public) fundamental shock.
        if cfg.enable_insider and self._insider_shock is not None:
            tilt = cfg.insider_edge * np.sign(self._insider_shock)
            tilt = np.where(np.abs(self._insider_shock) > 1e-9, tilt, 0.0)
            base = base + (0.3 * wealth * tilt) / np.maximum(price, 1e-6)

        if self.scheme is None:
            return base

        s = self.scheme
        i = s.stock
        px = max(price[i], 1e-6)
        if s.phase in ("accumulate", "pump"):
            # Build a concentrated long in the target on top of the value book.
            target_dollars = (0.5 if s.phase == "pump" else 0.25) * wealth
            base[i] = base[i] + target_dollars / px
        elif s.phase == "dump":
            # Offload the position into the lingering hype.
            base[i] = min(base[i], 0.0)
        return base


class CorporateAnchor(Agent):
    """Structural, valuation-elastic supply: companies / insiders issue shares
    when their stock is overvalued and buy it back when it is cheap. Capital-
    unconstrained and always present, it is the backstop that keeps prices from
    detaching without bound when informed capital is scarce. It is NOT counted as
    an investor archetype in the reported populations -- it represents corporate
    finance / deep-value supply, not a trading player."""
    type_name = "anchor"
    can_short = True

    def desired_shares(self, view, price):
        strength = self.cfg.valuation_anchor
        if strength <= 0:
            return np.zeros(self.cfg.n_companies)
        gap = np.clip(price / np.maximum(view.intrinsic, 1e-6) - 1.0, -3.0, 3.0)
        # Overvalued (gap>0) -> supply shares (negative holding); cheap -> absorb.
        return -strength * view.shares_out * gap


def build_population(cfg: SimulationConfig, rng: np.random.Generator,
                     total_capital: float) -> List[Agent]:
    shares = cfg.player_shares()
    agents: List[Agent] = []

    def split(capital, count):
        if count <= 0 or capital <= 0:
            return []
        weights = rng.uniform(0.6, 1.4, count)
        weights /= weights.sum()
        return list(capital * weights)

    for cap in split(total_capital * shares["passive"], cfg.n_passive_funds):
        agents.append(PassiveIndexFund(cfg, rng, cap))
    for cap in split(total_capital * shares["retail"], cfg.n_retail):
        agents.append(RetailTrader(cfg, rng, cap))
    for cap in split(total_capital * shares["active"], cfg.n_active):
        agents.append(ActiveInvestor(cfg, rng, cap))
    for cap in split(total_capital * shares["manipulator"], cfg.n_manipulators):
        agents.append(Manipulator(cfg, rng, cap))
    return agents
