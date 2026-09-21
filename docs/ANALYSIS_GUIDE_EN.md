# GA4 Churn Toolkit — Analysis & Interpretation Guide

This document explains the methodology behind the purchase-based churn workflow in `ga4-churn-toolkit`, the meaning of each output, and how the results should be interpreted.

The analysis uses **GA4 `user_id`** as the user key and classifies identified purchasers into three purchase-status groups:

```text
active_purchaser
pre_churn
churned
```

Example:

```python
analysis.churn_analysis(60, 90)
```

This means:

```text
0–60 days since last purchase        → active_purchaser
61–90 days                            → pre_churn
more than 90 days                     → churned
```

The analysis is descriptive. It does not predict which users will churn in the future. It classifies current purchaser status using observed purchase history and user-defined inactivity thresholds.

---

# 1. Identity scope

All calculations are performed at `user_id` level.

Only source rows with a populated `user_id` are included:

```text
user_id IS NOT NULL
```

Anonymous users who only have `user_pseudo_id` are excluded.

This means the output represents the identified-user population for which the GA4 implementation sends `user_id`.

Example:

```text
Total GA4 users: 1,200,000
Users with user_id: 280,000
```

The churn workflow operates on the 280,000 identified users, not on the full GA4 user population.

This is not an error, but the scope must be stated clearly when results are reported.

A recommended description is:

> The analysis is calculated for identified users with a populated GA4 `user_id` in the BigQuery export.

`user_id` can provide a more customer-oriented view than `user_pseudo_id` when the same identifier is consistently sent across devices and sessions. However, incomplete `user_id` implementation can introduce selection bias if only specific user groups are identified.

---

# 2. Analysis date

The analysis date is derived from the latest source event date:

```text
analysis_date = MAX(event_date)
```

Example:

```text
Current calendar date: September 21
Latest BigQuery event_date: September 18
```

All inactivity calculations are evaluated as of September 18.

Before results are shared, `analysis_date` should be checked to confirm that the export is fresh.

---

# 3. Setup

```python
analysis = ChurnAnalysis(
    project_id="your-project",
    dataset_id="analytics_123456789",
    table_id="events_*",
    output_dataset_id="ga4_churn",
)
```

| Input | Description |
|---|---|
| `project_id` | Google Cloud project containing the GA4 export |
| `dataset_id` | GA4 BigQuery export dataset |
| `table_id` | Source table or wildcard, usually `events_*` |
| `output_dataset_id` | Dataset where analysis tables are written |

Pre-churn and churn thresholds are intentionally not provided at initialization. Purchase-gap behavior is reviewed first, then candidate thresholds are selected.

---

# 4. Recommended workflow

```python
analysis.dry_run()
analysis.create_base_table()
analysis.purchase_day_distribution()
analysis.churn_analysis(60, 90)
```

The sequence answers the following questions:

```text
1. How much data will BigQuery scan?
2. What does the identified purchaser base look like?
3. How many days normally pass between repeat purchases?
4. Which inactivity windows are reasonable candidates for pre-churn and churn?
5. How do user counts and historical revenue differ across the resulting states?
```

---

# 5. `dry_run()`

`dry_run()` estimates BigQuery scan volume before the main analysis tables are created.

Example:

```text
Estimated scan: 86.4 GB
```

This is a query-cost control, not a business metric.

Unexpectedly high scan volume should trigger checks for:

- wrong dataset,
- unnecessarily long history,
- incorrect wildcard usage,
- production-scale data being used for a small validation run.

---

# 6. `create_base_table()`

```python
analysis.create_base_table()
```

Output grain:

```text
1 row = 1 user_id
```

Output table:

```text
<output_dataset>.churn_base
```

Core fields include:

| Field | Meaning |
|---|---|
| `user_id` | Identified-user key used in the analysis |
| `first_event_date` | First observed event date |
| `last_event_date` | Last observed event date |
| `event_count` | Total event count |
| `session_count` | Distinct `ga_session_id` count |
| `purchase_count` | Number of `purchase` events |
| `revenue` | Historical purchase revenue observed in GA4 |
| `first_purchase_date` | First observed purchase date |
| `last_purchase_date` | Last observed purchase date |
| `analysis_date` | Latest source event date |
| `days_since_last_purchase` | Days from last purchase to analysis date |

