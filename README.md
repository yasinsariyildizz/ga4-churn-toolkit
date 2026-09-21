# GA4 Churn Toolkit

Open-source, BigQuery-first churn analysis for GA4 ecommerce export data. The current version runs from Google Colab and uses **GA4 `user_id`** as the user key.

## Important identity rule

Only rows where `user_id` is populated are included.

This means the analysis represents identified / logged-in users for which your GA4 implementation sends `user_id`. Anonymous users with only `user_pseudo_id` are excluded.

Because of this, results from this version should not be compared one-to-one with older `user_pseudo_id`-based results.

## Documentation

- [Türkçe kullanım ve yorumlama rehberi](docs/ANALYSIS_GUIDE_TR.md)
- [English analysis guide](docs/ANALYSIS_GUIDE_EN.md)

## Google Colab notebook

[Open the Colab notebook source](notebooks/ga4_churn_colab.ipynb)

## Install

```python
%pip install -q --upgrade \
"ga4-churn-toolkit @ git+https://github.com/yasinsariyildizz/ga4-churn-toolkit.git@main"
```

## Setup

```python
from ga4_churn import ChurnAnalysis

analysis = ChurnAnalysis(
    project_id="your-gcp-project",
    dataset_id="analytics_123456789",
    table_id="events_*",
    output_dataset_id="ga4_churn",
)
```

## Workflow

```python
analysis.dry_run()
analysis.create_base_table()
analysis.purchase_day_distribution()
analysis.churn_analysis(60, 90)
```

The last line means:

```text
0–60 days since last purchase   → active_purchaser
61–90 days                      → pre_churn
more than 90 days               → churned
```

The first value is the **pre-churn threshold** and must be smaller than the churn threshold.

## Main outputs

### `create_base_table()`
Creates one row per `user_id` with event, session, purchase, revenue and last-purchase information.

### `purchase_day_distribution()`
Shows how many days typically pass between consecutive purchase days for repeat purchasers. It includes percentile statistics, histogram and cumulative coverage.

### `churn_analysis(pre_churn_threshold, churn_threshold)`
Creates three purchaser states:

- `active_purchaser`
- `pre_churn`
- `churned`

It also returns:

- active / pre-churn / churned user counts,
- pre-churn and churn rates,
- historical revenue shares,
- purchase-frequency comparisons,
- churn threshold sensitivity,
- HTML dashboard.

## Output tables

```text
churn_base
purchase_day_gaps
churn_users
```

The GA4 source tables are never modified.

## Required GA4 setup

`user_id` must be implemented in GA4 for this version to produce meaningful results. If your property does not send `user_id`, the analysis base may be empty or much smaller than your total GA4 user population.

## License

MIT
