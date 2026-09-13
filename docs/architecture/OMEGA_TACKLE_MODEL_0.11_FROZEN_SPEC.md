# OMEGA Tackle Model 0.11 / Freeze Gate 0.11.1

The substantive frozen model remains OMEGA 0.11: H012 exposure + H008 opportunity topology, with the precommitted 2025 one-shot protocol.

Freeze-gate hotfix 0.11.1 changes **only audit schema compatibility**. OMEGA 0.2's immutable audit uses `selection.xSnapL2`; the original gate requested a non-existent `xDefensiveSnapsL2` key. The hotfix reads the historical key and fails closed with explicit schema diagnostics if a required field is absent or malformed.

No model coefficients, feature families, windows, targets, verdict rules, holdout rules, or sportsbook boundaries change.