## Users

Distinct `user_id` count included in the workflow.

## Purchasers

Users with at least one observed purchase.

## One-time purchasers

Users with exactly one observed purchase.

## Repeat purchasers

Users with more than one observed purchase.

## Purchaser rate

```text
Purchasers / Users
```

This is a user-level purchaser share, not a session conversion rate.

## Repeat rate

```text
Repeat purchasers / Purchasers
```

This summarizes how much of the purchaser base has demonstrated repeat buying behavior.

## Revenue

Historical GA4 purchase revenue. Differences versus finance or ERP systems may result from duplicate purchase events, missing events, refunds, currency handling, consent, or tagging issues.

---

# 7. `purchase_day_distribution()` — core threshold-preparation step

```python
analysis.purchase_day_distribution()
```

The purpose of this step is not to classify churn directly. It describes the timing of repeat-purchase behavior.

The main analytical question is:

> After one purchase, how many days normally pass before the same `user_id` purchases again?

Distinct purchase dates are ordered for each user and consecutive date gaps are calculated.

Example:

```text
January 5
January 20
February 18
```

produces:

```text
15 days
29 days
```

Multiple purchases on the same calendar day are treated as one purchase date for interval analysis.

---

# 8. Gap observations

`gap_observations` is the total number of consecutive purchase intervals.

A user with 2 distinct purchase dates contributes 1 gap.

A user with 5 distinct purchase dates contributes 4 gaps.

Therefore:

```text
Gap observations != Repeat purchasers
```

is expected.

All distribution percentages should therefore be interpreted as percentages of **purchase intervals**, not percentages of users.

---

# 9. Mean and median

The mean is the arithmetic average of all purchase intervals.

The median is the midpoint of the ordered interval distribution.

Example:

```text
Mean   = 58 days
Median = 31 days
```

A large difference can indicate a long right tail where a smaller number of long intervals pull the mean upward.

The mean should not be used alone as a churn threshold.

If:

```text
Mean   = 34 days
Median = 31 days
```

the center of the distribution is more balanced.

---

# 10. P25 / P75 / P90 / P95

Example:

```text
P25 = 17 days
P50 = 29 days
P75 = 48 days
P90 = 82 days
P95 = 121 days
```

Interpretation:

```text
About 25% of intervals are 17 days or shorter.
About 50% are 29 days or shorter.
About 75% are 48 days or shorter.
About 90% are 82 days or shorter.
About 95% are 121 days or shorter.
```

P90 and P95 are especially useful as upper-tail reference points when calibrating churn thresholds.

If P90 is 82 days, only around 10% of observed purchase intervals are longer than 82 days.

This makes the 80–90 day range a reasonable area to investigate, but not an automatic threshold.

---

# 11. IQR

```text
IQR = P75 - P25
```

IQR describes the width of the middle 50% of purchase intervals.

Example A:

```text
P25 = 20
P75 = 50
IQR = 30 days
```

Repeat timing is relatively concentrated.

Example B:

```text
P25 = 10
P75 = 120
IQR = 110 days
```

The purchaser population is much more heterogeneous.

A wide IQR is a warning that one global threshold may not fit all customer groups equally well.

---

# 12. Standard deviation and coefficient of variation

Coefficient of variation:

```text
CV = standard deviation / mean
```

Directional interpretation:

```text
CV < 0.5    → relatively regular repeat timing
0.5–1.0     → moderate variability
CV >= 1.0   → highly variable repeat timing
```

These are practical diagnostics, not hard statistical rules.

Example:

```text
Median = 28
P90 = 75
CV = 0.42
```

suggests a relatively regular repeat-purchase cycle.

By contrast:

```text
Median = 27
P90 = 190
CV = 1.45
```

indicates highly varied customer timing despite a similar median.

---

