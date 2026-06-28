# How the simulation works

A precise, code-level description of the model: the world, the price mechanism,
and exactly how each player decides what to hold. Everything here matches the
code in [`simulation/`](../simulation); parameter names are the fields of
[`SimulationConfig`](../simulation/config.py).

---

## One period at a glance

Each trading period (≈ one day; 252 = one year) runs in this order
([`engine.py`](../simulation/engine.py), `run_simulation`):

1. **Fundamentals advance.** Cash flows move; a fundamental shock may become
   public. Insiders were allowed to see it one period early.
2. **Capital flows in.** A steady external inflow is added, mostly to passive
   funds.
3. **Manipulators act.** They advance their schemes and emit hype / spoof / wash
   signals into the market.
4. **Players fix their signals.** Retail computes its target weights; active
   investors form their (noisy) value estimates.
5. **The market clears.** A price vector is found where total desired holdings
   equal the fixed share supply (tâtonnement). Then a little idiosyncratic noise
   is added.
6. **Trades settle.** Every player moves to its desired holding at the clearing
   price, paying a transaction cost. History and efficiency metrics are recorded.

The central design choice is **step 5: market clearing.** Share supply is fixed,
so prices can't drift arbitrarily — they settle where demand meets supply. When
price-insensitive money (passive + retail) bids against a fixed float, the price
rises until value investors are willing to sell/short enough to clear. That
balance between *uninformed flow* and *informed capital* is what the whole model
is about.

---

## The world: companies and their true value

Each company has a **true (intrinsic) value equal to the discounted value of its
future cash flows** ([`fundamentals.py`](../simulation/fundamentals.py)).

- Each company `i` has an expected annual growth rate
  `gᵢ ~ Normal(mean_earnings_growth, growth_dispersion)`, clipped to stay safely
  below the discount rate.
- The **discount rate** is `risk_free_rate + equity_risk_premium`.
- Intrinsic value is a **Gordon-growth DCF**:

  ```
  Vᵢ = cash_flowᵢ · (1 + gᵢ) / (discount_rate − gᵢ)
  ```

  Raising the risk-free rate raises the discount rate and **lowers every
  valuation**, exactly as in the real world.
- **Cash flows evolve** as a geometric process with drift `gᵢ` and volatility
  `earnings_vol` (per period, `dt = 1/252`), plus occasional **jumps**: with
  probability `fundamental_shock_prob` a company gets a shock of size
  `Normal(0, fundamental_shock_size)`.
- **The insider channel:** each jump is drawn one period *before* it becomes
  public (`pending_shock`). Honest players only ever see the public value `Vᵢ`;
  insiders get to peek at the pending shock early.

Shares outstanding per company are fixed (`Uniform(0.5, 2.0) × 1,000,000`), and
initial values are spread around \$40–\$180 so prices look stock-like.

---

## Capital, initialization, and flows

- **Total capital** ≈ the total market float value × `initial_capital_multiple`,
  split across the four player types by their configured capital shares.
- **Initialization:** every agent starts ~90 % invested with a style-appropriate
  portfolio (passive holds cap-weighted, active/manipulators cap-weighted with a
  tilt, retail noisy near equal-weight) so the market opens as a going concern
  rather than an opening stampede.
- **Inflows:** each period a net external inflow of
  `net_inflow_rate × total_wealth` arrives. A fraction `passive_inflow_share`
  (default 80 %) goes to passive funds, the rest to everyone else. This steady,
  price-insensitive contribution stream is the engine of passive's rise — the
  model's version of 401(k) / target-date flows. Contributions are tracked
  separately so performance can be reported *net of money paid in*.

---

## Price formation: market clearing (tâtonnement)

Instead of a hand-tuned price-impact rule, the engine **searches for the price
that clears the market** (`_clear_price`):

```
repeat (up to 40 times):
    demand   = Σ over all players of desired_shares(price)
    excess   = (demand − shares_outstanding) / shares_outstanding
    price   *= exp(clip(0.5 · excess, −0.15, +0.15))     # raise where over-demanded
    clamp total move this period to ±max_daily_move        # soft circuit breaker
stop early once the price barely moves
```

