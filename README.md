# GA4 Churn Toolkit

A lightweight, open-source **purchase-based churn analysis toolkit for GA4 BigQuery export data**.

The toolkit is designed for BigQuery / Colab Enterprise notebooks. Users provide only five inputs, then run four functions in order.

## Inputs

```python
analysis = ChurnAnalysis(
    project_id="your-gcp-project",
    dataset_id="analytics_123456789",
    table_id="events_*",
    output_dataset_id="ga4_churn",
    churn_threshold=90,
)
```

- `project_id`: GCP project containing the GA4 export
- `dataset_id`: GA4 BigQuery export dataset
- `table_id`: GA4 event table or wildcard, e.g. `events_*`
- `output_dataset_id`: dataset where analysis tables will be created
- `churn_threshold`: inactivity threshold in days after the last purchase

## Install

```python
%pip install -q --upgrade "ga4-churn-toolkit @ git+https://github.com/yasinsariyildizz/ga4-churn-toolkit.git@main"
```

Then:

```python
from ga4_churn import ChurnAnalysis
```

## Notebook workflow

```python
analysis.dry_run()
analysis.base_table()
analysis.purchase_day_distribution()
analysis.churn_analysis()
```

### `dry_run()`
Estimates BigQuery scan volume before creating output tables.

### `base_table()`
Creates one row per `user_pseudo_id` with:
- event count
- session count
- purchase count
- revenue
- first / last purchase date
- days since last purchase

### `purchase_day_distribution()`
Calculates days between consecutive distinct purchase dates for repeat purchasers and displays mean, standard deviation, P25, median, P75, P90, P95 and a histogram.

### `churn_analysis()`
Basic definition:

> A purchaser is churned when `days_since_last_purchase > churn_threshold`.

Users with no purchase are labelled `never_purchased` and excluded from the churn-rate denominator.

The function also creates a standalone `ga4_churn_dashboard.html` file in the notebook runtime.

## Output tables

```text
churn_base
purchase_day_gaps
churn_users
```

The source GA4 tables are never modified.

## Important note

If `table_id="events_*"`, this basic version scans all matching historical GA4 export tables. Run `dry_run()` first to inspect the expected scan volume.

## License

MIT