# 13. Purchase-gap histogram

The histogram groups intervals into:

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

### Example A — clear short repeat cycle

If most observations sit in 15–30 and 31–60 days and very few are above 90 days, candidate pre-churn and churn ranges may be relatively short.

### Example B — two peaks

If the distribution has one peak around 15–30 days and another around 91–180 days, multiple customer or product cycles may exist in the same dataset.

Possible causes include:

- consumable versus durable products,
- low-value versus high-value categories,
- different customer groups,
- seasonal repeat behavior.

In this case, a single global threshold should be treated cautiously.

### Example C — long tail

Material volume in 181–365 or 366+ days may indicate:

- seasonality,
- long replacement cycles,
- large product-category differences,
- very long observation windows,
- genuinely infrequent repeat purchasing.

The highest histogram bar should not be used mechanically as a churn threshold.

---

# 14. Cumulative repeat-purchase coverage

This chart answers:

> What share of observed purchase intervals are at or below X days?

Example:

```text
30 days  → 42%
45 days  → 61%
60 days  → 74%
90 days  → 89%
120 days → 94%
180 days → 98%
```

If pre-churn is set at 60 days and churn at 90 days:

- about 74% of observed intervals occur before the pre-churn boundary,
- about 89% occur before the churn boundary.

Coverage is interval-level, not user-level.

---

# 15. How to select pre-churn and churn thresholds

Threshold selection should combine multiple signals rather than relying on one statistic.

## Step 1 — confirm adequate observation history

If a 120-day churn threshold is being considered, the available data history should be materially longer than 120 days and ideally cover several purchase cycles.

## Step 2 — use median and P75 to understand normal behavior

Example:

```text
Median = 28 days
P75 = 50 days
```

A large share of repeat behavior is still occurring within 50 days. A 30-day pre-churn boundary may be too aggressive.

## Step 3 — use P90 and P95 to inspect the upper tail

Example:

```text
P90 = 84 days
P95 = 126 days
```

A 90-day churn boundary would sit near the upper edge of normal repeat behavior. A 120-day boundary would create a more conservative churn definition.

## Step 4 — inspect cumulative coverage

Example:

```text
60 days coverage  = 76%
75 days coverage  = 84%
90 days coverage  = 90%
120 days coverage = 95%
```

Candidate scenarios may include:

```text
Pre-churn = 60 or 75 days
Churn = 90 or 120 days
```

## Step 5 — compare with the real purchase cycle

The same percentile structure can mean different things in different businesses.

### Fast-repeat category

```text
Median = 24
P75 = 35
P90 = 52
```

Possible candidate windows:

```text
Pre-churn = 35–45 days
Churn = 55–70 days
```

### Lower-frequency fashion / discretionary category

```text
Median = 52
P75 = 95
P90 = 160
```

A 60-day churn rule would likely be too aggressive.

### Seasonal or annual purchase category

Standard day-based churn may be insufficient. Prior-year seasonality or renewal periods may be more appropriate reference points.

---

# 16. Pre-churn threshold logic

Pre-churn is intended to identify purchasers who have not yet crossed the churn boundary but are beginning to move outside normal return behavior.

Example:

```text
Median = 30
P75 = 52
P90 = 88
P95 = 130
```

A candidate setup may be:

```text
Pre-churn threshold = 60 days
Churn threshold = 90 days
```

This creates:

```text
0–60 days   → normal / active area
61–90 days  → intervention area
90+ days    → churned area
```

The goal is to leave enough time between pre-churn and churn for CRM or marketing action.

---

# 17. Churn threshold logic

The churn boundary should represent a point sufficiently beyond normal repeat-purchase behavior.

Review together:

- P90,
- P95,
- cumulative coverage,
- histogram tail,
- replenishment or replacement cycle,
- seasonality,
- campaign cadence,
- customer segments,
- business use case.

Example:

```text
P75 = 50
P90 = 85
P95 = 125
90-day coverage = 91%
```

A 90-day churn rule may be a reasonable starting point, unless business knowledge indicates that 3–4 month repeat cycles are normal.

