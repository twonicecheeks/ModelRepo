#!/bin/zsh
set -euo pipefail

ROOT="$HOME/Developer/MODEL"
TARGET="$ROOT/apps/chrome-extension/src"
APP_DIR="$HOME/Library/Application Support/MODEL"

python3 - "$TARGET" "$ROOT" "$APP_DIR" <<'PY2'
import json, re, sys, hashlib
from pathlib import Path

t = Path(sys.argv[1])
root = Path(sys.argv[2])
app = Path(sys.argv[3])

EXPECTED = {
    "extension": "3.2.0",
    "service": "2.3.7",
    "trust": "3.0.0",
    "controller": "1.13.0",
    "k_engine": "1.4",
    "ml_engine": "1.3",
    "radar": "1.7",
    "k_lineage": "mlb-k-v0.8.3-sample-shrinkage-workload-2026-09-07",
    "ml_lineage": "mlb-moneyline-v0.8.0-offense-strength-2026-09-06",
}


def read(path):
    if not path.is_file():
        raise SystemExit(f"FAIL missing {path}")
    return path.read_text(encoding="utf-8", errors="replace")


def sha(path):
    h = hashlib.sha256()
    h.update(path.read_bytes())
    return h.hexdigest()

manifest = json.loads(read(t / "manifest.json"))
if manifest.get("version") != EXPECTED["extension"]:
    raise SystemExit(f"FAIL extension version {manifest.get('version')} (expected {EXPECTED['extension']})")
print(f"PASS extension {EXPECTED['extension']}")

core = read(t / "model_v2_core.js")
ui = read(t / "model_v2.js")
if f"const VERSION='{EXPECTED['trust']}'" not in core:
    raise SystemExit("FAIL Trust core version")
if f"const V='{EXPECTED['trust']}'" not in ui:
    raise SystemExit("FAIL Trust UI version")
for marker in (
    "localStarterKMarket",
    "propsmadness_sharp_consensus",
    "EXPECTED_K_INDEPENDENT_OF_TARGET_K_LINE",
    "K_ONLY_ZERO_ODDSPAPI",
    "RESEARCH ANOMALY",
):
    if marker not in core + ui:
        raise SystemExit(f"FAIL Trust marker {marker}")
print("PASS Trust 3.0.0 opportunity-integrity + research-hardening path")

controller = read(t / "features/data_pipeline/controller.js")
if f"const VERSION='{EXPECTED['controller']}'" not in controller:
    raise SystemExit("FAIL data-pipeline controller version")
if "release:'3.0.0'" not in controller or "PRODUCTION AUDIT 3.0.0" not in controller:
    raise SystemExit("FAIL copied ML audit release metadata")
print("PASS Data Pipeline 1.13.0 + automatic zero-new-API Trust rebuild + copied audit release metadata")

k = read(t / "models/mlb/k/structured_k_core.js")
ml = read(t / "models/mlb/moneyline/structured_ml_core.js")
radar = read(t / "features/slate_radar/radar_core.js")
if f"const VERSION='{EXPECTED['k_engine']}'" not in k or "TARGET_K_MARKET_WEIGHT=0" not in k:
    raise SystemExit("FAIL structured K core / target-market separation")
if EXPECTED["k_lineage"] not in k:
    raise SystemExit("FAIL K lineage")
if f"const VERSION='{EXPECTED['ml_engine']}'" not in ml or EXPECTED["ml_lineage"] not in ml:
    raise SystemExit("FAIL structured ML lineage")
if f"const VERSION='{EXPECTED['radar']}'" not in radar or "PRELINEUP_ACTIVE_ROSTER_PROXY" not in radar:
    raise SystemExit("FAIL Slate Radar version/mode")
print("PASS K 1.4 / ML 1.3 / Slate Radar 1.7 / RCE 0.5")
if "const RESEARCH_VERSION='RCE-0.5'" not in radar or "probabilityMutationFromResearch:false" not in radar:
    raise SystemExit("FAIL RCE non-mutating contract")
panel = read(t / "features/slate_radar/radar_panel.js")
workspace = read(t / "features/workspace/workspace_shell.js")
popup = read(t / "popup.html")
if "WHY THIS PROBABILITY?" not in panel or "Recent Form" not in panel and "RECENT FORM" not in panel:
    raise SystemExit("FAIL Radar explanation UI")
if "get('workspace')==='1'" not in workspace or "features/workspace/workspace_shell.js" not in popup or "OPEN WORKSPACE" not in controller:
    raise SystemExit("FAIL persistent Workspace contract")
