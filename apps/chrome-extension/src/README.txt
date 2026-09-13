MODEL 3.2.0 — Personnel & Matchup Impact

Production MLB architecture with Slate Radar, structured K/ML boards, Trust, persistent Workspace, and a sourced but non-mutating Research Confirmation audit layer.

Frozen MLB prediction-math baseline inherited from 2.8.2/2.8.3:
- K lineage v0.8.3: current-season pitcher samples under 180 BF are shrunk toward prior-season/league skill.
- Limited current Pitcher Outs lines reduce confidence and widen K uncertainty.
- Production ML requires a current-game Pitcher Outs anchor; season average is Radar/diagnostic only.
- PropsMadness book-level K offers are preserved; Pinnacle + Circa same-line two-sided prices can form a downstream sharp K consensus.
- Target K market weight in expected K remains 0.
- OddsPapi player-prop requests remain 0.
- Legacy PMV1Engine/Hydrate/Batch runtime remains physically removed.

Decision hierarchy remains unchanged: VERIFIED > WATCH (not verified) > preliminary Radar; ANOMALY and NEWS HOLD are research-only; PASS/BLOCKED are suppressed from top opportunities.

3.0.1 Matchup Detail Panels additions:
- Slate Radar 1.4 / RCE-0.5 keeps the 2.8.4 WHY THIS PROBABILITY model-component visibility and Recent Form HOT/AVERAGE/COLD.
- Public Research provider 0.5.0 retrieves recent MLB StatsAPI transactions and Google News RSS headlines for the highest-ranked research targets.
- High-risk pitcher news/transactions can create NEWS HOLD — REVIEW without changing probability or Trust.
- numberFire daily MLB win probabilities, when available through FanDuel Research, are displayed as a true independent ML projection benchmark — never as sportsbook consensus.
- Opposite-side external ML disagreement is surfaced as MIXED or CONFLICT; a >=12pp opposite-side gap is CONFLICT.
- SYNC + BUILD K + ML + TRUST automatically rebuilds Trust from the latest saved OddsPapi snapshot with 0 new OddsPapi requests; REFRESH ML + ALL remains the explicit fresh game-market call.
- BET STATUS / WHY is displayed separately from MODEL THESIS and RESEARCH CONFIDENCE.
- Sourced headlines/transactions are distilled into MATERIAL FINDINGS, with strongest supporting/opposing signals called out.
- ML external projections display the selected-side model-vs-external probability delta.
- REFRESH RESEARCH updates only research evidence; it does not rebuild the models or refresh OddsPapi.
- OPEN WORKSPACE remains a single-instance persistent extension tab.
- K numeric external projections remain NOT_AVAILABLE_FOR_K in this provider version.

Research boundary: public research is observational. It never mutates K xK, K probability, ML run projection, ML probability, Trust state, or Trust thresholds.

- Matchup Center 1.0 adds MLB/NFL league toggle, per-game MLB model/RCE research, and a separate NFL weekly public-research surface via ESPN scoreboard + Google News.
- NFL research is non-mutating and does not alter or silently import the existing NFL/Omega model pipeline.

- Matchup Center 1.1 expands MLB games into full outlook/starter/offense/bullpen/market/research diagnostics.
- NFL Public Research 0.2 adds ESPN game-summary detail and named injury/QB context.
- Local service 2.3.7 exposes a read-only OMEGA tackle matchup bridge with zero OddsPapi calls.
- NFL Matchup Center can display existing OMEGA tackle model/market rows without letting public research mutate OMEGA.


3.0.2 Matchup Clarity & Materiality:
- MLB bottom-line priority now follows Trust blockers before generic research verdict wording.
- MLB status explicitly separates Trust, starter-board verification, starter confirmation, and official-lineup count.
- Background/stale MLB/NFL research is hidden from the primary handicap.
- NFL long-term IR is baseline/background; QB and clustered position-group issues drive REVIEW, ordinary non-QB availability defaults to WATCH.
- OMEGA shows MARKET READY vs PRE-GAMEDAY / NOT ACTIONABLE and summarizes blockers once.


3.1.0 Matchup Intelligence:
- Adds a non-mutating Matchup Intelligence layer to each MLB game, ranking projected-runs, offense, starter, bullpen, recent-form, model-vs-sharp and independent-projection advantages.
- Adds NFL public-context intelligence from ESPN predictor, public market, and severity-weighted availability; it is explicitly NOT an NFL game-side MODEL pick.
- Surfaces a compact edge map / public-context consensus in collapsed matchup cards.
- Preserves all 3.0.2 clarity/materiality fixes.

3.2.0 Personnel & Matchup Impact:
- MLB records a pre-lineup proxy baseline and, once official orders arrive, shows added/missing proxy hitters plus offense-rating, projected-run, and selected-side probability movement.
- NFL enriches current injury rows with ESPN depth-chart rank/role and weights personnel impact by status × depth role × position importance.
- Matchup Intelligence ranks personnel pressure points without mutating MLB probabilities, Trust, OMEGA, or any NFL game-side model.
- Fixes MLB starting-pitching edge labels so the displayed side and explanatory text cannot disagree.
