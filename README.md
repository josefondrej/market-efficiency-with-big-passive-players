# 📈 Market efficiency with big passive players

An interactive **agent-based stock-market simulation** that explores what happens
to price discovery and market efficiency as large, price-insensitive **passive
index funds** come to dominate, a few **active sophisticated investors** do the
real price discovery, a crowd of **retail "dumb money"** chases momentum, and a
handful of **manipulators** cheat (pump-and-dump, spoofing, insider trading, wash
trading).

Companies are real economic objects: each one's **true value is the discounted
value of its future cash flows** (a Gordon-growth DCF). The market **clears**
every period — the price moves to where total demand meets the fixed share
supply — so prices settle at supply = demand instead of drifting arbitrarily.

The dashboard focuses on **how efficient the market is**, and on what the **index
funds** end up holding versus what those companies are actually worth.

![tabs: Efficiency · Index funds · Who profits · Single stock](https://img.shields.io/badge/Streamlit-app-FF4B4B)

---

## The experiment

The headline question: *does a market dominated by passive funds price companies
correctly?*

Try it: in the sidebar, shrink the **Active / sophisticated** slice and grow
**Passive** + **Retail**. With little informed capital left to arbitrage prices
toward fundamentals:

- **mispricing rises** (|price − fair value| / fair value),
- the **price–value correlation falls** (worse price discovery),
- the **index drifts away from fair value** — a valuation gap passive holders
  inherit without choosing any of it.

Then toggle the **🕵️ Cheating toolkit** on and off and watch the *Who profits*
tab: manipulation typically transfers wealth from retail "dumb money" to the
manipulators, while passive funds are mostly bystanders.

---

## Is any of this real? (the literature)

The simulation is a stylised cartoon, but the forces it models are studied
extensively. A grounded, cited review lives in
**[`docs/literature-and-market-context.md`](docs/literature-and-market-context.md)**.
The short version:

- **"Dumb money" is real and well established.** Retail / mutual-fund flows
  chase past performance and underperform through bad timing
  (Frazzini & Lamont 2008; Barber & Odean 2000). The *direction* is rock-solid;
  the precise *magnitude* is contested.
- **Passive investing genuinely lowers price informativeness and raises
  comovement/volatility at the margin** (Grossman–Stiglitz's free-rider logic;
  causal evidence from index-inclusion studies) — but the effects are modest, and
  the **"index effect" has actually *disappeared*** over time
  (Greenwood & Sammon), which cuts against the strong "passive is breaking
  markets" claim.
- **Today (2024):** passive overtook active at **>50% of US fund assets**, and the
  S&P 500 is at **record concentration** (the "Magnificent Seven" ≈ 30–35% of the
  index). Whether this makes markets *fragile to a flow reversal* is the main
  open debate — not a settled fact.

See the doc for the full discussion, the established-vs-contested breakdown, and
references.

---

## Run it locally

```bash
pip install -r requirements.txt
streamlit run app.py
```

Then open http://localhost:8501.

You can also use the engine headlessly:

```python
from simulation import SimulationConfig, run_simulation, summary
r = run_simulation(SimulationConfig(passive_share=0.7, active_share=0.05))
print(summary(r))
```

---

## Deploy it for free (Streamlit Community Cloud)

1. Push this repo to GitHub (already done if you're reading this there).
2. Go to **https://share.streamlit.io** and sign in with GitHub.
3. Click **Create app → Deploy a public app from GitHub**.
4. Pick this repository, branch **`claude/stock-market-sim-jftam1`** (or `main`
   once merged), and set **Main file path** to **`app.py`**.
5. Click **Deploy**. The first build installs `requirements.txt` (a minute or
   two); after that it's live at a public `*.streamlit.app` URL you can share.

No secrets, API keys, or paid services are required — the whole simulation runs
in the app process.

---

## What the model does

> **For the full, code-level description** — the period-by-period loop, the exact
> demand rule for every player, the cheating state machine, and the price-clearing
> math — see **[`docs/simulation-design.md`](docs/simulation-design.md)**. The
> summary below is the short version.

| Player | Behaviour |
| --- | --- |
| **Passive index funds** | Hold the whole market by capitalisation weight, completely price-insensitive. Buy a stock simply because money flowed in and it's in the index. |
| **Retail / dumb money** | Chase momentum and trade noisily; panic on crashes; swayed by manipulation hype, spoofed order flow and inflated (wash-trade) volume. |
| **Active / sophisticated** | Estimate intrinsic value (with error) and want more of a stock the cheaper it is vs. value. Their downward-sloping demand is what pins prices to fundamentals. |
| **Manipulators** | Trade like active investors but also *cheat* (pump-and-dump, spoofing, insider trading, wash trading). |

**Fundamentals.** Each company's cash flow follows a stochastic process with
occasional jumps. Intrinsic value = Gordon-growth DCF discounted at
*risk-free rate + equity risk premium*, so raising rates lowers every valuation.

**Price formation.** Share supply is fixed; each period a price vector is found
by tâtonnement where aggregate desired holdings equal supply. A structural
**corporate anchor** issues shares when a stock is overvalued and buys them back
when cheap, so prices stay finite even when informed capital is scarce.

**The cheating toolkit.**
- **Pump-and-dump** — quietly accumulate a target, blast hype to lure retail
  FOMO, then dump the position into the buying.
- **Spoofing** — post fake order flow that momentum traders react to.
- **Insider trading** — peek at the next fundamental shock one period early.
- **Wash trading** — generate fake volume that makes a stock look hot.

### Exposed parameters

Everything is tunable in the sidebar: number of companies and periods, the
capital split and head-count of each player type, risk-free rate, equity risk
premium, earnings growth and volatility, fundamental-shock frequency, fund-flow
rate and how much of it goes to passive, retail momentum/noise, active
aggressiveness/leverage/estimation error, the corporate valuation anchor, price
noise, and each manipulation tactic with its strength.

---

## Caveats

This is a **stylised teaching model, not a calibrated forecast**. In particular,
sophisticated investors' *compounded* returns over long runs are exaggerated
(there is no funding risk or risk of ruin), so treat the cross-type return
comparison as qualitative. The value of the model is in the *relationships* it
makes visible — how efficiency and the index's valuation gap respond to the mix
of players and to cheating.

## Project layout

```
app.py                 Streamlit dashboard
simulation/
  config.py            All tunable parameters (SimulationConfig)
  fundamentals.py      Cash flows + DCF intrinsic value
  agents.py            Passive / retail / active / manipulator + corporate anchor
  engine.py            Market-clearing loop and history/metrics recording
  metrics.py           Summary numbers and the performance table
tests/test_engine.py   Invariants (no NaNs, efficiency responds to player mix)
```
