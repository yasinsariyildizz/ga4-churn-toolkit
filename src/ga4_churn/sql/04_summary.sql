-- name: Final Summary
-- output_table: demo_summary
-- result: true
-- cost_check: false

CREATE OR REPLACE TABLE `{{PROJECT_ID}}.{{OUTPUT_DATASET}}.demo_summary` AS
SELECT
  us.users,
  us.sessions,
  p.purchase_events,
  p.revenue,
  e.event_count
FROM `{{PROJECT_ID}}.{{OUTPUT_DATASET}}.demo_user_session_metrics` AS us
CROSS JOIN `{{PROJECT_ID}}.{{OUTPUT_DATASET}}.demo_purchase_metrics` AS p
CROSS JOIN `{{PROJECT_ID}}.{{OUTPUT_DATASET}}.demo_event_metrics` AS e;
