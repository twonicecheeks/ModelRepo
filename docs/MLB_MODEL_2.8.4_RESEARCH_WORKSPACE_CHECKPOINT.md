# MLB MODEL 2.8.4 — Research Workspace checkpoint

Date: 2026-09-12
Status: prepared source + local/synthetic regression tested; live Mac activation not yet verified.

## Runtime matrix
- Chrome extension: 2.8.4 Research Workspace
- Local market service: 2.3.6 (unchanged)
- Data Pipeline: 1.10.0
- Structured K: 1.4 / `mlb-k-v0.8.3-sample-shrinkage-workload-2026-09-07`
- Structured ML: 1.3 / `mlb-moneyline-v0.8.0-offense-strength-2026-09-06`
- Slate Radar: 1.2 / `PRELINEUP_ACTIVE_ROSTER_PROXY`
- Research Confirmation Engine: RCE-0.1
- Workspace shell: 1.0

## What changed
1. Opportunity Radar exposes real model components behind **WHY THIS PROBABILITY?**. When Trust has a current projection, the explanation prefers that exact final projection; otherwise it labels the source as preliminary Radar.
2. K explanations expose expected K, structural/recent/season K blend, expected batters faced/innings, pitcher/opponent/matchup K rates, and blend weights from the existing K `components` object.
3. Structured ML surfaces starter-runs, bullpen-runs, raw runs before park, park factor, home-field runs, expected starter innings, run rates, offense rating/factor, and related inputs without changing the run/win formula.
4. RCE-0.1 adds Recent Form **HOT / AVERAGE / COLD**, recent K hit-rate summaries, opponent K fit, workload context, recent team W-L/run differential, confirmation/conflict/anomaly verdicts, and a confidence score.
5. Research is explicitly non-mutating: it cannot change xK, K probability, ML runs, ML probability, Trust state, or Trust thresholds.
6. Data Pipeline makes one free MLB StatsAPI recent-results request for team-form context and records feed success/failure in the audit. OddsPapi policy is unchanged.
7. Trust stores the previous edge-board snapshot so Radar can show market movement direction where comparable.
8. **Open Workspace** is restored. It creates `popup.html?workspace=1` as a persistent single-instance extension tab and focuses the existing tab on subsequent clicks. Workspace reads the same `chrome.storage.local` boards as the popup.

## Deliberate RCE boundary
External projection and free-form news aggregation are not silently fabricated. RCE-0.1 reports external projections as `NOT_CONNECTED`; current news/status context is limited to structured starter/lineup/workload information already available to the runtime. A later sourced research-provider layer can add external projections/news after its provider contracts and backtests are defined.

## Prediction-math integrity
No K/ML coefficients, formulas, lineages, Trust thresholds, or OddsPapi quota rules changed in 2.8.4. Target K market weight remains 0.

## Verification performed in prepared tree
- JavaScript syntax checks for all changed runtime files
- K golden/independence and workload uncertainty regressions
- ML golden-math/fail-closed regression
- Slate Radar 1.2/RCE non-mutation/component tests
- Trust opportunity hierarchy tests
- repository mirror/integrity tests
- 19 MLB/core/provider/service regression files pass
- active-tree audit passes in source-only mode

Live extension reload, UI inspection, and live-service verification on the user Mac remain pending.
