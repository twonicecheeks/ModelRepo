# Data Pipeline v1.2.3 — Static Control Plane

Installed: 2026-09-06T19:36:02Z
Archive: `/Users/abbeyfelix/Developer/MODEL/archive/migrations/data-pipeline-v123-static-control-plane-before-20260906-153600`

Why this replaces v1.2.2:
- v1.2.2 still mounted Data Pipeline relative to dynamically managed popup surfaces.
- The panel could disappear later even though sync/data storage succeeded.
- Reopening the popup rebuilt it, which is why the controls came back.

v1.2.3 clean cut:
- popup.html owns one permanent `#modelControlPlaneRoot`
- Data Pipeline owns static `#modelDataPipelineHost`
- Trust Layer owns static `#modelTrustHost`
- neither feature moves itself relative to Batch Workflow anymore
- temporary bootstrap/remount runtime is deleted from active source
- no polling observer or remount interval remains
- old Batch Workflow remains quarantined while model consumers are extracted

No model coefficient, OddsPapi calculation, or provider schema changed.
