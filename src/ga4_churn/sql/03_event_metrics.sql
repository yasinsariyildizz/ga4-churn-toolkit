-- name: Event Count
-- output_table: demo_event_metrics
-- result: false
-- cost_check: true

CREATE OR REPLACE TABLE `{{PROJECT_ID}}.{{OUTPUT_DATASET}}.demo_event_metrics` AS
SELECT
  COUNT(*) AS event_count
FROM `{{PROJECT_ID}}.{{DATASET_ID}}.events_*`
WHERE _TABLE_SUFFIX BETWEEN @start_suffix AND @end_suffix;
