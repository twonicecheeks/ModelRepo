# MODEL 2.4.7 post-install audit

Installed: 2026-09-07T02:01:15Z
Archive: `/Users/abbeyfelix/Developer/MODEL/archive/migrations/propsmadness-k-market-fallback-v247-before-20260906-220110`

Active service: `/Users/abbeyfelix/Library/Application Support/MODEL/service/model_service.py` v2.3.3
Canonical service source: `/Users/abbeyfelix/Developer/MODEL/services/market-service/src/model_service.py`

Expected OddsPapi usage per uncached refresh with the default config:
- 3 full-slate `odds-by-tournaments` requests: Pinnacle, Circa, FanDuel.
- Occasionally +1 participants-cache request only when participant identity cache is missing.
- 0 player-prop requests.

K market truth is now read from the already-captured PropsMadness structured K market. The target market has zero weight in expected K.
