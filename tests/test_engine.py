"""Invariant / sanity tests for the simulation engine.

Run with:  python -m pytest -q   (or just  python tests/test_engine.py)
"""
import numpy as np

from simulation import SimulationConfig, run_simulation


def test_runs_and_is_finite():
    r = run_simulation(SimulationConfig(n_periods=120, seed=1))
    assert r.prices.shape == (121, 30)
    assert np.isfinite(r.prices).all()
    assert (r.prices > 0).all()
    assert np.isfinite(r.intrinsic).all()


def test_no_runaway_inflation_when_balanced():
    # With a healthy slice of informed capital, prices should track fair value:
    # the index must not detach by more than a sane factor.
    r = run_simulation(SimulationConfig(n_periods=252, seed=2))
    ratio = r.index_nav[-1] / r.fair_index[-1]
    assert 0.5 < ratio < 2.0, ratio
    assert r.mispricing[126:].mean() < 0.30


def test_efficiency_degrades_as_active_shrinks():
    """The core thesis: replacing informed active capital with price-insensitive
    passive money should (weakly) raise average mispricing."""
    def mispricing(passive, active):
        cfg = SimulationConfig(n_periods=200, seed=7, passive_share=passive,
                               retail_share=0.35, active_share=active,
                               manipulator_share=0.03)
        return run_simulation(cfg).mispricing[100:].mean()

    healthy = mispricing(passive=0.10, active=0.52)
    starved = mispricing(passive=0.59, active=0.03)
    assert starved > healthy, (healthy, starved)


def test_cheating_helps_manipulators_and_hurts_retail():
    """Averaged over seeds, enabling the cheating toolkit should raise
    manipulators' returns and lower retail's."""
    def avg(enable):
        ov = dict(enable_pump_and_dump=enable, enable_spoofing=enable,
                  enable_insider=enable, enable_wash_trading=enable)
        man, ret = [], []
        for s in range(20, 28):
            r = run_simulation(SimulationConfig(n_periods=200, seed=s, **ov))
            man.append(r.wealth_by_type["manipulator"][-1] /
                       r.contributed_by_type["manipulator"][-1])
            ret.append(r.wealth_by_type["retail"][-1] /
                       r.contributed_by_type["retail"][-1])
        return np.mean(man), np.mean(ret)

    man_on, ret_on = avg(True)
    man_off, ret_off = avg(False)
    assert man_on > man_off, (man_on, man_off)
    assert ret_on < ret_off, (ret_on, ret_off)


if __name__ == "__main__":
    test_runs_and_is_finite()
    test_no_runaway_inflation_when_balanced()
    test_efficiency_degrades_as_active_shrinks()
    test_cheating_helps_manipulators_and_hurts_retail()
    print("all tests passed")
