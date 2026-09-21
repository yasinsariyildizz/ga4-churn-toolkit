CREATE OR REPLACE TABLE `{{PROJECT_ID}}.{{OUTPUT_DATASET_ID}}.churn_users` AS
SELECT
  *,
  @pre_churn_threshold AS pre_churn_threshold,
  @churn_threshold AS churn_threshold,
  CASE
    WHEN purchase_count = 0 THEN 'never_purchased'
    WHEN days_since_last_purchase > @churn_threshold THEN 'churned'
    WHEN days_since_last_purchase > @pre_churn_threshold THEN 'pre_churn'
    ELSE 'active_purchaser'
  END AS churn_status,
  purchase_count > 0
    AND days_since_last_purchase > @pre_churn_threshold
    AND days_since_last_purchase <= @churn_threshold AS pre_churn_flag,
  purchase_count > 0
    AND days_since_last_purchase > @churn_threshold AS churn_flag
FROM `{{PROJECT_ID}}.{{OUTPUT_DATASET_ID}}.churn_base`;
