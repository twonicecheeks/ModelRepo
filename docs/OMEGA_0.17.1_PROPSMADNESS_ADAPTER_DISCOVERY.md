# OMEGA 0.17.1 — PropsMadness Adapter Discovery

Purpose: inspect and package the installed PropsMadness provider contract before writing the NFL T+A market adapter.

This phase makes no network requests, captures no sportsbook prices, does not invoke OddsPapi, and does not alter the frozen OMEGA-I ledger. It fingerprints the four existing provider files, checks JavaScript syntax when Node is available, extracts static dependency/export/field/call-site clues, and creates a code-only handoff ZIP.

The adapter built after this discovery must emit only the OMEGA 0.17 raw market schema. Model probability, edge, EV and picks remain prohibited from raw market capture.