---

# 18. Three threshold-calibration examples

## Scenario 1 — regular repeat behavior

```text
Median = 25
P75 = 40
P90 = 62
P95 = 80
CV = 0.45
```

Candidate range:

```text
Pre-churn = 45–50
Churn = 70–80
```

## Scenario 2 — moderate variability

```text
Median = 32
P75 = 60
P90 = 95
P95 = 145
CV = 0.85
```

Candidate range:

```text
Pre-churn = 60–75
Churn = 100–120
```

Sensitivity analysis becomes especially important.

## Scenario 3 — highly heterogeneous behavior

```text
Median = 30
P75 = 95
P90 = 220
P95 = 340
CV = 1.60
```

One global threshold is risky. Consider segment-specific analysis by:

- product category,
- customer type,
- purchase frequency,
- historical value,
- acquisition source,
- geography or campaign group.

---

# 19. `churn_analysis(pre_churn_threshold, churn_threshold)`

Example:

```python
analysis.churn_analysis(60, 90)
```

Rules:

```text
purchase_count = 0
→ never_purchased

purchase_count > 0 and days_since_last_purchase <= 60
→ active_purchaser

purchase_count > 0 and 60 < days_since_last_purchase <= 90
→ pre_churn

purchase_count > 0 and days_since_last_purchase > 90
→ churned
```

The pre-churn threshold must be lower than the churn threshold.

---

# 20. Pre-churn rate and churn rate

Both rates use purchasers as the denominator.

```text
Pre-churn rate = pre_churn users / all purchasers
Churn rate = churned users / all purchasers
```

Example:

```text
Purchasers = 100,000
Active = 55,000
Pre-churn = 18,000
Churned = 27,000
```

Results:

```text
Pre-churn rate = 18%
Churn rate = 27%
```

Never-purchased users are excluded.

---

# 21. Active / pre-churn / churned distribution

Example A:

```text
Active    = 68%
Pre-churn = 8%
Churned   = 24%
```

The intervention pool is relatively small. If churn is already high, the pre-churn window may be too narrow or too late for operational action.

Example B:

```text
Active    = 45%
Pre-churn = 30%
Churned   = 25%
```

A large proportion of purchasers are approaching churn and may become a priority CRM audience.

Example C:

```text
Active    = 80%
Pre-churn = 15%
Churned   = 5%
```

This may indicate strong repeat behavior, but the churn threshold should also be checked for being too lenient.

---

# 22. One-time versus repeat purchasers

Churn among one-time purchasers usually represents failure to reach the second purchase.

Churn among repeat purchasers represents lapse after prior demonstrated repeat behavior.

Example:

```text
Churned users = 30,000
Churned one-time = 22,000
Churned repeat = 8,000
```

If most churned users are one-time purchasers, improving second-purchase behavior may be a more important business problem than reactivating established repeat customers.

---

# 23. Historical revenue shares

## Pre-churn revenue share

Historical revenue generated by pre-churn users divided by historical revenue generated by all purchasers.

## Churned revenue share

Historical revenue generated by churned users divided by historical revenue generated by all purchasers.

Example:

```text
Pre-churn rate = 15%
Pre-churn historical revenue share = 28%
```

The pre-churn group may be disproportionately valuable.

Example:

```text
Churn rate = 30%
Churned historical revenue share = 12%
```

The churn population may be relatively low-value despite being large in user count.

These are historical contribution metrics. They are not lost revenue or future revenue forecasts.

---

# 24. Status diagnostics

Active, pre-churn and churned users are compared on:

- user count,
- average purchases,
- median purchases,
- average revenue,
- median revenue,
- average inactivity days,
- median inactivity days.

Example:

```text
                 Avg purchases   Avg revenue
Active                4.8            1,250
Pre-churn             3.9            1,480
Churned               1.7              410
```

A high pre-churn average revenue can indicate that valuable customers are moving into the risk window.

Mean and median should be interpreted together because revenue is often highly skewed.

---

# 25. Purchase-frequency comparison

Purchasers are grouped into:

