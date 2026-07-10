# Understanding and Using the App

## Purpose and Intended Use

The Monte Carlo Retirement Planner (`myfinmodel`) stress-tests a retirement spending plan across many possible market and inflation paths. The simulator runs 100 to 10,000 independent paths over your selected planning horizon, applies configurable guardrails, and reports portfolio survival, spending behavior, withdrawal-rate pressure, and guardrail activity.

This tool is built for planning and scenario analysis, not prediction. Use it to compare tradeoffs (spending, allocation assumptions, guardrails, Social Security timing), not to treat any one run as a guaranteed forecast.

> [!WARNING]
> ## Disclaimer
> This Monte Carlo Retirement Planning Model is provided for EDUCATIONAL AND PLANNING PURPOSES ONLY. It is NOT financial advice, investment advice, tax advice, or legal advice. All projections are hypothetical and based on assumptions that may not reflect future market conditions. Past performance of investment markets does not guarantee future results. Actual outcomes will differ, possibly significantly, from modeled projections. Monte Carlo simulation cannot predict sequence-of-returns risk, legislative changes, health emergencies, or personal circumstances that may materially affect your financial situation.
>
> **Consult a qualified professional:** Work with a Certified Financial Planner (CFP), Certified Public Accountant (CPA), or other licensed professional before making major financial decisions based on this model. ACA subsidy eligibility, tax treatment of withdrawals, and Social Security claiming strategy should be reviewed annually and verified with current law.

## Recommended Workflow

1. Enter or load a scenario on the Inputs tab.
2. Confirm validation messages are clear of blocking errors.
3. Click `Run Simulation` in the sidebar.
4. Review dashboard cards first, then tab-level charts/tables.
5. Save scenarios and compare at least two alternatives before deciding on changes.

## Section 1: Input Parameters Reference

### 1.1 Portfolio

- **Starting Portfolio Value ($):** Total investable assets at retirement start.
- **Taxable Account ($):** Brokerage assets.
- **Tax-Deferred - IRA/401k ($):** Pre-tax retirement assets.
- **Roth ($):** Tax-free assets.
- **Unrealized Gain % (Taxable):** Embedded capital-gain share inside taxable assets.
- **LTCG Tax Rate:** Federal long-term capital gains rate used in the tax approximation.
- **Ordinary Income Tax Rate:** Marginal ordinary-income rate used for IRA/401k withdrawals.

Why these matter: Portfolio size and account mix drive sustainability, withdrawal tax drag, and guardrail frequency.

### 1.2 Personal Information

- **Current Age:** Current age for planning context.
- **Retirement Start Age:** Age withdrawals begin.
- **Filing Status:** `Single` or `Married Filing Jointly`.
- **Social Security Start Age:** Claiming age (62-70).
- **Planning Horizon (years):** Simulation length; app displays ending age.

Why these matter: Start ages and horizon materially change sequence risk and survival rate.

### 1.3 Spending

