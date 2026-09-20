# GA4 Churn Toolkit — Analysis & Interpretation Guide

This guide documents the methodology behind the purchase-based churn workflow in `ga4-churn-toolkit` and how to read the outputs. It is written for digital analytics, marketing analytics, CRM analytics, lifecycle and BI teams working with GA4 BigQuery export data.

This is not a predictive churn model. It does not score the probability that a user will churn in the future. It builds a purchaser-level behavioral view from historical GA4 purchase data and classifies users against a selected inactivity window.

---

## 1. Analytical framework

The core logic is purchaser-level recency.

A `user_pseudo_id` enters the purchaser base once at least one `purchase` event is observed. For each purchaser, the workflow calculates the number of days between the last observed purchase and the analysis date:

```text
days_since_last_purchase = analysis_date - last_purchase_date
```

The inactivity cutoff is passed only when churn classification is run:

```python
analysis.churn_analysis(90)
```

For a 90-day cutoff:

```text
purchase_count = 0
→ never_purchased

purchase_count > 0
and days_since_last_purchase <= 90
→ active_purchaser

purchase_count > 0
and days_since_last_purchase > 90
→ churned
```

This is a behavioral inactivity rule. It is not the same as a subscription cancellation flag, CRM lifecycle status, or a confirmed customer-loss record.

---

## 2. Metric scope and analysis date

The analysis date is derived from the source data:

```text
analysis_date = MAX(event_date)
```

This keeps the setup lightweight, but data freshness becomes part of the metric definition.

Example:

```text
Today: September 20
Latest event_date in BigQuery: August 31
```

The churn classification is evaluated as of August 31, not September 20.

Always review `analysis_date` before sharing the result.

---

## 3. Input model

```python
analysis = ChurnAnalysis(
    project_id="your-project",
    dataset_id="analytics_123456789",
    table_id="events_*",
    output_dataset_id="ga4_churn",
)
```

| Input | Use |
|---|---|
| `project_id` | GCP project containing the GA4 export |
| `dataset_id` | GA4 BigQuery export dataset |
| `table_id` | Source table or wildcard such as `events_*` |
| `output_dataset_id` | Dataset where analytical outputs are written |

The churn cutoff is deliberately excluded from initialization so repeat-purchase behavior can be reviewed before selecting an inactivity window.

---

# 4. Recommended workflow

```python
analysis.dry_run()
analysis.create_base_table()
analysis.purchase_day_distribution()
analysis.churn_analysis(90)
```

The workflow answers four practical questions:

```text
1. How much data will the queries scan?
2. What does the purchaser base look like?
3. What is the natural repeat-purchase cadence?
4. How does churn look under the selected inactivity cutoff?
```

---

# 5. `dry_run()` — Query cost check

```python
analysis.dry_run()
```

This estimates BigQuery scan volume before the analytical queries are executed.

Main output:

```text
Estimated scan: X GB
```

This is not a business metric. It is a query-footprint and cost-control check.

If `table_id="events_*"`, the query may scan all matching historical export tables.

Review the estimate when:

- the expected scan is much larger than anticipated,
- the wrong GA4 property or dataset may have been selected,
- a full-history scan is unnecessary,
- production-scale data is being used for a quick validation run.

This is particularly useful in agency and multi-client environments where BigQuery cost governance matters.

---

# 6. `create_base_table()` — Purchaser-level analytical base

```python
analysis.create_base_table()
```

Output grain:

```text
1 row = 1 user_pseudo_id
```

Output table:

```text
<output_dataset>.churn_base
```

This table is the user-level feature layer for the churn workflow.

## Core fields

| Field | Definition |
|---|---|
| `user_pseudo_id` | GA4 device/browser-scoped user identifier |
| `first_event_date` | First event date observed in the export |
| `last_event_date` | Last event date observed in the export |
| `event_count` | Total observed event volume |
| `session_count` | Distinct `ga_session_id` count |
| `purchase_count` | Number of purchase events |
| `revenue` | Sum of `ecommerce.purchase_revenue` |
| `first_purchase_date` | First observed purchase date |
| `last_purchase_date` | Last observed purchase date |
| `analysis_date` | Maximum `event_date` in the source |
| `days_since_last_purchase` | Purchase recency |

## Users

Distinct `user_pseudo_id` count. This should not be interpreted as an exact customer count because GA4 identity is generally device/browser scoped.

## Purchasers

Users with at least one observed purchase. This is the base population for purchaser churn.

## One-time purchasers

