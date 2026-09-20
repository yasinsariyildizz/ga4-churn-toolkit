# GA4 Churn Toolkit

Open-source, BigQuery-first churn analysis for GA4 ecommerce export data.

The toolkit is built for digital analytics teams that want a lightweight way to move from raw GA4 event export to a purchaser-level churn view without rebuilding the same SQL for every property.

It focuses on four things:

- creating a reusable purchaser-level analytical base,
- understanding repeat-purchase cadence before defining churn,
- classifying churn with an explicit inactivity cutoff,
- checking how sensitive the result is to that cutoff.

## Documentation

- [Türkçe analiz ve yorumlama rehberi](docs/ANALYSIS_GUIDE_TR.md)
- [English analysis and interpretation guide](docs/ANALYSIS_GUIDE_EN.md)

## Install

```python
%pip install -q --upgrade \
"ga4-churn-toolkit @ git+https://github.com/yasinsariyildizz/ga4-churn-toolkit.git@main"
```

```python
from ga4_churn import ChurnAnalysis
```

## Setup

```python
analysis = ChurnAnalysis(
    project_id="your-gcp-project",
    dataset_id="analytics_123456789",
    table_id="events_*",
    output_dataset_id="ga4_churn",
)
```

Inputs are intentionally limited to the source and output objects. The churn cutoff is selected later, after reviewing actual repeat-purchase behavior.

## Workflow

```python
analysis.dry_run()
analysis.create_base_table()
analysis.purchase_day_distribution()
analysis.churn_analysis(90)
```

### `dry_run()`
Checks expected BigQuery scan volume before running the workflow.

### `create_base_table()`
Builds a one-row-per-`user_pseudo_id` analytical base with:

- event and session volume,
- purchase count,
- historical revenue,
- first / last observed purchase date,
- days since last purchase,
- purchaser / repeat-purchaser diagnostics.

### `purchase_day_distribution()`
Profiles repeat-purchase cadence using consecutive distinct purchase dates.

Outputs include:

- mean / median purchase gap,
- P10 / P25 / P50 / P75 / P90 / P95,
- standard deviation and IQR,
- coefficient of variation,
- 30 / 60 / 90-day repeat-purchase coverage,
- purchase-gap histogram,
- cumulative repeat-purchase coverage,
- behavioral readout for threshold selection.

### `churn_analysis(churn_threshold)`

```python
analysis.churn_analysis(90)
```

Basic purchaser-level rule:

```text
purchase_count = 0
→ never_purchased

purchase_count > 0 and days_since_last_purchase <= threshold
→ active_purchaser

purchase_count > 0 and days_since_last_purchase > threshold
→ churned
```

The churn output includes:

- purchaser / active / churned base sizes,
- churn rate,
- one-time vs repeat purchaser diagnostics,
- active vs churned purchase and revenue profiles,
- churn rate by purchase-frequency band,
- threshold sensitivity,
- selected cutoff vs historical purchase-gap distribution,
- standalone HTML dashboard.

## Output tables

```text
churn_base
purchase_day_gaps
churn_users
```

The GA4 source tables are read-only. Analysis outputs are written to the selected output dataset.

## Metric scope

This is a descriptive purchaser-lifecycle analysis, not a churn prediction model.

A purchaser is classified using observed GA4 purchase history and the selected inactivity window. The framework does not claim that the chosen cutoff is universally correct; it exposes purchase cadence and sensitivity metrics so the cutoff can be defended with both behavioral evidence and business context.

## GA4 measurement notes

Results depend on the quality of the underlying implementation. Before using the output for CRM, retention or lifecycle decisions, validate:

- `purchase` event quality,
- duplicate transaction handling,
- revenue and currency implementation,
- GA4 export completeness,
- identity scope (`user_pseudo_id` vs logged-in customer identity),
- data freshness and observation window.

If `table_id="events_*"`, the current basic version can scan all matching historical export tables. Run `dry_run()` before a full-history execution.

## License

MIT
