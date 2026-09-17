-- name: User & Session Metrics
-- output_table: demo_user_session_metrics
-- result: false
-- cost_check: true

CREATE OR REPLACE TABLE `{{PROJECT_ID}}.{{OUTPUT_DATASET}}.demo_user_session_metrics` AS
WITH base AS (
  SELECT
    user_pseudo_id,
    (
      SELECT ep.value.int_value
      FROM UNNEST(event_params) AS ep
      WHERE ep.key = 'ga_session_id'
      LIMIT 1
    ) AS ga_session_id
  FROM `{{PROJECT_ID}}.{{DATASET_ID}}.events_*`
  WHERE _TABLE_SUFFIX BETWEEN @start_suffix AND @end_suffix
)
SELECT
  COUNT(DISTINCT user_pseudo_id) AS users,
  COUNT(
    DISTINCT IF(
      user_pseudo_id IS NULL OR ga_session_id IS NULL,
      NULL,
      CONCAT(user_pseudo_id, '-', CAST(ga_session_id AS STRING))
    )
  ) AS sessions
FROM base;
