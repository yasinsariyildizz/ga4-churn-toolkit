# GA4 Churn Toolkit

Open-source, BigQuery-first churn analysis for GA4 ecommerce export data. The current version runs from Google Colab, uses **GA4 `user_id`** as the analysis key, and classifies purchasers into **active**, **pre-churn**, and **churned** states.

## Important identity rule

Only rows where `user_id` is populated are included.

This means the analysis represents identified users for which the GA4 implementation sends `user_id`. Anonymous users with only `user_pseudo_id` are excluded.

Results from this version should therefore not be compared one-to-one with older `user_pseudo_id`-based outputs.

## Documentation

- [Türkçe analiz ve yorumlama rehberi](docs/ANALYSIS_GUIDE_TR.md)
- [English analysis and interpretation guide](docs/ANALYSIS_GUIDE_EN.md)

The guides cover not only execution, but also:

- how to interpret purchase-gap statistics,
- how to use P75 / P90 / P95,
- how to read the purchase-gap histogram,
- how cumulative purchase-gap coverage should be interpreted,
- how pre-churn and churn thresholds can be calibrated,
- how one-time and repeat purchasers should be compared,
- how threshold sensitivity should be reported,
- where GA4 measurement and `user_id` coverage can bias the result.

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
0–60 days since last purchase       → active_purchaser
61–90 days                           → pre_churn
more than 90 days                    → churned
```

The first value is the **pre-churn threshold** and must be smaller than the churn threshold.

## Main outputs

### `dry_run()`
Estimates BigQuery scan volume before the analysis tables are created.

### `create_base_table()`
Creates one row per `user_id` with:

- first / last observed event date,
- event and session counts,
- purchase count,
- historical purchase revenue,
- first / last purchase date,
- days since last purchase.

### `purchase_day_distribution()`
Analyzes the number of days between consecutive distinct purchase dates for repeat purchasers.

Outputs include:

- mean and median gap,
- P10 / P25 / P50 / P75 / P90 / P95,
- standard deviation,
- IQR,
- coefficient of variation,
- purchase-gap histogram,
- cumulative purchase-gap coverage.

This step is intended to support pre-churn and churn threshold selection rather than to produce a churn classification by itself.

### `churn_analysis(pre_churn_threshold, churn_threshold)`
Creates four states:

- `never_purchased`
- `active_purchaser`
- `pre_churn`
- `churned`

It also returns:

- active / pre-churn / churned user counts,
- pre-churn and churn rates,
- one-time vs repeat purchaser breakdowns,
- pre-churn and churn historical revenue shares,
- purchase-frequency comparisons,
- churn-threshold sensitivity,
- purchase-gap coverage at the selected cutoffs,
- standalone HTML dashboard.

## Output tables

```text
churn_base
purchase_day_gaps
churn_users
```

The GA4 source tables are never modified.

## Threshold selection

The toolkit does not select thresholds automatically.

Recommended review sequence:

```text
1. Validate data history and purchase tracking
2. Review median and P75
3. Review P90 and P95
4. Inspect histogram shape
5. Inspect cumulative purchase-gap coverage
6. Define candidate pre-churn and churn windows
7. Compare with the natural purchase cycle of the business
8. Review churn threshold sensitivity
9. Compare one-time and repeat purchaser results
10. Revisit thresholds periodically as behavior changes
```

For example:

```text
Median = 30 days
P75 = 52 days
P90 = 88 days
P95 = 130 days
```

A candidate configuration may be:

```text
Pre-churn threshold = 60 days
Churn threshold = 90 days
```

This is an analytical starting point, not a universal rule.

## Required GA4 setup

`user_id` must be implemented consistently for this version to produce representative results.

Before using the output for CRM, retention, lifecycle or campaign decisions, validate:

- `user_id` coverage,
- `purchase` event quality,
- duplicate transaction handling,
- revenue and currency implementation,
- GA4 export completeness,
- data freshness,
- observation-window length,
- seasonality and category purchase cycles.

## License

MIT
