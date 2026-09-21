CREATE OR REPLACE TABLE `{{PROJECT_ID}}.{{OUTPUT_DATASET_ID}}.churn_base` AS
WITH raw AS (
  SELECT
    user_id,
    SAFE.PARSE_DATE('%Y%m%d', event_date) AS event_date,
    event_name,
    (
      SELECT ep.value.int_value
      FROM UNNEST(event_params) ep
      WHERE ep.key = 'ga_session_id'
      LIMIT 1
    ) AS ga_session_id,
    COALESCE(ecommerce.purchase_revenue, 0) AS purchase_revenue
  FROM `{{PROJECT_ID}}.{{DATASET_ID}}.{{TABLE_ID}}`
  WHERE user_id IS NOT NULL
    AND event_date IS NOT NULL
),
analysis_context AS (
  SELECT MAX(event_date) AS analysis_date
  FROM raw
),
user_agg AS (
  SELECT
    user_id,
    MIN(event_date) AS first_event_date,
    MAX(event_date) AS last_event_date,
    COUNT(*) AS event_count,
    COUNT(DISTINCT ga_session_id) AS session_count,
    COUNTIF(event_name = 'purchase') AS purchase_count,
    SUM(IF(event_name = 'purchase', purchase_revenue, 0)) AS revenue,
    MIN(IF(event_name = 'purchase', event_date, NULL)) AS first_purchase_date,
    MAX(IF(event_name = 'purchase', event_date, NULL)) AS last_purchase_date
  FROM raw
  GROUP BY user_id
)
SELECT
  u.*,
  c.analysis_date,
  DATE_DIFF(c.analysis_date, u.last_purchase_date, DAY) AS days_since_last_purchase
FROM user_agg u
CROSS JOIN analysis_context c;
