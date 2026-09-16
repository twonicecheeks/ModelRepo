"""Machine-readable DEN@KC M01-M88 NFL nuance registry.

Registration preserves the development hypotheses and gates. It is NOT promotion
into a fitted or frozen probability model. Full definitions and engineering rules
live in docs/architecture/NFL_STATE_INTELLIGENCE_0.1.0.md.
"""
from __future__ import annotations

VERSION = "0.1.0"
SOURCE_GAME = "DEN@KC_2026-09-14"
SOURCE_LEDGER = "M01-M88"
FROZEN_OMEGA_MUTATION_ALLOWED = False

_ROWS = (
    ("M01", "Designed pass/run vs box-score pass/run", "CORE"),
    ("M02", "Pass/run ratio must be conditional", "CORE"),
    ("M03", "Opening-script tendency", "BACKTEST"),
    ("M04", "Early-down success creates downstream QB environment", "CORE"),
    ("M05", "Opponent pressure is not equally exposed every snap", "CORE"),
    ("M06", "Scheme can suppress a matchup weakness", "CORE"),
    ("M07", "Cost of first-down aggression depends on opponent", "CORE"),
    ("M08", "High-leverage target share", "CORE"),
    ("M09", "QB trust hierarchy is not raw target share", "BACKTEST"),
    ("M10", "Coverage allocation creates secondary-receiver opportunity", "CORE"),
    ("M11", "In-game injuries must be snap-timestamped", "CORE"),
    ("M12", "Replacement-player cascade", "CORE"),
    ("M13", "QB response after negative events", "BACKTEST"),
    ("M14", "Play-caller adaptation speed", "CORE"),
    ("M15", "Drive-level RB workload persistence", "BACKTEST"),
    ("M16", "RB rotation purpose", "BACKTEST"),
    ("M17", "QB mobility health signal", "BACKTEST"),
    ("M18", "Health should not be binary", "CORE"),
    ("M19", "Third-down distance independent modeling", "CORE"),
    ("M20", "Receiver usage after defensive personnel change", "WATCH"),
    ("M21", "Explosive-play probability is coverage-state dependent", "CORE"),
    ("M22", "Game-script pass-rate elasticity", "CORE"),
    ("M23", "Successful short passing can function like rushing", "IMPLEMENT"),
    ("M24", "Personnel-specific defensive coverage schema", "CORE"),
    ("M25", "Bayesian shrinkage for live updating", "CORE"),
    ("M26", "Outcome vs mechanism classification", "CORE"),
    ("M27", "Penalty/drive disruption state", "CORE"),
    ("M28", "RB receiving role as pressure/long-yardage solution", "BACKTEST"),
    ("M29", "Starting field position affects passing risk profile", "CORE"),
    ("M30", "Drive continuation efficiency", "CORE"),
    ("M31", "Separate QB volume from QB efficiency", "CORE"),
    ("M32", "Offensive touch concentration", "BACKTEST"),
    ("M33", "Offensive operation/continuity", "BACKTEST"),
    ("M34", "Completion quality / functional completion", "CORE"),
    ("M35", "Defensive rally-and-tackle ability", "BACKTEST"),
    ("M36", "QB statistical production is not team offensive production", "CORE"),
    ("M37", "First-down generation by play type", "CORE"),
    ("M38", "Broadcast intelligence extraction", "EXTERNAL DATA"),
    ("M39", "QB creation can rescue failed passing structure", "CORE"),
    ("M40", "Offensive mechanism diversity", "CORE"),
    ("M41", "Receiver-yardage decomposition", "CORE"),
    ("M42", "Play-caller identity", "CORE"),
    ("M43", "Situational play-calling fingerprint", "CORE"),
    ("M44", "Play-call quality separate from play result", "CORE"),
    ("M45", "Play-caller adaptation rate", "CORE"),
    ("M46", "Play caller x QB style interaction", "CORE"),
    ("M47", "Offensive caller vs defensive caller matchup", "CORE"),
    ("M48", "Passing creation vs YAC creation", "CORE"),
    ("M49", "Missed-tackle probability / tackling quality", "BACKTEST"),
    ("M50", "Explosive-play causal classification", "CORE"),
    ("M51", "Drive continuity state after conversions", "BACKTEST"),
    ("M52", "Cumulative defensive workload/fatigue", "BACKTEST"),
    ("M53", "Success-weighted play selection", "CORE"),
    ("M54", "Counterfactual play-call value", "CORE"),
    ("M55", "Result luck vs decision quality", "CORE"),
    ("M56", "Substitution-denial tempo", "CORE"),
    ("M57", "Personnel package as information and deception", "CORE"),
    ("M58", "Short-yardage front compression vs edge vulnerability", "CORE"),
    ("M59", "Fourth-down decision vs fourth-down concept", "CORE"),
    ("M60", "Halftime Adjustment Delta", "CORE"),
    ("M61", "Catchable-pass attribution / receiver error", "CORE"),
    ("M62", "Pre-snap operational efficiency", "CORE"),
    ("M63", "Expected drive value lost by error source", "CORE"),
    ("M64", "Contextual risk budget", "CORE"),
    ("M65", "Field-position-adjusted turnover cost", "CORE"),
    ("M66", "Deep-attempt downside distribution", "CORE"),
    ("M67", "Turnover outcome decomposition", "CORE"),
    ("M68", "Sudden-change offense and defense", "CORE"),
    ("M69", "Short-field defensive compression", "CORE"),
    ("M70", "State-dependent negative-play cost", "CORE"),
    ("M71", "Turnover capitalization rate", "CORE"),
    ("M72", "Sack outcome decomposition", "CORE"),
    ("M73", "QB ball security under pressure", "CORE"),
    ("M74", "Penalty amplification after successful plays", "CORE"),
    ("M75", "Secondary RB receiving / role substitution", "BACKTEST"),
    ("M76", "Field-position-dependent offensive aggression", "CORE"),
    ("M77", "Win-probability-dependent offensive objective", "CORE"),
    ("M78", "Clock-adjusted play value", "CORE"),
    ("M79", "Late-game personnel/workload redistribution", "CORE"),
    ("M80", "Closeout-state contamination of historical stats", "CORE"),
    ("M81", "Drive fragility / disruption resilience", "CORE"),
    ("M82", "Special-teams contribution to offensive starting state", "BACKTEST"),
    ("M83", "Review/overturn state correction", "CORE"),
    ("M84", "Starter exposure / injury-risk management", "CORE"),
    ("M85", "Clock-burn efficiency per snap", "CORE"),
    ("M86", "Victory-formation plays excluded from normal tendencies", "CORE"),
    ("M87", "Predictive football stats vs official prop-settlement stats", "CORE"),
    ("M88", "Terminal/surrender-state classification", "CORE"),
)

