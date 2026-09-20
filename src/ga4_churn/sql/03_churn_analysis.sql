CREATE OR REPLACE TABLE `{{PROJECT_ID}}.{{OUTPUT_DATASET_ID}}.churn_users` AS
SELECT
  *,
  @churn_threshold AS churn_threshold,
  CASE
    WHEN purchase_count = 0 THEN 'never_purchased'
    WHEN days_since_last_purchase > @churn_threshold THEN 'churned'
    ELSE 'active_purchaser'
  END AS churn_status,
  purchase_count > 0
    AND days_since_last_purchase > @churn_threshold AS churn_flag
FROM `{{PROJECT_ID}}.{{OUTPUT_DATASET_ID}}.churn_base`;
