# OMEGA 0.16.1 — macOS TLS Capture Hotfix

Scope: transport-only repair for the OMEGA 0.16 prospective 2026 pregame source capture.

The Python.org 3.14 framework can fail HTTPS certificate-chain validation when its CA bundle is not configured. 0.16.1 replaces Python `urllib` downloads with macOS/system `curl` while keeping normal TLS certificate verification enabled.

No model coefficients, NB_ROLE parameters, H008/H012 logic, target universe rules, source URLs, market boundaries, or 2025-consumed rules are changed.

Security rules:
- no `CERT_NONE`
- no unverified SSL context
- no `curl -k` / `--insecure`
- downloads are written to `.part` files and atomically renamed only after curl succeeds
- required-source failures remain fail-closed
