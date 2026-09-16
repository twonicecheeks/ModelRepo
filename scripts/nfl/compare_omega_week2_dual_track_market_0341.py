#!/usr/bin/env python3
"""OMEGA 0.34.1 — reference-only aware Week 2 dual-track market comparison.

Compatibility hardening over 0.34.0 only. PropsMadness `offerType=noOffer` /
`referenceBet` quotes are useful market references but are never labeled executable.
Frozen OMEGA control and role-shadow probabilities are unchanged.
"""
from pathlib import Path
import types

ROOT = Path('/Users/abbeyfelix/Developer/MODEL')
BASE = ROOT / 'scripts/nfl/compare_omega_week2_dual_track_market_0340.py'


def patched_source() -> str:
    src = BASE.read_text(encoding='utf-8')
    replacements = [
        ('SCHEMA = "OMEGA_WEEK2_DUAL_TRACK_MARKET_COMPARISON_0.34.0"', 'SCHEMA = "OMEGA_WEEK2_DUAL_TRACK_MARKET_COMPARISON_0.34.1"'),
        ('VERSION = "0.34.0"', 'VERSION = "0.34.1"'),
        ('root / "data/prospective/nfl/omega_week2_market_comparison_0340"', 'root / "data/prospective/nfl/omega_week2_market_comparison_0341"'),
        ('"OMEGA_0.34_WEEK2_MARKET_COMPARISON.csv"', '"OMEGA_0.34.1_WEEK2_MARKET_COMPARISON.csv"'),
        ('"OMEGA_0.34_UNMATCHED.csv"', '"OMEGA_0.34.1_UNMATCHED.csv"'),
        ('"OMEGA_0.34_AMBIGUOUS.csv"', '"OMEGA_0.34.1_AMBIGUOUS.csv"'),
        ('"OMEGA_0.34_UNSUPPORTED.csv"', '"OMEGA_0.34.1_UNSUPPORTED.csv"'),
        ('"OMEGA_0.34_POSTKICK_EXCLUDED.csv"', '"OMEGA_0.34.1_POSTKICK_EXCLUDED.csv"'),
        ('"OMEGA_0.34_WEEK2_MARKET_COMPARISON_AUDIT.json"', '"OMEGA_0.34.1_WEEK2_MARKET_COMPARISON_AUDIT.json"'),
        ('print("OMEGA 0.34 — WEEK 2 DUAL-TRACK DOWNSTREAM MARKET COMPARISON")', 'print("OMEGA 0.34.1 — WEEK 2 DUAL-TRACK DOWNSTREAM MARKET COMPARISON")'),
        ("final/'OMEGA_0.34_WEEK2_MARKET_COMPARISON_AUDIT.json'", "final/'OMEGA_0.34.1_WEEK2_MARKET_COMPARISON_AUDIT.json'"),
        ("final/'OMEGA_0.34_WEEK2_MARKET_COMPARISON.csv'", "final/'OMEGA_0.34.1_WEEK2_MARKET_COMPARISON.csv'"),
    ]
    for old, new in replacements:
        if old not in src:
            raise SystemExit(f'FAIL 0.34.1 compatibility patch target missing: {old}')
        src = src.replace(old, new)

    old = '        op_status = status_for(p, resolved)\n\n        rec = {'
    new = '''        is_reference_only = (\n            str(m.get("source") or "").strip().lower() == "propsmadness-reference-api"\n            or "REFERENCE_ONLY_NON_EXECUTABLE" in str(m.get("notes") or "")\n        )\n        op_status = "REFERENCE_ONLY_NOT_EXECUTABLE" if is_reference_only else status_for(p, resolved)\n\n        rec = {'''
    if src.count(old) != 1:
        raise SystemExit(f'FAIL expected one operational-status patch target; found {src.count(old)}')
    src = src.replace(old, new)

    old = '            "book": m.get("book"), "market_kind": "tackles_assists", "line": line,\n'
    new = '''            "book": m.get("book"), "market_kind": "tackles_assists", "line": line,\n            "market_source": m.get("source"),\n            "market_quote_classification": "REFERENCE_ONLY_NON_EXECUTABLE" if is_reference_only else "EXECUTABLE_OFFER",\n'''
    if src.count(old) != 1:
        raise SystemExit(f'FAIL expected one market-source patch target; found {src.count(old)}')
    src = src.replace(old, new)

    old = '            "marketFieldsReadDownstreamOnly": True,\n'
    new = '''            "referenceOnlyRows": sum(r.get("market_quote_classification") == "REFERENCE_ONLY_NON_EXECUTABLE" for r in out),\n            "executableOfferRows": sum(r.get("market_quote_classification") == "EXECUTABLE_OFFER" for r in out),\n            "marketFieldsReadDownstreamOnly": True,\n'''
    if src.count(old) != 1:
        raise SystemExit(f'FAIL expected one audit patch target; found {src.count(old)}')
    src = src.replace(old, new)
    return src


def main() -> int:
    src = patched_source()
    mod = types.ModuleType('omega0341_runtime')
    mod.__dict__['__name__'] = 'omega0341_runtime'
    mod.__dict__['__file__'] = str(BASE)
    exec(compile(src, str(BASE) + '::0341', 'exec'), mod.__dict__)
    print('OMEGA 0.34.1 — COMPATIBILITY HARDENING')
    print('PASS PropsMadness noOffer/referenceBet quotes explicitly labeled REFERENCE_ONLY_NOT_EXECUTABLE')
    print('PASS frozen probability tracks/model logic unchanged')
    return int(mod.main())


if __name__ == '__main__':
    raise SystemExit(main())