Then a small drift-corrected idiosyncratic noise is applied
(`exp(idiosyncratic_vol·Z − ½·idiosyncratic_vol²)`) so there is no systematic
inflation from the noise term.

Because demand is **price-dependent and supply is fixed**, this converges to a
genuine supply = demand equilibrium each period. If informed capital is too thin
to provide enough price-elasticity, prices can run far from value (a bubble), but
the structural anchor below keeps them finite.

---

## The players

Every player exposes one function — `desired_shares(view, price)` — returning how
many shares of each stock it wants to hold at a hypothetical price. The clearing
loop calls this repeatedly; settlement calls it once at the final price. All four
archetypes live in [`agents.py`](../simulation/agents.py).

### 1. Passive index funds — *the big, price-blind player*

> Holds the whole market by capitalisation weight, completely price-insensitive.

- Keeps a 2 % cash buffer; deploys the rest by **market-cap weight**:

  ```
  desired_sharesᵢ = wealth · (1 − 0.02) · shares_outᵢ / Σⱼ(priceⱼ · shares_outⱼ)
  ```

- It does **no valuation** at all. It buys a stock purely because it is in the
  index and money flowed in. When inflows arrive it buys more of *everything* by
  weight, mechanically pushing extra money into whatever is already large.
- **Knobs:** its capital share, head-count (`n_passive_funds`), and how much of
  inflows it receives (`passive_inflow_share`).

### 2. Retail traders — *"dumb money"*

> Chase momentum and noise, panic on crashes, and are the prey of manipulation.

Once per period each retail trader forms a target weight per stock from a signal:

```
signal = momentum_chase  +  panic  +  manipulation  +  noise

  momentum_chase = personal_momentum · trailing_return · (1 + 0.5 · wash_volume)
  panic          = −retail_panic · max(−last_return − 0.04, 0)      # dump sharp drops
  manipulation   = personal_hype · (pump_hype + spoofed_flow)       # FOMO bait
  noise          = personal_noise · 𝒩(0,1)

weightsᵢ = clip(1 + 0.6 · signalᵢ, 0, ∞) , normalised to sum to 1
desired_sharesᵢ = 0.95 · wealth · weightsᵢ / priceᵢ
```

- They **chase trends** (buy what just went up), **panic-sell** on sharp drops,
  and are **moved by manipulation** — hype during a pump, spoofed order flow, and
  inflated (wash-trade) volume that makes a stock look hot.
- Each trader is heterogeneous: `personal_momentum`, `personal_noise` and
  `personal_hype` are randomised around the global `retail_momentum`,
  `retail_noise`, `retail_hype_susceptibility`.
- They never short and do little genuine valuation — collectively they add noise
  and are the consistent losers in the *Who profits* tab.

### 3. Active investors — *sophisticated value / price discovery*

> Want more of a stock the cheaper it is relative to its true value.

```
V̂ᵢ   = Vᵢ · (1 + estimate_bias + 𝒩(0, active_value_noise))   # noisy fair-value estimate
edgeᵢ = clip((V̂ᵢ − priceᵢ) / priceᵢ, −1, +1)                  # % mispricing they perceive
desired_valueᵢ = active_aggressiveness · edgeᵢ · wealth
   • capped per stock to ±active_max_position · wealth          # diversification limit
   • scaled so gross exposure ≤ active_max_leverage · wealth    # leverage limit
desired_sharesᵢ = desired_valueᵢ / priceᵢ
```

- Their **demand slopes downward in price**: the cheaper a stock is versus their
  estimate of value, the more they want; when it's expensive they go **short**.
  This elasticity is the force that **pins prices to fundamentals** — it's the
  "informed capital" whose share you vary to see efficiency change.
- They are imperfect: each has a standing bias plus fresh per-period estimation
  noise (`active_value_noise`), so they don't all agree and can't instantly
  arbitrage everything away.