```text
1 purchase
2 purchases
3–5 purchases
6+ purchases
```

Pre-churn and churn rates are calculated separately for each band.

Example:

```text
                 Pre-churn   Churn
1 purchase          18%       44%
2 purchases         16%       29%
3–5 purchases       12%       17%
6+ purchases         8%        7%
```

This may show that deeper purchase history is associated with lower churn, but it does not prove causality.

Useful questions include:

- Is churn concentrated among one-time purchasers?
- Is the second purchase a critical retention milestone?
- Are highly repeat purchasers entering pre-churn at a meaningful rate?
- Should high-value repeat purchasers receive separate reactivation treatment?

---

# 26. Churn threshold sensitivity

The toolkit recalculates churn using nearby churn boundaries.

Example:

```text
60 days  → 39%
75 days  → 33%
90 days  → 28%
105 days → 25%
120 days → 22%
150 days → 18%
```

This answers:

> How dependent is the reported churn rate on the selected cutoff?

### Stable case

```text
75 days  → 29%
90 days  → 28%
105 days → 27%
```

### Sensitive case

```text
75 days  → 41%
90 days  → 28%
105 days → 18%
```

In a highly sensitive case, the churn rate should be reported together with the threshold range rather than as a single absolute number.

---

# 27. Pre-churn and churn gap coverage

The output includes:

```text
pre_churn_gap_coverage
churn_gap_coverage
```

Example:

```text
Pre-churn threshold = 60
Pre-churn gap coverage = 74%

Churn threshold = 90
Churn gap coverage = 90%
```

This indicates that 74% of observed purchase intervals are at or below 60 days and 90% are at or below 90 days.

This helps validate whether the selected pre-churn and churn windows are consistent with observed repeat-purchase behavior.

---

# 28. Recommended decision process

```text
1. Validate user_id coverage and purchase tracking
2. Confirm sufficient observation history
3. Review median and P75
4. Review P90 and P95
5. Inspect histogram shape
6. Inspect cumulative coverage
7. Define candidate pre-churn and churn boundaries
8. Compare with the business purchase cycle
9. Review churn sensitivity
10. Compare one-time and repeat purchaser outcomes
11. Recalibrate periodically as behavior changes
```

Thresholds should not be treated as permanent constants. Pricing, promotion cadence, product mix, seasonality and customer behavior can all change repeat-purchase timing.

---

# 29. HTML dashboard

`churn_analysis()` creates:

```text
ga4_churn_dashboard.html
```

The dashboard summarizes:

- selected thresholds,
- purchaser volume,
- active / pre-churn / churned volumes,
- pre-churn and churn rates,
- status-level purchase and revenue comparisons.

The dashboard is a presentation layer. It does not create a separate metric definition from the notebook or BigQuery output tables.

---

# 30. Measurement caveats

Results can be misleading when:

- `user_id` coverage is low or selective,
- purchase events are duplicated or missing,
- revenue tracking is unreliable,
- the observation window is shorter than the selected threshold,
- strong seasonality exists,
- very different product cycles are mixed together,
- active users are interpreted as guaranteed future repeat purchasers,
- pre-churn users are interpreted as guaranteed future churners.

`active_purchaser` only means the user has not crossed the pre-churn boundary.

`pre_churn` only means the user is currently inside the defined inactivity-risk window.

---

# 31. Reporting example

Weak reporting:

```text
Churn rate is 27%.
```

More complete reporting:

```text
The analysis covers 82,000 purchasers with a populated GA4 user_id.

Median repeat-purchase gap is 31 days and P90 is 86 days.
A 60-day pre-churn boundary and a 90-day churn boundary are used.

Under this definition:
- 56% are active,
- 17% are pre-churn,
- 27% are churned.

Pre-churn users represent 24% of historical purchaser revenue.
Churn is 46% for one-time purchasers and 9% for users with 6+ purchases.

If the churn boundary is reduced to 75 days, churn rises to 34%.
If it is increased to 105 days, churn falls to 22%.
```

This format makes both the result and the assumptions behind it visible.