Users with exactly one observed purchase. From a lifecycle perspective, this is the purchaser segment that has not yet demonstrated repeat behavior.

## Repeat purchasers

Users with more than one observed purchase. This population drives repeat-purchase cadence analysis.

## Purchaser rate

```text
purchasers / observed users
```

This is not a session conversion rate. It is a user-level observed purchaser share.

## Repeat rate

```text
repeat purchasers / purchasers
```

This summarizes how much of the purchaser base has demonstrated repeat buying behavior.

## Revenue

Historical revenue observed on GA4 purchase events.

Measurement quality matters. Duplicate purchases, transaction deduplication issues, currency mapping, missing revenue and consent or tagging gaps can all affect this number. GA4 revenue should not automatically be expected to reconcile one-to-one with finance or ERP revenue.

---

# 7. `purchase_day_distribution()` — Repeat-purchase cadence

```python
analysis.purchase_day_distribution()
```

This step profiles repurchase timing before the inactivity cutoff is selected.

Distinct purchase dates are ordered per user and consecutive day gaps are calculated.

Example:

```text
January 10
January 25
February 20
```

produces:

```text
15 days
26 days
```

Multiple purchases on the same day count as one purchase date for interval analysis. This keeps order frequency separate from day-gap distribution.

One-time purchasers do not contribute because they have no repeat interval.

---

# 8. Distribution metrics

## Gap observations

Total number of consecutive purchase intervals.

A user with five distinct purchase dates contributes four observations. Therefore:

```text
gap observations != repeat purchasers
```

is expected.

## Mean gap

Average repeat-purchase interval. It is sensitive to long-tail behavior and should not be used alone as a churn cutoff.

## Median / P50

A more robust center point for repeat-purchase cadence.

```text
Median = 32 days
```

means roughly half of observed intervals are 32 days or shorter.

## P25 / P75

These define the middle 50% of observed repeat-purchase intervals.

```text
P25 = 18
P75 = 56
```

suggests the core cadence is concentrated around an 18–56 day window.

## IQR

```text
IQR = P75 - P25
```

A narrow IQR suggests a relatively consistent purchase cadence. A wide IQR suggests a more heterogeneous purchaser base, where one global churn cutoff may fit some segments better than others.

## P90 / P95

Useful upper-tail references for threshold calibration.

```text
P90 = 84 days
P95 = 126 days
```

A 90-day cutoff would sit near the upper end of historical repeat-purchase behavior.

P90 or P95 should not be treated as an automatic churn threshold. They are behavioral baselines that still need to be combined with category cycle, replenishment period, seasonality and CRM strategy.

## Standard deviation

Measures purchase-gap volatility. A high value can indicate substantial variation in repurchase cadence across the purchaser base.

## Coefficient of Variation

```text
CV = standard deviation / mean
```

A scale-independent dispersion measure.

Practical diagnostic:

```text
CV < 0.5   → relatively concentrated cadence
0.5–1.0    → moderate variability
CV >= 1.0  → high variability
```

These are directional diagnostics, not hard statistical rules.

---

# 9. Purchase-gap histogram

Buckets:

```text
0–7
8–14
15–30
31–60
61–90
91–180
181–365
366+
```

Each bar represents observed interval volume within that range.

If most observations sit in the 15–30 and 31–60 day buckets, a large part of the purchaser base may be cycling back within roughly two months.

If the 181+ buckets are material, investigate:

- long replenishment cycles,
- seasonality,
- category mix,
- high-value / low-frequency segments,
- long observation windows.

The histogram shows distribution shape. It should not be used as a standalone cutoff rule.

---

# 10. Cumulative repeat-purchase coverage

This chart answers:

```text
What share of observed purchase intervals happened within X days?
```

Example:

```text
30 days  → 46%
60 days  → 73%
90 days  → 89%
180 days → 97%
```

If the 90-day coverage is 89%, approximately 89% of historical repeat-purchase intervals were 90 days or shorter.

This does not mean 89% of users return within 90 days. The metric scope is interval-level, not user-level.

---

# 11. Purchase behavior readout

The notebook surfaces short analyst notes from the distribution output.

Example:

```text
Median repeat-purchase interval: 31 days
Middle 50% range: 18–55 days
Distribution: right-skewed
Cadence variability: high
```

These notes are intended to make the output easier to scan. The inactivity cutoff remains an analyst / business decision.

---

# 12. `churn_analysis(threshold)` — Purchaser inactivity classification

```python
analysis.churn_analysis(90)
```