print("PASS Research Confirmation visibility + persistent Workspace contract")
if "BET STATUS / WHY" not in panel or "STRONGEST SUPPORT" not in panel or "MATERIAL FINDINGS" not in panel:
    raise SystemExit("FAIL research-hardening explanation UI")
if "MODEL_TRUST_CONTROLLER" not in controller or "refreshFromLatest" not in controller or "0 new API" not in controller:
    raise SystemExit("FAIL automatic zero-new-API Trust rebuild contract")
print("PASS research-hardening UX + automatic Trust rebuild contract")
research = read(t / "providers/public_research/public_research_core.js")
manifest_hosts = manifest.get("host_permissions", [])
if "const VERSION='0.5.0'" not in research or "numberFire via FanDuel Research" not in research or "Google News RSS" not in research:
    raise SystemExit("FAIL public research provider contract")
if "https://news.google.com/*" not in manifest_hosts or "https://www.fanduel.com/*" not in manifest_hosts:
    raise SystemExit("FAIL public research host permissions")
if "INDEPENDENT ML PROJECTION" not in panel or "SOURCED PUBLIC RESEARCH" not in panel or "NEWS HOLD" not in panel:
    raise SystemExit("FAIL sourced research Radar UI")
print("PASS Public Research 0.5 / material findings + sourced ML projection delta + NEWS HOLD contract")
nfl_research = read(t / "providers/nfl_public/nfl_public_core.js")
matchup_core = read(t / "features/matchup_center/matchup_core.js")
matchup_panel = read(t / "features/matchup_center/matchup_panel.js")
matchup_intelligence = read(t / "features/matchup_center/matchup_intelligence_core.js")
if "const VERSION='0.4.0'" not in nfl_research or "ESPN GAME SUMMARY" not in nfl_research:
    raise SystemExit("FAIL NFL public research provider")
if "const VERSION='1.4.0'" not in matchup_core or "mlbMatchups" not in matchup_core or "nflMatchups" not in matchup_core or "omegaForGame" not in matchup_core:
    raise SystemExit("FAIL Matchup Center core")
if "REFRESH NFL WEEK + DETAIL" not in matchup_panel or "OMEGA TACKLE MODEL" not in matchup_panel or "INJURY / AVAILABILITY IMPACT" not in matchup_panel or "MATCHUP INTELLIGENCE" not in matchup_panel:
    raise SystemExit("FAIL Matchup Center panel")
if "const VERSION='0.2.0'" not in matchup_intelligence or "mlbIntelligence" not in matchup_intelligence or "nflIntelligence" not in matchup_intelligence or "probabilityMutation:false" not in matchup_intelligence:
    raise SystemExit("FAIL Matchup Intelligence non-mutating contract")
if "https://site.api.espn.com/*" not in manifest_hosts:
    raise SystemExit("FAIL ESPN host permission")
print("PASS Matchup Center 1.4 + Matchup Intelligence 0.2 + NFL Public Research 0.4 + personnel/depth-chart + read-only OMEGA boundary")

# Package/runtime mirrors.
mirrors = [
    (t / "model_v2_core.js", root / "packages/core/src/trust/model_v2_core.js"),
    (t / "model_v2.js", root / "packages/core/src/trust/model_v2.js"),
    (t / "features/data_pipeline/controller.js", root / "packages/core/src/data_pipeline/controller.js"),
    (t / "features/slate_radar/radar_core.js", root / "packages/core/src/slate_radar/radar_core.js"),
    (t / "providers/public_research/public_research_core.js", root / "packages/providers/public_research/src/public_research_core.js"),
    (t / "providers/nfl_public/nfl_public_core.js", root / "packages/providers/nfl_public/src/nfl_public_core.js"),
    (t / "features/matchup_center/matchup_core.js", root / "packages/core/src/matchup_center/matchup_core.js"),
    (t / "features/matchup_center/matchup_intelligence_core.js", root / "packages/core/src/matchup_center/matchup_intelligence_core.js"),
    (t / "models/mlb/k/structured_k_core.js", root / "packages/models/mlb/k/structured_k_core.js"),
    (t / "models/mlb/moneyline/structured_ml_core.js", root / "packages/models/mlb/moneyline/structured_ml_core.js"),
]
for a, b in mirrors:
    if read(a) != read(b):
        raise SystemExit(f"FAIL mirror divergence: {a.relative_to(root)} != {b.relative_to(root)}")
print("PASS package/runtime mirror integrity")

canon = root / "services/market-service/src/model_service.py"
deployed = app / "service/model_service.py"
canon_text = read(canon)
if f'VERSION = "{EXPECTED["service"]}"' not in canon_text:
    raise SystemExit("FAIL canonical service version")
