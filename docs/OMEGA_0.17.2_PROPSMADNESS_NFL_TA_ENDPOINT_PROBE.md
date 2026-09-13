# OMEGA 0.17.2 — PropsMadness NFL T+A Endpoint Probe

Purpose: discover the actual same-origin PropsMadness NFL `Tckl+Ast` structured API endpoint and payload shape before writing the canonical OMEGA market adapter.

This release does **not** guess an NFL endpoint from the existing MLB provider. It does not capture request headers, cookies, tokens, or credentials. It does not normalize markets and does not read/write OMEGA-I.

Workflow:
1. Install 0.17.2.
2. Run `prepare_omega_propsmadness_nfl_ta_probe_0172.command` to copy the browser probe to the macOS clipboard.
3. Open PropsMadness NFL in Chrome, paste the probe into DevTools Console, and allow it to force `Tackles -> Tckl+Ast`.
4. The browser probe copies the captured relevant same-origin API JSON to the clipboard.
5. Run `import_omega_propsmadness_nfl_ta_probe_0172.command` to validate, freeze, hash, and create an upload handoff.
6. Build 0.17.3 against the observed endpoint/payload, then emit only the canonical 0.17 raw market schema.
