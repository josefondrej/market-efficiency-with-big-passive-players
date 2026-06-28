"""Streamlit dashboard for the passive-vs-active market-efficiency simulation.

Run locally:   streamlit run app.py
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from simulation import (
    SimulationConfig, run_simulation, summary, performance_table, PERIODS_PER_YEAR,
)

st.set_page_config(page_title="Market Efficiency with Big Passive Players",
                   layout="wide", page_icon="📈")

TYPE_COLORS = {
    "passive": "#2563eb", "retail": "#f59e0b",
    "active": "#16a34a", "manipulator": "#dc2626",
}
TYPE_LABELS = {
    "passive": "Passive index funds", "retail": "Retail / dumb money",
    "active": "Active (sophisticated)", "manipulator": "Manipulators",
}


@st.cache_data(show_spinner=False)
def cached_run(cfg_dict: dict):
    return run_simulation(SimulationConfig(**cfg_dict))


# --------------------------------------------------------------------------- #
#  Sidebar: all the exposed parameters                                        #
# --------------------------------------------------------------------------- #
def sidebar_config() -> SimulationConfig:
    d = SimulationConfig().to_dict()
    st.sidebar.title("⚙️ Simulation parameters")

    with st.sidebar.expander("General", expanded=True):
        d["n_companies"] = st.slider("Number of companies", 5, 80, d["n_companies"])
        d["n_periods"] = st.slider("Trading periods (≈252 = 1 yr)", 60, 756,
                                   d["n_periods"], step=12)
        d["seed"] = st.number_input("Random seed", 0, 10_000, d["seed"])

    with st.sidebar.expander("Player population (capital shares)", expanded=True):
        st.caption("How the starting capital is split between the four player "
                   "types. The values are normalised to sum to 100%.")
        p = st.slider("Passive index funds %", 0, 100, int(d["passive_share"] * 100))
        rtl = st.slider("Retail / dumb money %", 0, 100, int(d["retail_share"] * 100))
        a = st.slider("Active / sophisticated %", 0, 100, int(d["active_share"] * 100))
        m = st.slider("Manipulators (cheaters) %", 0, 30, int(d["manipulator_share"] * 100))
        tot = max(p + rtl + a + m, 1)
        d["passive_share"], d["retail_share"] = p / tot, rtl / tot
        d["active_share"], d["manipulator_share"] = a / tot, m / tot
        st.caption(f"→ normalised: passive {d['passive_share']:.0%}, retail "
                   f"{d['retail_share']:.0%}, active {d['active_share']:.0%}, "
                   f"manip {d['manipulator_share']:.0%}")
        d["n_passive_funds"] = st.slider("# passive funds", 1, 10, d["n_passive_funds"])
        d["n_retail"] = st.slider("# retail traders", 5, 120, d["n_retail"])
        d["n_active"] = st.slider("# active investors", 1, 40, d["n_active"])
        d["n_manipulators"] = st.slider("# manipulators", 0, 10, d["n_manipulators"])

    with st.sidebar.expander("Macro / fundamentals", expanded=False):
        d["risk_free_rate"] = st.slider("Risk-free rate (annual)", 0.0, 0.12,
                                        d["risk_free_rate"], 0.005)
        d["equity_risk_premium"] = st.slider("Equity risk premium", 0.0, 0.12,
                                             d["equity_risk_premium"], 0.005)
        d["mean_earnings_growth"] = st.slider("Mean earnings growth", -0.02, 0.10,
                                              d["mean_earnings_growth"], 0.005)
        d["earnings_vol"] = st.slider("Earnings volatility (annual)", 0.02, 0.50,
                                      d["earnings_vol"], 0.01)
        d["fundamental_shock_prob"] = st.slider("Fundamental shock prob / period",
                                                0.0, 0.03, d["fundamental_shock_prob"], 0.001)

    with st.sidebar.expander("Capital flows", expanded=False):
        st.caption("Steady external contributions (think 401k inflows) that go "
                   "mostly to passive funds — the engine of passive's rise.")
        d["net_inflow_rate"] = st.slider("Net inflow rate / period", 0.0, 0.005,
                                         d["net_inflow_rate"], 0.0002, format="%.4f")
        d["passive_inflow_share"] = st.slider("Share of inflows to passive", 0.0, 1.0,
                                              d["passive_inflow_share"], 0.05)

    with st.sidebar.expander("Behaviour & microstructure", expanded=False):
        d["retail_momentum"] = st.slider("Retail momentum (trend chasing)", 0.0, 4.0,
                                         d["retail_momentum"], 0.1)
        d["retail_noise"] = st.slider("Retail noise", 0.0, 2.0, d["retail_noise"], 0.1)
        d["active_aggressiveness"] = st.slider("Active aggressiveness", 0.0, 1.5,
                                               d["active_aggressiveness"], 0.05)
        d["active_value_noise"] = st.slider("Active value-estimate error", 0.0, 0.4,
                                            d["active_value_noise"], 0.01)
        d["active_max_leverage"] = st.slider("Active max leverage", 1.0, 3.0,
                                             d["active_max_leverage"], 0.1)
        d["valuation_anchor"] = st.slider("Corporate valuation anchor "
                                          "(issuance/buyback)", 0.0, 0.5,
                                          d["valuation_anchor"], 0.02)
        d["idiosyncratic_vol"] = st.slider("Idiosyncratic price noise", 0.0, 0.05,
                                           d["idiosyncratic_vol"], 0.002)

    with st.sidebar.expander("🕵️ Cheating toolkit", expanded=True):
        d["enable_pump_and_dump"] = st.checkbox("Pump & dump", d["enable_pump_and_dump"])
        d["enable_spoofing"] = st.checkbox("Spoofing (fake orders)", d["enable_spoofing"])
        d["enable_insider"] = st.checkbox("Insider trading", d["enable_insider"])
        d["enable_wash_trading"] = st.checkbox("Wash trading (fake volume)",
                                               d["enable_wash_trading"])
        d["pump_hype_strength"] = st.slider("Pump hype strength", 0.0, 6.0,
                                            d["pump_hype_strength"], 0.5)
        d["insider_edge"] = st.slider("Insider edge", 0.0, 1.0, d["insider_edge"], 0.05)

    return SimulationConfig(**d)


# --------------------------------------------------------------------------- #
#  Charts                                                                      #
# --------------------------------------------------------------------------- #
def fig_efficiency(r):
    fig = go.Figure()
    fig.add_trace(go.Scatter(y=r.mispricing * 100, name="Avg |price−value| / value (%)",
                             line=dict(color="#dc2626", width=2)))
    fig.add_trace(go.Scatter(y=r.price_value_corr * 100,
                             name="Price–value correlation (%)",
                             line=dict(color="#2563eb", width=2), yaxis="y2"))
    fig.update_layout(
        title="Market efficiency over time",
        xaxis_title="Trading period",
        yaxis=dict(title="Mispricing (%)", color="#dc2626"),
        yaxis2=dict(title="Correlation (%)", overlaying="y", side="right",
                    color="#2563eb", range=[0, 100]),
        legend=dict(orientation="h", y=1.12), height=380, margin=dict(t=60))
    return fig


def fig_index(r):
    fig = go.Figure()
    fig.add_trace(go.Scatter(y=r.index_nav, name="Index price level (what passive holds)",
                             line=dict(color="#2563eb", width=2.5)))
    fig.add_trace(go.Scatter(y=r.fair_index, name="Fair value (discounted cash flows)",
                             line=dict(color="#16a34a", width=2, dash="dash")))
    fig.update_layout(title="Index level vs. fair value",
                      xaxis_title="Trading period", yaxis_title="Cap-weighted level",
                      legend=dict(orientation="h", y=1.12), height=380, margin=dict(t=60))
    return fig


def fig_ownership(r):
    fig = go.Figure()
    for t in ["passive", "retail", "active", "manipulator"]:
        fig.add_trace(go.Scatter(y=r.ownership_by_type[t] * 100, name=TYPE_LABELS[t],
                                 stackgroup="one", line=dict(width=0.5,
                                 color=TYPE_COLORS[t])))
    fig.update_layout(title="Who owns the market (% of shares)",
                      xaxis_title="Trading period", yaxis_title="Ownership (%)",
                      legend=dict(orientation="h", y=1.15), height=360, margin=dict(t=60))
    return fig


def fig_stock(r, i):
    fig = go.Figure()
    fig.add_trace(go.Scatter(y=r.prices[:, i], name="Market price",
                             line=dict(color="#111827", width=2)))
    fig.add_trace(go.Scatter(y=r.intrinsic[:, i], name="Intrinsic (fair) value",
                             line=dict(color="#16a34a", width=2, dash="dash")))
    # Shade pump / dump windows for this stock.
    pump = [e["period"] for e in r.manipulation_events
            if e["stock"] == i and e["phase"] == "pump"]
    dump = [e["period"] for e in r.manipulation_events
            if e["stock"] == i and e["phase"] == "dump"]
    for p in pump:
        fig.add_vline(x=p, line=dict(color="rgba(220,38,38,0.25)", width=2))
    for p in dump:
        fig.add_vline(x=p, line=dict(color="rgba(37,99,235,0.25)", width=2))
    fig.update_layout(title=f"Stock #{i}: price vs fair value "
                            f"(red lines = pump, blue = dump)",
                      xaxis_title="Trading period", yaxis_title="Price",
                      legend=dict(orientation="h", y=1.12), height=380, margin=dict(t=60))
    return fig


# --------------------------------------------------------------------------- #
#  Main                                                                        #
# --------------------------------------------------------------------------- #
st.title("📈 Market efficiency with big passive players")
st.markdown(
    "An agent-based stock market. Companies have a **true value** equal to their "
    "discounted future cash flows. Four kinds of players trade them: "
    "**passive index funds** (buy the market by weight, price-blind), "
    "**retail / dumb money** (chase momentum, get manipulated), "
    "**active sophisticated investors** (arbitrage price toward value), and "
    "**manipulators** (who cheat). Each period the market *clears* — the price "
    "moves to where demand meets the fixed share supply. Use the sidebar to "
    "change the world, then watch how efficient (or not) the market becomes.")

cfg = sidebar_config()
# The simulation can take a few seconds, so only run it when the user clicks the
# button (not on every slider tweak). The first page load runs once so the
# dashboard isn't empty; after that, parameter changes wait for an explicit run.
st.sidebar.markdown("---")
run_clicked = st.sidebar.button("▶️ Run simulation", type="primary",
                                width='stretch')

if "result" not in st.session_state:
    run_clicked = True  # auto-run on first load

if run_clicked:
    with st.spinner("Simulating the market…"):
        st.session_state.result = cached_run(cfg.to_dict())
        st.session_state.ran_cfg = cfg.to_dict()

r = st.session_state.result
s = summary(r)

if st.session_state.ran_cfg != cfg.to_dict():
    st.warning("⚠️ Parameters have changed since the last run. "
               "Click **▶️ Run simulation** to update the results below.")

c1, c2, c3, c4 = st.columns(4)
c1.metric("Avg mispricing (2nd half)", f"{s['avg_mispricing']*100:.1f}%",
          help="Average |price − fair value| / fair value across stocks. Lower = "
               "more efficient.")
c2.metric("Price–value correlation", f"{s['avg_price_value_corr']*100:.0f}%",
          help="How well the cross-section of prices tracks fair value. Higher = "
               "better price discovery.")
c3.metric("Passive ownership", f"{s['passive_ownership_end']*100:.0f}%",
          delta=f"{(s['passive_ownership_end']-s['passive_ownership_start'])*100:+.0f} pts",
          help="Share of all stock owned by passive index funds, start → end.")
c4.metric("Index vs. fair value", f"{s['index_vs_fair']*100:+.1f}%",
          help="How much the index price return ran ahead of (or behind) the "
               "growth in true fair value — the valuation gap passive holders inherit.")

tab1, tab2, tab3, tab4 = st.tabs(
    ["📉 Efficiency", "🏦 Index funds", "💰 Who profits", "🔬 Single stock"])

with tab1:
    a, b = st.columns(2)
    a.plotly_chart(fig_efficiency(r), width='stretch', key="eff")
    b.plotly_chart(fig_ownership(r), width='stretch', key="own1")
    st.info("**Read the experiment:** shrink the *active / sophisticated* slice "
            "and grow *passive* + *retail*. With little informed capital to "
            "arbitrage prices toward fundamentals, mispricing rises and the "
            "price–value correlation falls — the market gets less efficient even "
            "though nothing changed about the companies themselves.")

with tab2:
    a, b = st.columns(2)
    a.plotly_chart(fig_index(r), width='stretch', key="idx")
    b.plotly_chart(fig_ownership(r), width='stretch', key="own2")
    st.markdown(
        f"The passive index funds mechanically hold the market by weight, "
        f"buying regardless of valuation. Over this run the index price moved "
        f"**{s['index_total_return']*100:+.1f}%** while true fair value moved "
        f"**{s['fair_total_return']*100:+.1f}%** — a valuation gap of "
        f"**{s['index_vs_fair']*100:+.1f}%** that passive holders are along for. "
        f"Passive ownership went from **{s['passive_ownership_start']*100:.0f}%** "
        f"to **{s['passive_ownership_end']*100:.0f}%**.")

with tab3:
    perf = pd.DataFrame(performance_table(r))
    fig = go.Figure(go.Bar(
        x=perf["Investor type"], y=perf["Total return %"],
        marker_color=["#2563eb", "#f59e0b", "#16a34a", "#dc2626"][:len(perf)],
        text=[f"{v:+.0f}%" for v in perf["Total return %"]], textposition="outside"))
    fig.update_layout(title="Total return by player type (net of contributions)",
                      yaxis_title="Return %", height=380, margin=dict(t=60))
    st.plotly_chart(fig, width='stretch', key="perf")
    st.dataframe(perf.style.format({"Wealth per $1 in": "{:.2f}",
                                    "Total return %": "{:+.1f}%"}),
                 width='stretch', hide_index=True)
    st.caption(f"{s['n_manipulation_events']} pump/dump phase-periods occurred. "
               "Turn the cheating toolkit on/off in the sidebar and compare: "
               "manipulation typically transfers wealth from retail 'dumb money' "
               "to the manipulators, while passive funds are mostly bystanders "
               "that inherit whatever mispricing the crowd leaves behind.")

with tab4:
    # Use the displayed result's stock count so this stays valid even if the
    # sidebar's company count was changed without re-running.
    i = st.slider("Pick a stock", 0, r.prices.shape[1] - 1, 0)
    st.plotly_chart(fig_stock(r, i), width='stretch', key="stock")
    st.caption("Vertical lines mark manipulation windows (red = pump, blue = dump). "
               "Watch the market price detach from the green fair-value line during "
               "a pump and snap back after the dump.")

with st.expander("ℹ️ How the model works / caveats"):
    st.markdown(
        "- **True value** = Gordon-growth DCF of each company's stochastic cash "
        "flows, discounted at *risk-free rate + equity risk premium*. Raising "
        "rates lowers every valuation, as in reality.\n"
        "- **Market clearing**: share supply is fixed; each period a price is "
        "found where total desired holdings equal supply (tâtonnement). Prices "
        "therefore settle at supply = demand rather than drifting arbitrarily.\n"
        "- **Passive** buys cap-weighted and price-blind; **retail** chases "
        "momentum/noise and is swayed by hype, spoofed flow and inflated volume; "
        "**active** investors want more of a stock the cheaper it is vs value "
        "(this elasticity is what pins prices to fundamentals); a structural "
        "**corporate anchor** issues/buys back shares with valuation, so prices "
        "stay finite even when informed capital is scarce.\n"
        "- **Cheating**: pump-and-dump (accumulate → hype → dump into FOMO), "
        "spoofing (fake order flow), insider trading (peek at the next "
        "fundamental shock), wash trading (fake volume that lures momentum).\n"
        "- **Caveats**: this is a stylised teaching model, not a calibrated "
        "forecast. Sophisticated investors' compounded returns over long runs "
        "are exaggerated (no funding/blow-up risk); treat cross-type comparisons "
        "as qualitative.\n"
        "- **Full mechanics**: the period-by-period loop and every player's exact "
        "demand rule are documented in [`docs/simulation-design.md`](https://"
        "github.com/josefondrej/market-efficiency-with-big-passive-players/blob/"
        "main/docs/simulation-design.md).\n"
        "- **The real literature**: a cited review of the 'dumb money' and "
        "passive-investing research, and where the S&P 500 stands today, is in "
        "[`docs/literature-and-market-context.md`](https://github.com/josefondrej/"
        "market-efficiency-with-big-passive-players/blob/main/docs/"
        "literature-and-market-context.md).")
