-- name: Purchase & Revenue Metrics
-- output_table: demo_purchase_metrics
-- result: false
-- cost_check: true

CREATE OR REPLACE TABLE `{{PROJECT_ID}}.{{OUTPUT_DATASET}}.demo_purchase_metrics` AS
SELECT
  COUNTIF(event_name = 'purchase') AS purchase_events,
  COALESCE(
    SUM(IF(event_name = 'purchase', ecommerce.purchase_revenue, 0)),
    0
  ) AS revenue
FROM `{{PROJECT_ID}}.{{DATASET_ID}}.events_*`
WHERE _TABLE_SUFFIX BETWEEN @start_suffix AND @end_suffix;
