# OMEGA Sports Intelligence: one workspace

OMEGA is a local web application: a Python server, browser interface, and SQLite database. It is not a native macOS application or a hosted cloud service. The Chrome extension is now its PropsMadness collector. DELTA and V2 are model modules inside OMEGA.

## Open and pair

From the canonical repository on your Mac:

```sh
cd /Users/abbeyfelix/Developer/MODEL
zsh Start_OMEGA.command
```

Keep the terminal open. Open OMEGA in Chrome at http://127.0.0.1:8741. In chrome://extensions, reload the extension already loaded from `apps/chrome-extension/src`; this preserves that extension's Chrome records. Its popup is now called OMEGA Collector. Click **Open OMEGA & connect**, then connect from OMEGA's **Chrome collector** screen. Pairing is required once, or again after disconnecting/resetting extension storage. Keep your normal PropsMadness browser session signed in.

Use **Sync MLB slate** in OMEGA for the desired date. This collects source data, runs the existing OMEGA MLB refresh, and captures prices again after forecasts have been saved. Official MLB starters and nine confirmed hitters per team are still required. Held prices explain why a comparison could not be made. Sync is a current capture: changing the date does not manufacture historical PropsMadness observations.

## Ownership and storage

- OMEGA owns model inference, saved forecasts, comparisons, and review.
- The extension gathers PropsMadness data; its default popup no longer runs the separate browser MLB models.
- Sources and results enter the existing database at `~/Library/Application Support/OMEGA Next/omega.sqlite3`.
- **Archive previous Chrome records** copies allowlisted old source/model boards into that database as inactive research records. It does not promote old forecasts or copy credentials.
- The previous extension interface remains in `popup_legacy.html` for reference. Its other specialized research screens have not been fully migrated into OMEGA.
- The older service on port 8765 and its MODEL support folder are legacy components; this connection uses port 8741 and does not require that service. Existing files are preserved.

This is one product with a main application and a browser collector, rather than two competing inference interfaces. Source code, documents and historical archives remain in the same Git repository. SQLite records and Chrome storage are local runtime data, not automatically GitHub backups; use OMEGA's database backup export to preserve them.

## Safety and chronology

The collector pairs to one extension ID using a revocable token. The application stores only its hash. Browser login cookies and passwords are not transferred. Application control endpoints retain their local session protection. Source delivery retries preserve observation timestamps. The pending queue is bounded to three captures and 16 MB.

Quotes join by scheduled teams/time and exact team-scoped official starter name. PropsMadness numeric player IDs are not MLBAM or GSIS IDs. Quote observations must follow the saved forecast and precede first pitch. Prices remain research references, not verified wager receipts. Neither this integration nor a displayed edge establishes profitable betting performance.

## Model boundaries

This change does not alter frozen model parameters. Supporting pitcher outs, earned runs, hits allowed and walks are archived sources, not automatically fitted DELTA workload inputs. There is still no calibrated hitter hits, total bases, home run, or H+R+RBI engine. NFL tackle-plus-assist captures are stored as raw research sources; no new current tackle forecast or guessed GSIS mapping is created.

The collector requires Chrome and the default port 8741. OMEGA's alternate-port standalone mode does not pair with this collector.

## Verification

Nine offline Python contracts cover persistence, exact identity, chronology, idempotency, legacy archives, and actual request-handler authorization/CORS logic using an in-memory HTTP transport. Node worker checks cover origin scope, offline retries, original timestamps, archive allowlists, and the collector-only popup. Thirteen UI templates render successfully. Socket binding and real Chrome installation were unavailable in the preparation environment; a live Mac/Chrome connection remains the installation verification step.

```sh
cd omega_delta
python3 -m unittest discover -s tests -p test_chrome_collector.py -v
node tests/check_chrome_collector.cjs
node tests/check_ui.cjs
```

The prepared Git patch is based on checkpoint `252811e`. It has not been installed on your Mac or pushed to GitHub. Git network access failed because the preparation environment's proxy was unreachable, not because GitHub rejected your account.
