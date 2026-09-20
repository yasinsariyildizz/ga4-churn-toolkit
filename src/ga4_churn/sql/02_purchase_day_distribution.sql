CREATE OR REPLACE TABLE `{{PROJECT_ID}}.{{OUTPUT_DATASET_ID}}.purchase_day_gaps` AS
WITH purchase_days AS (
  SELECT DISTINCT
    user_pseudo_id,
    SAFE.PARSE_DATE('%Y%m%d', event_date) AS purchase_date
  FROM `{{PROJECT_ID}}.{{DATASET_ID}}.{{TABLE_ID}}`
  WHERE event_name = 'purchase'
    AND user_pseudo_id IS NOT NULL
    AND event_date IS NOT NULL
),
ordered AS (
  SELECT
    user_pseudo_id,
    purchase_date,
    LAG(purchase_date) OVER (
      PARTITION BY user_pseudo_id
      ORDER BY purchase_date
    ) AS previous_purchase_date
  FROM purchase_days
)
SELECT
  user_pseudo_id,
  previous_purchase_date,
  purchase_date,
  DATE_DIFF(purchase_date, previous_purchase_date, DAY) AS gap_days
FROM ordered
WHERE previous_purchase_date IS NOT NULL;
