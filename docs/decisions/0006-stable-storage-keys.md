# Decision 0006 — Stable storage keys

Created: 2026-09-06T18:59:40Z

Active pipeline storage uses stable keys rather than release-numbered keys:
- model_pm_table_snapshot_current
- model_mlb_official_starter_board_current
- model_data_pipeline_audit_current

Schema/version metadata belongs inside the stored object. Release-numbered storage keys are migration debt and are retired.
