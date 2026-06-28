"""Company fundamentals and intrinsic ("true") value.

The true price of a company is the discounted value of its future cash flows.
We model each company's cash flow as a stochastic process and compute the
intrinsic value with a Gordon-growth DCF: a stream of cash flows growing at the
company's expected rate, discounted at the risk-free rate plus an equity risk
premium. Higher interest rates therefore mechanically lower valuations, just
like in the real world.
"""
from __future__ import annotations

import numpy as np

from .config import SimulationConfig, PERIODS_PER_YEAR


class Fundamentals:
    def __init__(self, cfg: SimulationConfig, rng: np.random.Generator):
        self.cfg = cfg
        self.rng = rng
        n = cfg.n_companies

        # Per-company expected growth rates (annual), dispersed around the mean.
        self.growth = rng.normal(cfg.mean_earnings_growth, cfg.growth_dispersion, n)
        # Cap growth strictly below the discount rate so the DCF stays finite.
        self.discount_rate = cfg.risk_free_rate + cfg.equity_risk_premium
        self.growth = np.clip(self.growth, -0.05, self.discount_rate - 0.01)

        # Initial cash flow per company, chosen so initial intrinsic values are
        # spread around ~$100/share.
        target_value = rng.uniform(40, 180, n)
        gordon = (1 + self.growth) / (self.discount_rate - self.growth)
        self.cash_flow = target_value / gordon

        self.dt = 1.0 / PERIODS_PER_YEAR
        self.shares_outstanding = rng.uniform(0.5, 2.0, n) * 1_000_000

        # The fundamental shock that will become public *next* period. Insiders
        # are allowed to peek at this one period early.
        self.pending_shock = np.zeros(n)

        self.intrinsic = self._intrinsic_value()

    def _intrinsic_value(self) -> np.ndarray:
        gordon = (1 + self.growth) / (self.discount_rate - self.growth)
        return np.maximum(self.cash_flow * gordon, 1e-6)

    def step(self) -> np.ndarray:
        """Advance cash flows one period and return the public fundamental shock.

        The shock returned here is the one that becomes public *this* period;
        ``pending_shock`` holds the one insiders can already see for next period.
        """
        cfg = self.cfg
        n = cfg.n_companies

        # Realise the shock that was pending from last period (now public).
        public_shock = self.pending_shock.copy()

        # Draw next period's pending shock (insiders will see this early).
        jump = self.rng.random(n) < cfg.fundamental_shock_prob
        self.pending_shock = np.where(
            jump, self.rng.normal(0.0, cfg.fundamental_shock_size, n), 0.0
        )

        # Diffusive growth of cash flows + the now-public jump.
        drift = (self.growth - 0.5 * cfg.earnings_vol ** 2) * self.dt
        diffusion = cfg.earnings_vol * np.sqrt(self.dt) * self.rng.normal(0, 1, n)
        self.cash_flow = self.cash_flow * np.exp(drift + diffusion + public_shock)
        self.cash_flow = np.maximum(self.cash_flow, 1e-6)

        self.intrinsic = self._intrinsic_value()
        return public_shock