- **Spending Tiers (1-5 tiers):** Age ranges plus annual spending in real (today's) dollars.
- **Spending Floor:** Minimum spending after guardrail adjustments.
- **Spending Ceiling:** Maximum spending after guardrail adjustments.

Rules enforced by validation:

- Tiers must cover the full horizon contiguously.
- `spend_floor < spend_ceiling`.

### 1.4 Social Security

- **Enable Social Security:** Toggle SS income on/off.
- **Annual SS Benefit at Claiming Age ($):** Base annual benefit in today's dollars.
- **SS COLA Rate (%):** Annual cost-of-living adjustment applied after claiming.

### 1.5 Health Insurance

- **Medicare Start Age:** Age Medicare begins.
- **Annual Medicare Premium ($):** Annual premium in today's dollars.
- **Enable ACA MAGI Guardrail:** Enables ACA threshold/premium logic.
- **ACA MAGI Cliff ($):** Income level where ACA subsidies are lost.
- **ACA Safe Target MAGI ($):** Target income below cliff.
- **Annual Premium if Over Cliff ($):** Unsubsidized premium assumption.
- **Annual Premium if Under Cliff ($):** Subsidized premium assumption.

### 1.6 Portfolio Style and Market Assumptions

- **Portfolio Style Preset:** Conservative, Moderate, Growth, Aggressive Growth, Equity Only, or Custom.
- **Expected Annual Return (%):** Mean portfolio return.
- **Return Standard Deviation (%):** Return volatility.
- **Return-Inflation Correlation:** Correlation used in bivariate draws.
- **Inflation Mean (%), Std Dev (%), Floor (%):** Inflation distribution controls.
- **Simulation Paths:** Number of Monte Carlo paths (100-10,000).
- **Lock Random Seed / Random Seed:** Reproducibility controls.

### 1.7 Guardrail Thresholds

- **Inflation Guardrail (GR4):** Trigger rate and spending cut percent.
- **Portfolio Value Guardrail (GR1):** Floor %, ceiling %, cut %, raise %.
- **Withdrawal Rate Guardrail (GR2):** Low/warn/critical thresholds plus adjustment percents.
- **ACA MAGI Guardrail (GR3):** Enabled only when ACA guardrail is enabled in Health Insurance.

## Section 2: Guardrails Explained (Execution Order)

Guardrails are applied each year in this order:

1. GR1 (Portfolio Value)
2. GR2 (Withdrawal Rate)
3. GR3 (ACA MAGI / health-cost logic)
4. GR4 (Inflation)
5. Floor/Ceiling clamp

Only the first guardrail that triggers in a year is logged as the event code for that path-year.

### 2.1 GR1 Portfolio Value (`PV-DOWN`, `PV-UP`)

- **Trigger:** Portfolio below configured floor or above configured ceiling (as % of starting portfolio).
- **Action:** Cut spending (`PV-DOWN`) or raise spending (`PV-UP`) by configured percentages.
- **Intent:** React to major capital impairment or sustained overperformance.

### 2.2 GR2 Withdrawal Rate (`WR-LOW`, `WR-WARN`, `WR-CRIT`)

- **Trigger:** Gross withdrawal rate crosses low/warn/critical thresholds.
- **Action:** Raise or cut spending based on tier thresholds.
- **Intent:** Keep withdrawal pressure inside a sustainable band.

### 2.3 GR3 ACA MAGI (`ACA-BREACH`)

- **Scope:** Pre-Medicare years only.
- **Trigger:** Estimated MAGI breach relative to configured ACA cliff/target logic.
- **Action:** Applies ACA-related health-cost consequences and logs breach events when triggered.
- **Important:** GR3 must be enabled and ACA guardrail must also be enabled in health settings.

### 2.4 GR4 Inflation (`INF`)

- **Trigger:** Annual inflation draw exceeds configured trigger.
- **Action:** Cuts spending by configured percentage.
- **Intent:** Protect purchasing power when inflation spikes.

### 2.5 Ruin-State Override

When a path is depleted, spending is set to Social Security income only, withdrawal becomes zero, health cost is set to zero, and event code is reset to `NONE`.

## Section 3: Monte Carlo Methodology

### 3.1 Draw Process

- The engine draws annual portfolio return and inflation jointly from a bivariate normal distribution.
- Correlation is user-configured.
- Inflation draws are clipped at the inflation floor.

### 3.2 Annual Simulation Loop

For each year and each path:

1. Update cumulative inflation index.
2. Determine Social Security income (if enabled and claim age reached).
3. Determine health cost baseline (Medicare rules or pre-Medicare GR3 behavior).
4. Build base spending from age-tier schedule and inflation index.
5. Apply guardrails in fixed order, then floor/ceiling clamp.
6. Compute net and gross withdrawals (tax-adjusted approximation).
7. Update end-of-year portfolio.
8. Store portfolio, spending, withdrawal rate, inflation, health cost, and event code arrays.

### 3.3 Tax Approximation

The model uses a blended effective tax rate derived from starting account fractions and user tax-rate assumptions. It is a simplified approximation and does not model full tax-lot accounting, bracket transitions, or account depletion order dynamics.

### 3.4 Reproducibility

- If `Lock random seed` is ON, repeated runs with identical inputs are reproducible.
- If OFF, the app generates a new random seed each run.

## Section 4: Results Reference (Charts, Tables, and Exports)

### 4.1 Summary Dashboard Cards

- Full Horizon Survival Rate
- Median Final Portfolio
- 10th Percentile Final Portfolio
- 90th Percentile Final Portfolio
- Avg Spending (Surviving)
- Median Withdrawal Rate
- Active Guardrails
- Inflation Floor

Special banners:

- If survival is 0%, app shows a high-risk depletion warning.
- If survival is 100%, app shows an all-paths-survived success banner.

### 4.2 Results Tabs

- **Success Metrics:** Tabular metrics across portfolio outcomes, spending outcomes, guardrail frequencies, and withdrawal-rate statistics.
- **Portfolio:** Nominal or real percentile fan chart by age.
- **Spending:** Nominal or real spending fan chart with floor/ceiling lines.
- **Analysis:** Guardrail event chart, survival donut, inflation fan chart.
- **Tax Efficiency:** Withdrawal-rate fan/box chart with reference lines.
- **Raw Data:** Downloadable tables and optional full path export.
- **Compare:** Appears when at least two saved scenarios include results.

### 4.3 Raw Data Tables

- **Table 1 - Percentile Portfolio Paths** (Age/Year, 10/25/50/75/90th percentiles)
- **Table 2 - Percentile Spending Paths** (Age/Year, nominal percentiles, median real)
- **Table 3 - Guardrail Event Frequency** (event counts by age)
- **Table 4 - Inflation Statistics** (min, percentiles, max, median cumulative inflation)
- **Table 5 - Full Path Data Export** (Path, Age, Portfolio, Spending, WR, SS Income, Health Cost, Event Code, Cum Inflation, Real Portfolio)

### 4.4 Which Inputs Most Affect Core Outputs

- **Survival rate:** Spending tiers, starting portfolio, horizon length, return mean/std, and guardrail aggressiveness.
- **Tail outcomes (10th percentile):** Return volatility, withdrawal-rate thresholds, and spending floor.
- **Average surviving spending:** Spending tiers, floor/ceiling, GR1/GR2 settings.
- **ACA breach frequency:** ACA cliff/target settings, SS timing, account mix assumptions, and GR3 enablement.
- **Inflation-trigger events:** Inflation mean/std/floor plus GR4 trigger.

## Section 5: Interpreting Success Rate and Distribution

### 5.1 Success Rate

Success rate is the share of paths with portfolio value above zero at the end of the planning horizon.

Suggested interpretation bands:

- **>= 90%:** Strong durability under modeled assumptions.
- **80-89%:** Moderate durability; review spending flexibility.
- **70-79%:** Elevated risk; consider reducing spending or adjusting assumptions.
- **< 70%:** High depletion risk; material plan changes likely needed.

UI threshold coloring in summary cards:

- Green: `>= 85%`
- Yellow: `70% to <85%`
- Red: `<70%`

### 5.2 Distribution View

- **10th percentile:** Stress-case planning anchor.
- **Median (50th):** Typical modeled outcome.
- **90th percentile:** Favorable-path context, not a planning baseline.

Wide percentile spread indicates high sequence sensitivity and/or high return variance assumptions.

## Section 6: Verified Assumptions and Constraints

The following are aligned to current implementation:

- Returns are modeled in nominal terms; real values are derived by inflation-adjusting outputs.
- Inflation is stochastic and floored by `inf_floor`; deflation can be excluded when floor > 0.
- Social Security can be enabled/disabled and includes COLA when enabled.
- ACA behavior is simplified and controlled by user thresholds/premiums.
- RMDs are not modeled.
- State taxes are not modeled.
- Annual draws are independent year-to-year (no explicit autocorrelation/mean reversion model).
- Tax treatment is simplified via blended effective rates, not full tax simulation.
- Spending tiers must fully cover the horizon contiguously.
- `n_paths` is bounded to 100-10,000 by validation.

## Section 7: Assumptions and Limitations

- Normal return assumptions may understate tail risk and crisis clustering.
- Sequence risk is represented through random path dispersion, but no dedicated historical-regime replay is included.
- Longevity beyond the selected planning horizon is out of scope.
- Housing equity, home sale/downsize, annuitization, and other non-portfolio assets are not modeled directly.
- Labor income, consulting income, inheritance, and windfalls are excluded unless manually represented through spending assumptions.
- Behavioral adherence to guardrails is assumed; real-world behavior can differ.
- Tax and ACA law changes can invalidate parameter assumptions over time.

## Section 8: Missing Items and Proposed Additions

The document is now structurally consistent and TODOs are filled, but these additions would improve completeness:

1. **Input Field Data Dictionary (proposed):** One compact table listing each input, allowed range, default, and validator rule.
2. **Event Code Glossary (proposed):** Define each event code (`PV-DOWN`, `WR-CRIT`, `ACA-BREACH`, etc.) with trigger and practical response.
3. **Worked Example Scenario (proposed):** A full baseline scenario with concrete inputs and a short interpretation walkthrough.
4. **Troubleshooting Guide (proposed):** Common validation errors/warnings and how to fix them quickly.
5. **Sensitivity Playbook (proposed):** A checklist for what to vary first (spending, horizon, return assumptions, guardrails) and by how much.
6. **Compare Tab Method Notes (proposed):** Explain delta interpretation and how differing horizons are padded in overlays.
7. **Versioned Assumption Log (proposed):** Track major model assumption changes across releases.