- They pay more in **transaction costs** than passive because they trade more —
  the model's version of passive's real-world cost advantage.

### 4. Manipulators — *sophisticated players who also cheat*

> Trade like active investors, plus a toolkit of market abuse. Each tactic is
> independently toggleable.

They start from the **same value-investor book** as an active investor, then add:

- **Insider trading** (`enable_insider`): they peek at the not-yet-public
  fundamental shock and pre-position toward it:
  `+ 0.3 · wealth · insider_edge · sign(pending_shock) / price`.
- **Pump-and-dump** (`enable_pump_and_dump`): a per-stock state machine on a
  random target:

  | Phase | Length | What they do | Signals emitted to retail |
  |---|---|---|---|
  | **Accumulate** | `pump_accumulate_periods` | quietly build a long (`0.25·wealth`) | spoofed order flow |
  | **Pump** | `pump_periods` | push hard into the target (`0.5·wealth`) | full hype (`pump_hype_strength`) + spoof + wash volume |
  | **Dump** | `dump_periods` | sell the whole position into the FOMO | *lingering* hype (½) + ½ wash, so retail keeps buying while they exit |
  | **Cooldown** | `pump_cooldown_periods` | sit out, then pick a new target | — |

- **Spoofing** (`enable_spoofing`): posts fake order flow (`spoof_strength`) that
  momentum-driven retail reacts to, with no intent to trade it.
- **Wash trading** (`enable_wash_trading`): generates fake volume
  (`wash_trade_intensity`) that inflates a stock's apparent activity and amplifies
  retail's trend-chasing.

The net effect: manipulators manufacture mispricing, harvest it from retail, and
(on average across seeds) earn the highest returns — while honest active
investors also profit by trading against the distortion, and passive funds are
bystanders that inherit whatever mispricing is left behind.

### A fifth, structural participant: the corporate valuation anchor

Not a tradeable "player" you configure, but it's in the clearing
(`CorporateAnchor`). It represents **corporate finance and deep-value supply** —
companies issue shares (IPOs, secondaries, insider/option selling) when their
stock is overvalued and buy them back when it's cheap:

```
desired_sharesᵢ = −valuation_anchor · shares_outᵢ · clip(priceᵢ/Vᵢ − 1, −3, +3)
```

It supplies shares into overvaluation and absorbs them in cheapness, so the market
clears at a **finite** price even when there are almost no active investors. Set
`valuation_anchor = 0` to remove it and let markets run away when informed capital
is scarce.

---

## Settlement and accounting

- Each player moves to its `desired_shares` at the (post-noise) clearing price.
  **Passive and retail cannot short** (their holdings are floored at zero);
  **active and manipulators can**, within their leverage limit.
- Cash adjusts by the traded value, minus a **transaction cost**
  (`transaction_cost` × traded value) on every trade.
- Total shares are conserved across players + the anchor; cash is conserved except
  for external inflows and costs. **Performance is reported as final wealth per
  dollar contributed**, so it isn't flattered by money paid in.

---

## What gets measured

Recorded every period ([`engine.py`](../simulation/engine.py),
[`metrics.py`](../simulation/metrics.py)):

- **Mispricing** — cap-weighted mean of `|price − value| / value` (lower = more
  efficient).
- **Price–value correlation** — cross-sectional `corr(price, value)` (higher =
  better price discovery).
- **Index level vs. fair value** — cap-weighted price index against cap-weighted
  intrinsic value; their gap is the over/under-valuation passive holders inherit.
- **Ownership by type** and **passive ownership** over time.
- **Manipulation events** — which stock is in a pump/dump phase, for the
  per-stock chart.

---

## Limitations

This is a **stylised teaching model, not a calibrated forecast.** In particular,
sophisticated investors' *compounded* returns over long runs are exaggerated
(there's no funding risk or risk of ruin), so treat cross-type return comparisons
as qualitative. The valuable output is the **relationships** — how efficiency and
the index's valuation gap respond to the mix of players and to cheating. For how
these map onto real research, see
[`literature-and-market-context.md`](literature-and-market-context.md).
