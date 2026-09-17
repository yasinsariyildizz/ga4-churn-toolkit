# GA4 Churn Toolkit — Architecture Demo

This first release does **not** calculate churn. It validates the final architecture:

**GitHub / PyPI package → BigQuery Notebook → Python orchestration → packaged SQL → BigQuery output tables → notebook results**

The demo calculates only:

- Users (`COUNT(DISTINCT user_pseudo_id)`)
- Sessions (`user_pseudo_id + ga_session_id`)
- Purchase events
- Purchase revenue (`ecommerce.purchase_revenue`)
- Event count

## Why this structure?

The Python engine is intentionally generic. It discovers ordered `.sql` files from the package and executes them as steps. Each SQL file contains lightweight metadata headers:

```sql
-- name: Step Name
-- output_table: output_table_name
-- result: false
```

When the real churn analysis is ready, the package/notebook architecture can remain the same. Replace the SQL step files with churn SQL.

## Install during GitHub testing

```python
%pip install -q --upgrade "ga4-churn-toolkit @ git+https://github.com/yasinsariyildizz/ga4-churn-toolkit.git@main"
```

After the GitHub test is stable, create a release tag and pin that version. After publishing to PyPI:

```python
%pip install -q "ga4-churn-toolkit==0.0.1"
```

## Usage

```python
from ga4_churn import GA4Analysis

analysis = GA4Analysis(
    project_id="your-gcp-project",
    dataset_id="analytics_123456789",
    output_dataset="ga4_analysis_demo",
    start_date="2026-08-01",
    end_date="2026-08-31",
)

analysis.validate()
analysis.dry_run()
analysis.run_all()
```

Or run steps separately:

```python
analysis.run_step(1)
analysis.run_step(2)
analysis.run_step(3)
analysis.run_step(4)
```

## Required permissions

The notebook identity needs permission to:

- Read the GA4 export dataset/tables
- Create/update tables in the output dataset
- Run BigQuery jobs in the billing project