if EXPECTED["k_lineage"] not in canon_text or EXPECTED["ml_lineage"] not in canon_text:
    raise SystemExit("FAIL canonical service adapter metadata")
for marker in (
    "playerPropBooks",
    "starterStrikeoutMarkets",
    "mlb_strikeout_catalog",
    "fixtureFallbackRequests",
    "extract_strikeout_props",
    "merge_fixture_prop_payload",
):
    if marker in canon_text:
        raise SystemExit(f"FAIL retired player-prop runtime marker {marker}")
if 'playerPropRequestsThisRefresh": 0' not in canon_text:
    raise SystemExit("FAIL quota policy marker")
print(f"PASS canonical local service {EXPECTED['service']} / zero player-prop requests")

if deployed.is_file():
    deployed_text = read(deployed)
    if f'VERSION = "{EXPECTED["service"]}"' not in deployed_text:
        raise SystemExit(f"FAIL deployed service version at {deployed}")
    if sha(canon) != sha(deployed):
        raise SystemExit("FAIL deployed service differs from canonical service source")
    print("PASS managed service deployment matches canonical source")
else:
    print("WARN managed service deployment not present; source audit only")

# Both checked-in service templates must be exact mirrors and current.
tpl_a = root / "services/market-service/config.template.json"
tpl_b = root / "services/market-service/src/config.template.json"
if read(tpl_a) != read(tpl_b):
    raise SystemExit("FAIL market-service config templates diverged")
tpl = json.loads(read(tpl_b))
if tpl.get("serviceVersion") != EXPECTED["service"]:
    raise SystemExit("FAIL template serviceVersion")
adapters = tpl.get("sports", {}).get("mlb", {}).get("modelAdaptersAvailable", [])
if adapters != [EXPECTED["ml_lineage"], EXPECTED["k_lineage"]]:
    raise SystemExit(f"FAIL template modelAdaptersAvailable {adapters}")
print("PASS service templates synchronized to current model lineages")

# Active-tree hygiene / retired runtime.
retired = [
    "features/data_pipeline/bootstrap.js",
    "scan_scope_v2_2.js",
    "scan_scope_v2_2_core.js",
    "propsmadness_table_probe.js",
    "propsmadness_table_probe_main.js",
    "propsmadness_table_ingestor.js",
    "propsmadness_table_ingestor_core.js",
    "propsmadness_table_ingestor_main.js",
    "workflow_v1.js",
    "workflow_v1_core.js",
    "pm_model_v1_core.js",
    "pm_model_v1_lab.js",
]
for rel in retired:
    if (t / rel).exists():
        raise SystemExit(f"FAIL retired active runtime file: {rel}")
for q in t.rglob("*"):
    n = q.name.lower()
    if q.is_file() and (n.endswith(".zip") or n.endswith(".pyc") or "backup" in n or "rollback" in n):
        raise SystemExit(f"FAIL active-tree clutter: {q}")
all_runtime = "\n".join(
    p.read_text(encoding="utf-8", errors="ignore")
    for p in t.rglob("*")
    if p.is_file() and p.suffix in {".js", ".html", ".json"}
)
if "window.PMV1Engine" in all_runtime:
    raise SystemExit("FAIL legacy PMV1Engine runtime marker active")
print("PASS active-tree hygiene / legacy runtime remains removed")

# Current docs must not regress the Radar checkpoint.
checkpoint = read(root / "docs/v281 Model Checkpoint.rtf")
if "* Slate Radar: **1.7**" not in checkpoint:
    raise SystemExit("FAIL current checkpoint Slate Radar version")
active_doc = read(root / "docs/architecture/ACTIVE_RUNTIME.md")
for expected in ("3.2.0", "2.3.7", "Slate Radar: **1.7", "RCE-0.5", "MLB Public Research provider: **0.5.0**", "NFL Public Research provider: **0.4.0**", "Matchup Intelligence: **0.2.0**", EXPECTED["k_lineage"]):
    if expected not in active_doc:
        raise SystemExit(f"FAIL active-runtime doc marker {expected}")
print("PASS current runtime documentation")

# Release inventory must explicitly distinguish packaged artifacts from install-history-only releases.
release_index = root / "releases/RELEASE_INDEX.json"
idx = json.loads(read(release_index))
if idx.get("currentPackagedRelease") != "2.8.3":
    raise SystemExit("FAIL release index currentPackagedRelease")
if not (root / "releases/2.8.3").is_dir():
    raise SystemExit("FAIL releases/2.8.3 missing")
print("PASS release inventory reconciliation")

print("AUDIT PASS — MODEL 3.2.0 Personnel & Matchup Impact source integrity; current packaged release remains 2.8.3")
PY2
