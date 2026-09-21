# GA4 Churn Toolkit

Open-source, BigQuery-first churn analysis for GA4 ecommerce export data.

The toolkit now runs through **Google Colab**. Colab is used only as the interface and orchestration layer; the heavy data processing still happens in BigQuery.

## Open in Colab

Use the ready notebook:

[Open `ga4_churn_colab.ipynb`](notebooks/ga4_churn_colab.ipynb)

The Colab workflow is:

```text
Install package
→ Enter BigQuery source information
→ Sign in with Google
→ Dry run
→ Create base table
→ Review repeat-purchase intervals
→ Run churn analysis
→ View / download HTML dashboard
```

## Documentation

- [Türkçe kullanım ve yorumlama rehberi](docs/ANALYSIS_GUIDE_TR.md)
- [English analysis and interpretation guide](docs/ANALYSIS_GUIDE_EN.md)

## Colab inputs

The user only provides four source/output fields:

```python
PROJECT_ID = "your-gcp-project"
DATASET_ID = "analytics_123456789"
TABLE_ID = "events_*"
OUTPUT_DATASET_ID = "ga4_churn"
```

In the Colab notebook these are shown as editable form fields.

The churn threshold is selected only in the final churn step:

```python
CHURN_THRESHOLD = 90
```

## Google authentication

The Colab notebook authenticates with the signed-in Google account:

```python
from google.colab import auth
auth.authenticate_user()
```

That account must have permission to:

- read the GA4 BigQuery export dataset,
- run BigQuery jobs in the selected project,
- create the output dataset or write tables to it.

No service-account JSON file is required for the normal Colab flow.

## Install

The ready notebook installs the package directly from GitHub:

```python
%pip install -q --upgrade \
"ga4-churn-toolkit @ git+https://github.com/yasinsariyildizz/ga4-churn-toolkit.git@main"
```

## Workflow

```python
analysis.dry_run()
analysis.create_base_table()
analysis.purchase_day_distribution()
analysis.churn_analysis(90)
```

### `dry_run()`
Checks estimated BigQuery scan volume before analysis tables are created.

### `create_base_table()`
Builds a one-row-per-`user_pseudo_id` table with purchase, session, revenue and last-purchase information.

### `purchase_day_distribution()`
Shows how many days typically pass between repeat purchase days and provides statistics and charts to help evaluate a sensible churn cutoff.

### `churn_analysis(churn_threshold)`
Classifies purchasers using the selected number of inactive days and produces churn KPIs, diagnostic comparisons, threshold sensitivity and an HTML dashboard.

## HTML dashboard in Colab

After churn analysis:

```python
churn_result = analysis.churn_analysis(90)
```

The notebook can display the generated dashboard inline and download it to the user's computer:

```python
from google.colab import files
files.download(churn_result["dashboard_path"])
```

## Where does the data run?

Even though the notebook is opened in Colab, raw GA4 data is **not downloaded into Colab for processing**.

The flow remains:

```text
Google Colab
    ↓
Python package
    ↓
BigQuery SQL jobs
    ↓
BigQuery output tables
    ↓
Small summary results / charts in Colab
```

The source GA4 tables remain read-only.

## Output tables

```text
churn_base
purchase_day_gaps
churn_users
```

## Important measurement note

This is a descriptive purchase-based churn classification, not a churn prediction model.

Before using the output for CRM or retention decisions, validate:

- `purchase` event quality,
- duplicate purchase handling,
- revenue implementation,
- GA4 export completeness,
- `user_pseudo_id` identity limitations,
- data freshness,
- whether the selected observation period is long enough for the chosen churn threshold.

If `table_id="events_*"`, all matching historical export tables may be scanned. Use `dry_run()` first.

## License

MIT