PHASE_1 = frozenset("M01 M02 M04 M19 M22 M27 M31 M37 M59 M64 M65 M66 M67 M68 M69 M70 M71 M77 M78 M79 M80 M83 M86 M87 M88".split())
PHASE_2 = frozenset("M05 M06 M08 M09 M10 M21 M24 M34 M35 M41 M48 M49 M50".split())
PHASE_3 = frozenset("M14 M42 M43 M44 M45 M46 M47 M53 M54 M56 M57 M58 M59 M60".split())
PHASE_4 = frozenset("M11 M12 M13 M14 M15 M16 M17 M18 M33 M38 M61 M62 M63 M72 M73 M74 M75 M76".split())
PHASE_5 = frozenset("M79 M84 M85 M86 M87".split())

DIRECT_PRIMITIVES_0_1 = frozenset("M01 M19 M27 M29 M34 M37 M39 M68 M80 M83 M86 M87".split())
PARTIAL_FOUNDATION_0_1 = frozenset("M02 M04 M05 M07 M22 M64 M69 M76 M77 M88".split())


def _phases(mid: str) -> tuple[str, ...]:
    out: list[str] = []
    if mid in PHASE_1: out.append("PHASE_1_STANDARD_PBP")
    if mid in PHASE_2: out.append("PHASE_2_RICH_CHARTING")
    if mid in PHASE_3: out.append("PHASE_3_PLAY_CALLER")
    if mid in PHASE_4: out.append("PHASE_4_OPERATIONS_HEALTH_LIVE")
    if mid in PHASE_5: out.append("PHASE_5_PROP_SETTLEMENT")
    return tuple(out or ["CROSSCUTTING_RESEARCH"])


def _integration_state(mid: str) -> str:
    if mid in DIRECT_PRIMITIVES_0_1:
        return "DIRECT_PRIMITIVE_0_1"
    if mid in PARTIAL_FOUNDATION_0_1:
        return "PARTIAL_FOUNDATION_0_1"
    return "REGISTERED_NOT_IMPLEMENTED"


NUANCE_REGISTRY = tuple(
    {
        "id": mid,
        "title": title,
        "source_status": source_status,
        "roadmap_phases": _phases(mid),
        "integration_state": _integration_state(mid),
    }
    for mid, title, source_status in _ROWS
)
BY_ID = {item["id"]: item for item in NUANCE_REGISTRY}

if len(NUANCE_REGISTRY) != 88 or len(BY_ID) != 88:
    raise RuntimeError("M01-M88 registry integrity failure")
if tuple(BY_ID) != tuple(f"M{i:02d}" for i in range(1, 89)):
    raise RuntimeError("M01-M88 registry ordering/coverage failure")

SOURCE_STATUS_COUNTS = {
    status: sum(1 for x in NUANCE_REGISTRY if x["source_status"] == status)
    for status in sorted({x["source_status"] for x in NUANCE_REGISTRY})
}
EXPECTED_SOURCE_STATUS_COUNTS = {
    "CORE": 70,
    "BACKTEST": 15,
    "WATCH": 1,
    "IMPLEMENT": 1,
    "EXTERNAL DATA": 1,
}
if SOURCE_STATUS_COUNTS != EXPECTED_SOURCE_STATUS_COUNTS:
    raise RuntimeError(f"M01-M88 source-status drift: {SOURCE_STATUS_COUNTS}")


def get_nuance(nuance_id: str) -> dict:
    return dict(BY_ID[nuance_id])


def integration_summary() -> dict[str, int]:
    out: dict[str, int] = {}
    for item in NUANCE_REGISTRY:
        key = item["integration_state"]
        out[key] = out.get(key, 0) + 1
    return dict(sorted(out.items()))


if __name__ == "__main__":
    print(f"NFL nuance registry {VERSION} · {SOURCE_GAME} · {len(NUANCE_REGISTRY)} items · {integration_summary()}")
