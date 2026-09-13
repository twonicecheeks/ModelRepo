# OMEGA Tackle Model 0.3 — H011 Opportunity Coupling

This phase tests exactly one new mechanism after H012 exposure passed: whether predicted team tackle-opportunity volume should directly drive player tackle-credit forecasts.

Frozen components:
- OMEGA 0.2 xTO model and selected ridge strength.
- OMEGA 0.2.2 exposure/role model and selected ridge strength.
- Standard defensive scrimmage tackle-credit semantics.

New component:

`xTC = predicted xTO × predicted player snap share × shrunk credit rate per opportunity-exposure unit`

Historical opportunity exposure is approximated as realized team tackle-opportunity plays multiplied by realized player defensive snap share. This is intentionally transparent and is not claimed to be exact on-field opportunity participation.

The shrinkage alpha is selected only on 2021–2023 chronological folds. 2024 is a diagnostic-directed confirmation set. OMEGA 2025 remains sealed. No sportsbook or market data is read.
