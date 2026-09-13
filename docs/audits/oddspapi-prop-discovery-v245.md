# MODEL 2.4.5 OddsPapi prop-discovery + clipboard confirmation post-install audit

Installed: 2026-09-06T23:27:27Z
Archive: `/Users/abbeyfelix/Developer/MODEL/archive/migrations/oddspapi-prop-discovery-copy-v245-before-20260906-192724`

Active service: `/Users/abbeyfelix/Library/Application Support/MODEL/service/model_service.py` v2.3.1
Canonical service source: `/Users/abbeyfelix/Developer/MODEL/services/market-service/src/model_service.py`

Expected full-slate OddsPapi calls per uncached refresh with default config:
- Pinnacle
- Circa
- FanDuel
- DraftKings
- Caesars
- BetMGM
- Hard Rock Bet

Each `odds-by-tournaments` request contains exactly one `bookmakers` slug and the service enforces the endpoint cooldown. FanDuel is reused for both moneyline context and player props, so the union is seven calls, not eight.

The K reference is labelled `retail_no_vig_consensus`, never `sharp_consensus`.
