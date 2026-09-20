# GA4 Churn Toolkit

A lightweight, open-source **purchase-based churn analysis toolkit for GA4 BigQuery export data**.

The toolkit is designed for BigQuery / Colab Enterprise notebooks. Users provide four source/output inputs, then choose the churn threshold only when running churn analysis.

## Analysis & interpretation guides

Before using the outputs in reporting or decision-making, read the detailed methodology and interpretation guides:

- [Türkçe analiz ve yorumlama rehberi](docs/ANALYSIS_GUIDE_TR.md)
- [English analysis & interpretation guide](docs/ANALYSIS_GUIDE_EN.md)

These guides explain the churn logic, purchase-gap statistics, percentile interpretation, charts, threshold sensitivity, automatic insights, methodological limitations, and common interpretation mistakes.

## Inputs

```python
analysis = ChurnAnalysis(
    project_id="your-gcp-project",
    dataset_id="analytics_123456789",
    table_id="events_*",
    output_dataset_id="ga4_churn",
)
```

- `project_id`: GCP project containing the GA4 export
- `dataset_id`: GA4 BigQuery export dataset
- `table_id`: GA4 event table or wildcard, e.g. `events_*`
- `output_dataset_id`: dataset where analysis tables will be created

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
analysis.create_base_table()
analysis.purchase_day_distribution()
analysis.churn_analysis(90)
```

### `dry_run()`
Estimates BigQuery scan volume before creating output tables.

### `create_base_table()`
Creates one row per `user_pseudo_id` with:
- event count
- session count
- purchase count
- revenue
- first / last purchase date
- days since last purchase

### `purchase_day_distribution()`
Calculates days between consecutive distinct purchase dates for repeat purchasers and returns a richer statistical profile including:
- min / max
- mean / median
- standard deviation
- P10 / P25 / P50 / P75 / P90 / P95
- IQR
- coefficient of variation
- repeat-purchase coverage within 30 / 60 / 90 days
- histogram
- cumulative distribution by threshold day
- rule-based analytical insights about skewness and purchase-cycle variability

### `churn_analysis(churn_threshold)`
The churn threshold is supplied only at analysis time:

```python
analysis.churn_analysis(90)
```

Basic definition:

> A purchaser is churned when `days_since_last_purchase > churn_threshold`.

Users with no purchase are labelled `never_purchased` and excluded from the churn-rate denominator.

The function adds:
- active vs churned purchaser KPIs
- churned historical revenue share
- status diagnostics with average / median purchase and revenue values
- churn rate by purchase frequency (`1`, `2`, `3-5`, `6+` purchases)
- threshold sensitivity around the selected cutoff
- selected threshold position versus observed purchase-gap distribution
- analytical insight text
- standalone `ga4_churn_dashboard.html`

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
