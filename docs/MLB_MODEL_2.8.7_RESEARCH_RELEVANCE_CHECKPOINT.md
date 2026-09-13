# MODEL 2.8.7 — Research Relevance & Diagnostic Clarity

- Extension/Trust: **2.8.7**
- Slate Radar: **1.5**
- RCE: **RCE-0.4**
- Public Research provider: **0.4.0**
- Local service: **2.3.6** (unchanged)

## Purpose
Reduce research noise without changing K/ML probability math or Trust thresholds.

## Changes
- Classifies sourced evidence as DIRECTLY_MATERIAL, POSSIBLY_MATERIAL, or BACKGROUND.
- Only DIRECTLY_MATERIAL evidence can create a NEWS HOLD / review state.
- Generic game recaps, betting previews, and unrelated team transactions remain background context.
- Trust anomalies are labeled separately from RCE model/observed-data anomalies.
- Major external ML projection disagreements are visible in collapsed Radar rows.
- Strongest support/opposition can show up to three signals.
- Research remains non-mutating.
