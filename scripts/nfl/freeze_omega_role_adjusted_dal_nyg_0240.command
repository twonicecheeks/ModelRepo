#!/bin/zsh
set -euo pipefail
ROOT="/Users/abbeyfelix/Developer/MODEL"
cd "$ROOT"
python3 scripts/nfl/record_omega_role_adjusted_challenger_0240.py \
  --game-id 2026_01_DAL_NYG \
  --adjustment 'DeMarvion Overshown|7.89|7.47|8.23|OFFICIAL_STARTING_LB_GREEN_DOT_ROLE_PREKICKOFF' \
  --adjustment 'Tremaine Edmunds|6.92|6.70|7.14|ROLE_CONSISTENT_EVERY_DOWN_CONTROL_PREKICKOFF' \
  --adjustment 'DaRon Bland|6.63|6.35|6.84|ROLE_CONSISTENT_STARTING_CB_CONTROL_PREKICKOFF' \
  --adjustment 'Tyler Nubin|6.52|6.17|6.72|OFFICIAL_STARTING_SAFETY_ROLE_PREKICKOFF' \
  --adjustment 'Jalen Thompson|5.74|5.44|5.93|ROLE_CONSISTENT_EVERY_DOWN_CONTROL_PREKICKOFF' \
  --adjustment 'Dee Winters|5.52|4.92|5.98|OFFICIAL_STARTING_LB_ROLE_PREKICKOFF' \
  --adjustment 'Arvell Reese|5.47|4.77|6.17|OFFICIAL_STARTING_WLB_ROLE_PREKICKOFF' \
  --adjustment 'Jevon Holland|5.07|4.80|5.29|OFFICIAL_STARTING_FS_ROLE_PREKICKOFF' \
  --adjustment 'Caleb Downs|4.57|4.15|4.93|OFFICIAL_FIRST_TEAM_DB_ROLE_PREKICKOFF' \
  --adjustment 'Deonte Banks|4.02|3.75|4.24|OFFICIAL_STARTING_CB_ROLE_PREKICKOFF' \
  --adjustment 'Greg Newsome II|3.75|3.50|3.95|OFFICIAL_STARTING_CB_ROLE_PREKICKOFF' \
  --adjustment 'Abdul Carter|3.55|3.27|3.80|ROLE_CONSISTENT_STARTING_EDGE_CONTROL_PREKICKOFF' \
  --pregame-proof-time '2026-09-13T20:08:00-04:00' \
  --provenance-note 'These exact 12 role-corrected T+A means and uncertainty bands were communicated in the MLB MODEL project chat before the user supplied an 8:08 PM ET DraftKings screenshot and before the 8:20 PM ET DAL@NYG kickoff. This bundle is packaged after kickoff solely to preserve those already-stated pregame challenger values. No game outcome, live-game state, or post-kickoff market information may influence these values.'
