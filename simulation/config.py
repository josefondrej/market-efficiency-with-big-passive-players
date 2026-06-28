"""Configuration for the market-efficiency simulation.

Every knob that controls the initial conditions / dynamics of the simulation
lives here so the Streamlit UI can expose them in one place.
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Dict

# Number of trading periods that make up one "year". Used to convert annual
# parameters (interest rate, growth, volatility) into per-period quantities.
PERIODS_PER_YEAR = 252


@dataclass
class SimulationConfig:
    # ----- General -----
    n_companies: int = 30
    n_periods: int = 252            # length of the run (1 trading year by default)
    seed: int = 42

    # ----- Fundamentals (the "true" world) -----
    risk_free_rate: float = 0.03    # annual, drives discounting -> valuations
    equity_risk_premium: float = 0.05  # extra discount investors demand on stocks
    mean_earnings_growth: float = 0.03  # annual expected cash-flow growth
    growth_dispersion: float = 0.02     # spread of per-company growth rates
    earnings_vol: float = 0.18      # annual volatility of cash flows
    fundamental_shock_prob: float = 0.004  # per-company per-period jump probability
    fundamental_shock_size: float = 0.20   # std-dev of a fundamental jump

    # ----- Capital & flows -----
    initial_capital_multiple: float = 1.0  # agents collectively hold this x total float value
    net_inflow_rate: float = 0.0008  # per-period external inflow as fraction of total capital
    passive_inflow_share: float = 0.80  # fraction of *new* inflows that goes to passive funds

    # ----- Player population (capital shares of the *initial* market) -----
    passive_share: float = 0.45
    retail_share: float = 0.30
    active_share: float = 0.22
    manipulator_share: float = 0.03

    # ----- Player counts (heterogeneity within each type) -----
    n_passive_funds: int = 3
    n_retail: int = 40
    n_active: int = 12
    n_manipulators: int = 3

    # ----- Microstructure / price impact -----
    idiosyncratic_vol: float = 0.012  # per-period noise on each price
    max_daily_move: float = 0.25    # circuit-breaker clamp on single-period return

    # Structural valuation anchor: real markets issue shares when a stock is
    # overvalued (IPOs, secondaries, insider/option selling) and buy them back
    # when it is cheap. This price-elastic supply keeps prices from detaching
    # without bound even if there are almost no active investors. Set to 0 to
    # remove it entirely (markets can then run away when informed capital is tiny).
    valuation_anchor: float = 0.12

    # ----- Retail / "dumb money" behaviour -----
    retail_momentum: float = 1.4    # trend-chasing strength
    retail_noise: float = 0.6       # random trading intensity
    retail_panic: float = 1.8       # extra selling pressure on sharp drops
    retail_hype_susceptibility: float = 1.0  # how much manipulation signals move them

    # ----- Active / sophisticated value investors -----
    active_aggressiveness: float = 0.5   # how hard they push toward fair value
    active_value_noise: float = 0.12     # error in their intrinsic-value estimate
    active_max_leverage: float = 1.3     # gross exposure cap (allows some shorting)
    active_max_position: float = 0.20    # max exposure to a single stock (risk limit)

    # Per-trade transaction cost (fraction of traded value). Charged on turnover,
    # so high-churn active traders pay more and low-turnover passive funds enjoy
    # their real-world cost advantage.
    transaction_cost: float = 0.0005

    # ----- Manipulation toolkit (the "cheating") -----
    enable_pump_and_dump: bool = True
    enable_spoofing: bool = True
    enable_insider: bool = True
    enable_wash_trading: bool = True

    pump_accumulate_periods: int = 8
    pump_periods: int = 6
    dump_periods: int = 4
    pump_cooldown_periods: int = 20
    pump_hype_strength: float = 3.0      # how much a pump inflates retail demand
    spoof_strength: float = 1.2          # fake order-flow signal size
    insider_edge: float = 0.7            # fraction of a fundamental shock seen early
    wash_trade_intensity: float = 1.5    # fake volume multiplier that lures momentum

    def player_shares(self) -> Dict[str, float]:
        raw = {
            "passive": self.passive_share,
            "retail": self.retail_share,
            "active": self.active_share,
            "manipulator": self.manipulator_share,
        }
        total = sum(raw.values()) or 1.0
        return {k: v / total for k, v in raw.items()}

    def to_dict(self) -> dict:
        return asdict(self)