Churn rate:

```text
churned purchasers / all purchasers
```

Never-purchased users are excluded from the denominator.

Example:

```text
Observed users      1,000,000
Purchasers            200,000
Churned                60,000

Churn rate = 60,000 / 200,000 = 30%
```

Using 60,000 / 1,000,000 would dilute the purchaser-churn metric with users who were never in the purchaser lifecycle.

---

# 13. Churn KPIs

## Active purchasers

Purchasers whose last purchase falls within the selected inactivity window.

## Churned purchasers

Purchasers whose purchase recency exceeds the selected cutoff.

## One-time purchasers

Purchasers who have not demonstrated repeat buying behavior after acquisition.

## Churned one-time buyers

Users with one purchase whose recency exceeds the cutoff.

## Churned repeat buyers

Users with prior repeat behavior whose recency now exceeds the cutoff.

This split is useful for CRM activation because one-time lapse and established-repeat lapse are not necessarily the same lifecycle problem.

---

# 14. Churned historical revenue share

```text
historical revenue from churned purchasers
-----------------------------------------
historical revenue from all purchasers
```

This provides a revenue-exposure view.

Example:

```text
Churn rate = 25%
Churned historical revenue share = 41%
```

The churned segment may have contributed a disproportionately large share of historical purchaser revenue.

Do not label this metric as `lost revenue`, `future revenue loss` or `incremental revenue opportunity`. Historical contribution and future loss are different concepts.

---

# 15. Status diagnostics

Active, churned and never-purchased groups are compared on:

- user volume,
- average purchases,
- median purchases,
- average revenue,
- median revenue,
- average inactivity days.

Mean and median should be read together.

```text
Active avg revenue    = 1,250
Active median revenue = 310
```

can indicate a high-value tail pulling the mean upward. This is common in digital commerce data where revenue distributions are often right-skewed.

---

# 16. Purchaser status chart

Compares absolute active and churned purchaser volume.

The chart shows volume, not rate. Interpret it together with churn rate and purchaser-base size.

---

# 17. Churn rate by purchase frequency

Purchasers are grouped into:

```text
1 purchase
2 purchases
3–5 purchases
6+ purchases
```

Churn rate is calculated separately for each band.

This helps show the relationship between purchaser depth and retention behavior.

Example:

```text
1 purchase   → 52%
2 purchases  → 34%
3–5          → 19%
6+           → 10%
```

This can be a useful lifecycle-segmentation diagnostic. It is still descriptive, not causal. An association between purchase frequency and lower churn does not prove that increasing purchase frequency will itself cause churn to fall.

---

# 18. Threshold sensitivity

This chart shows how dependent the churn metric is on the cutoff assumption.

For a 90-day selected threshold:

```text
60 days  → 36%
75 days  → 31%
90 days  → 27%
105 days → 24%
120 days → 21%
150 days → 17%
```

As the cutoff increases, churn classification becomes more conservative and the churn rate will usually decline.

### Stable case

```text
75 days  = 30%
90 days  = 29%
105 days = 28%
```

The metric is relatively stable around the selected cutoff.

### Sensitive case

```text
75 days  = 42%
90 days  = 29%
105 days = 18%
```

The metric is highly sensitive to the cutoff assumption. In this case, reporting a single churn rate without a sensitivity band can be misleading.

---

# 19. Threshold context / gap coverage

The selected cutoff is positioned against the historical repeat-purchase distribution.

```text
Threshold = 90 days
Gap coverage = 91%
P90 = 86 days
```

A useful business readout would be:

```text
The 90-day inactivity window covers roughly 91% of observed repeat-purchase intervals and sits slightly above the historical P90.
```

This is a behavioral sanity check, not proof that the cutoff is optimal.

---

# 20. Threshold calibration

Review the following together:

1. median purchase gap,
2. P75 / P90 / P95,
3. histogram shape,
4. cumulative coverage,
5. sensitivity curve,
6. category replenishment cycle,
7. seasonality,
8. campaign / promotion cadence,
9. CRM contact strategy,
10. observation-window length.

Example:

```text
Median = 29
P75 = 51
P90 = 87
P95 = 128
```

Candidate scenarios might be 60 / 90 / 120 days. The appropriate cutoff depends on both observed behavior and business use case.

---

# 21. HTML dashboard

`churn_analysis()` creates:

```text
ga4_churn_dashboard.html
```

The dashboard includes:

- selected inactivity threshold,
- purchaser base,
- active purchaser volume,
- churned purchaser volume,
- churn rate,
- gap coverage,
- churned historical revenue share,
- status diagnostics,
- churn by purchase frequency,
- threshold sensitivity,
- analyst notes.

The dashboard is intended for operational sharing. Metric definitions remain the same as in the notebook.

---

# 22. Measurement caveats

## `user_pseudo_id` is not a customer ID

GA4 `user_pseudo_id` is generally device/browser scoped. The same person may produce multiple identifiers across mobile and desktop, different browsers, cookie resets or consent-state changes.

Without logged-in user stitching, this should be interpreted as an observed-user analysis rather than a true customer-level analysis.

## Purchase tracking quality

The following implementation issues directly affect churn output:

- duplicate purchase events,
- missing purchases,
- broken `transaction_id`,
- revenue duplication,
- currency mismatch,
- delayed or partial tagging.

Ecommerce measurement QA should be completed before the churn output is used for lifecycle or CRM decisions.

## Export start-date bias

The BigQuery export start date is not the customer lifecycle start date. If export history is short, `first_purchase_date`, `purchase_count` and `repeat rate` may understate historical behavior.

## Observation-window bias

With a 90-day cutoff, a purchaser whose last purchase was 30 days ago has not yet had a full 90-day outcome window. The user is classified as active, but that does not mean they will remain active.

## Classification is not prediction

This framework answers:

```text
Which historical purchasers are currently in the churned segment under the selected inactivity rule?
```

It does not answer:

```text
Who will churn in the next 30 days?
```

Prediction requires a separate outcome definition, feature set, training window and model-validation process.

## Seasonality

The basic version does not adjust for seasonality. Use a global cutoff cautiously in categories such as travel, insurance, annual renewal, gifting, fashion seasonality and durable goods.

---

# 23. Reporting recommendation

A churn rate is more useful when reported with its behavioral context.

Example:

```text
Inactivity threshold          90 days
Purchaser churn rate          27%
Observed gap P90              84 days
Gap coverage @ 90d            91%
Churn @ 75d                   31%
Churn @ 105d                  24%
One-time purchaser churn      43%
6+ purchase churn             10%
Churned historical rev. share 38%
```

This keeps both the KPI and the assumptions behind it visible.

---

# 24. Analyst checklist

- [ ] Correct GCP project selected?
- [ ] Correct GA4 property / dataset selected?
- [ ] Does `events_*` cover the intended observation period?
- [ ] Is the dataset fresh?
- [ ] Has purchase-event QA been completed?
- [ ] Are revenue and currency mappings reliable?
- [ ] Has duplicate-transaction risk been checked?
- [ ] Is the purchaser base large enough to interpret?
- [ ] Are repeat-purchase observations sufficient?
- [ ] Have P50 / P75 / P90 / P95 been reviewed?
- [ ] Have the histogram and cumulative coverage been reviewed?
- [ ] Has threshold sensitivity been checked?
- [ ] Have one-time and repeat purchasers been separated in the readout?
- [ ] Is historical revenue share clearly distinguished from future lost revenue?
- [ ] Is the `user_pseudo_id` identity limitation documented?

---

# 25. Terminology

**Grain** — The analytical unit represented by one row. In `churn_base`, one row = one `user_pseudo_id`.

**Purchaser base** — Observed users with at least one purchase event.

**Repeat purchaser** — Purchaser with more than one observed purchase.

**Purchase cadence** — Timing pattern of repeat purchasing.

**Purchase gap** — Number of days between consecutive distinct purchase dates.

**Recency** — Days from last purchase to the analysis date.

**Inactivity threshold / cutoff** — Recency boundary used to classify a purchaser as churned.

**P90** — Value at or below which roughly 90% of observed intervals fall.

**IQR** — P75 minus P25; spread of the middle 50% of the distribution.

**Sensitivity analysis** — Testing how much the churn metric moves when the cutoff changes.

**Metric scope** — Population and grain on which a KPI is calculated.

---

## Summary

```text
Validate query scope
        ↓
Build purchaser-level base
        ↓
Profile repeat-purchase cadence
        ↓
Select a business-relevant inactivity window
        ↓
Classify active vs churned purchasers
        ↓
Check threshold sensitivity
        ↓
Read frequency + revenue diagnostics
        ↓
Use outputs for lifecycle / CRM / retention analysis
```

The main principle is simple: churn rate should never be read in isolation. The purchaser base, observation window and inactivity cutoff are part of the metric definition and should remain visible in any reporting or decision-making context.
