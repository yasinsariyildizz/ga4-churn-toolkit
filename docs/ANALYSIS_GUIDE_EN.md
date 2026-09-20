# GA4 Churn Toolkit — Analysis & Interpretation Guide (EN)

This document explains how the **basic purchase-based churn** analysis in `ga4-churn-toolkit` works, what each metric and chart means, and how analysts should interpret the outputs.

> This release is intentionally simple. Its purpose is to provide a transparent and reusable churn framework on top of GA4 BigQuery export data. It does **not predict future churn**. It classifies current historical purchasers according to a user-selected inactivity threshold.

---

## 1. Core analytical logic

The analysis is based on purchase behavior.

A user is considered a **purchaser** if they generated at least one `purchase` event. The tool calculates the number of days between the user's last purchase and the analysis date:

```text
days_since_last_purchase = analysis_date - last_purchase_date
```

The churn threshold is provided only when churn analysis is executed:

```python
analysis.churn_analysis(90)
```

In this example, the threshold is 90 days.

Classification logic:

```text
purchase_count = 0
→ never_purchased

purchase_count > 0 and days_since_last_purchase <= threshold
→ active_purchaser

purchase_count > 0 and days_since_last_purchase > threshold
→ churned
```

### What is the analysis date?

The user does not enter a separate analysis date. The toolkit uses the most recent `event_date` found in the source data:

```text
analysis_date = MAX(event_date)
```

Therefore, churn results depend on how fresh the dataset is. If the source data is stale, churn is evaluated relative to that stale date.

---

## 2. User inputs

```python
analysis = ChurnAnalysis(
    project_id="your-project",
    dataset_id="analytics_123456789",
    table_id="events_*",
    output_dataset_id="ga4_churn",
)
```

| Input | Meaning |
|---|---|
| `project_id` | GCP project that contains the GA4 export |
| `dataset_id` | GA4 BigQuery export dataset |
| `table_id` | Source table or wildcard, e.g. `events_*` |
| `output_dataset_id` | Dataset where analysis tables will be created |

The churn threshold is deliberately excluded from the constructor and is entered only in `churn_analysis()`.

---

# 3. Recommended workflow

```python
analysis.dry_run()
analysis.create_base_table()
analysis.purchase_day_distribution()
analysis.churn_analysis(90)
```

This order matters because each step helps interpret the next one.

---

# 4. `dry_run()` — Cost and scan validation

```python
analysis.dry_run()
```

This function estimates the amount of data BigQuery would scan before creating any output table.

Main output:

```text
Estimated scan: X GB
```

## How to interpret it

This is not an analytical result. It only describes the approximate data volume that BigQuery will read.

If:

```python
table_id="events_*"
```

is used, all matching export tables may be scanned. On large GA4 datasets this can create substantial query cost.

### Pay attention when

- estimated GB/TB is much larger than expected,
- the wrong dataset or wildcard may have been selected,
- a full-history scan is unnecessary for testing.

`dry_run()` is a **cost and safety control**, not a business-analysis step.

---

# 5. `create_base_table()` — User-level analytical base

```python
analysis.create_base_table()
```

The grain of this table is:

```text
1 row = 1 user_pseudo_id
```

Main output table:

```text
<output_dataset>.churn_base
```

## Core columns

| Column | Meaning |
|---|---|
| `user_pseudo_id` | GA4 browser/device-level user identifier |
| `first_event_date` | First event date observed in the dataset |
| `last_event_date` | Last event date observed in the dataset |
| `event_count` | Total event count for the user |
| `session_count` | Distinct `ga_session_id` count |
| `purchase_count` | Number of `purchase` events |
| `revenue` | Sum of `ecommerce.purchase_revenue` on purchase events |
| `first_purchase_date` | First observed purchase date |
| `last_purchase_date` | Last observed purchase date |
| `analysis_date` | Maximum event date in the source data |
| `days_since_last_purchase` | Days from last purchase to analysis date |

## Notebook KPIs

### Users

Distinct `user_pseudo_id` count in the source data.

### Purchasers

Users with at least one purchase event.

### One-time purchasers

Users with exactly one purchase event.

This group is especially important because one-time buyers often behave very differently from repeat purchasers.

### Repeat purchasers

Users with more than one purchase event.

### Purchaser rate

```text
purchasers / all users
```

This is **not** a churn rate. It is simply the share of observed users who became purchasers.

### Repeat rate

```text
repeat purchasers / purchasers
```

This describes how much of the purchaser base has demonstrated repeat buying behavior.

### Revenue

Historical revenue observed on purchase events in the dataset.

> This is not necessarily accounting revenue. GA4 tracking quality, currency implementation, and duplicate purchase events can affect the number.

---

# 6. `purchase_day_distribution()` — Repurchase timing analysis

```python
analysis.purchase_day_distribution()
```

This step is designed to help understand the customer's natural purchase rhythm before selecting a churn threshold.

## Calculation logic

Distinct purchase dates are sorted for each user.

Example:

```text
January 10
January 25
February 20
```

Generated gaps:

```text
15 days
26 days
```

If a user makes multiple purchases on the same day, that day is counted only once for interval analysis. This prevents same-day purchases from creating misleading zero-day repeat intervals.

> Only users with at least two distinct purchase dates contribute to the purchase-gap distribution. One-time purchasers are not included in this distribution.

---

## 6.1 Gap Observations

Total number of consecutive purchase intervals observed.

If one user purchases on five distinct dates, they contribute four gap observations.

Therefore:

```text
gap observations != repeat purchaser count
```

is expected.

---

## 6.2 Mean Gap

The arithmetic mean of observed purchase intervals.

It is sensitive to very long gaps.

Example:

```text
10, 12, 14, 15, 180
```

The 180-day interval materially increases the mean.

For that reason, the mean should not be used alone to select a churn threshold.

---

## 6.3 Median / P50

The midpoint of the purchase-gap distribution.

If:

```text
Median = 30 days
```

then approximately half of observed intervals are 30 days or shorter and half are longer.

The median is less sensitive to extreme values than the mean.

---

## 6.4 P25 and P75

P25 is the value at or below which about 25% of intervals fall. P75 is the equivalent point for about 75% of intervals.

Example:

```text
P25 = 18
P75 = 55
```

The middle 50% of observed repeat-purchase intervals are approximately between 18 and 55 days.

---

## 6.5 IQR

```text
IQR = P75 - P25
```

IQR describes the spread of the middle 50% of the distribution.

Low IQR → repeat-purchase timing is relatively concentrated.

High IQR → customer behavior is heterogeneous and one churn threshold may not fit all users equally well.

---

## 6.6 P90 and P95

These are especially useful reference points when evaluating churn thresholds.

Example:

```text
P90 = 82 days
```

This means that approximately 90% of observed repeat-purchase intervals are 82 days or shorter.

If a 90-day churn threshold is selected, the cutoff may sit near the upper tail of historical repeat behavior.

However:

> P90 is **not automatically the correct churn threshold**.

It is a behavioral reference point only. Seasonality, product renewal cycles, subscriptions, category-specific purchase patterns, and the observation window can all change how it should be interpreted.

---

## 6.7 Standard Deviation

Measures variability around the mean purchase interval.

A high standard deviation suggests that purchase timing differs substantially across observed intervals.

---

## 6.8 Coefficient of Variation (CV)

```text
CV = standard deviation / mean
```

It provides a relative measure of dispersion.

A rough interpretation aid:

```text
CV < 0.5   → relatively concentrated timing
0.5–1.0    → moderate variability
CV >= 1.0  → high variability
```

These are not universal statistical rules; they are only practical interpretation heuristics.

When CV is high, a single universal churn threshold should be used more cautiously.

---

# 7. How to read the Purchase-Gap Histogram

The histogram groups purchase intervals into buckets:

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

Each bar shows how many observed purchase intervals fall into that range.

## Example interpretation

If the largest bar is:

```text
15–30 days
```

then a large share of repeat purchasing occurs in that interval range.

If the 181+ buckets are also substantial, possible explanations include:

- long purchase cycles,
- heterogeneous customer segments,
- seasonality,
- long-tailed behavior caused by a long observation window.

### What should not be concluded from the histogram?

Do not automatically conclude:

> “The largest bar is 31–60 days, therefore the churn threshold must be 60 days.”

The histogram describes the shape of historical behavior. It does not make the business decision for you.

---

# 8. Cumulative Repeat-Purchase Coverage chart

This chart answers:

> What percentage of observed repeat-purchase intervals occur within X days?

Example:

```text
30 days → 48%
60 days → 72%
90 days → 89%
180 days → 97%
```

Interpretation:

- 48% of observed intervals happen within 30 days,
- 72% within 60 days,
- 89% within 90 days.

This chart is often more directly useful for threshold discussions than the histogram.

If a 90-day threshold has 89% coverage, then the selected threshold is at least as long as approximately 89% of historical observed purchase intervals.

This does **not** mean “89% of users return within 90 days.” The metric is interval-based, not user-based.

---

# 9. Automatic Purchase Behavior Insights

The toolkit generates deterministic summary statements from the observed statistics.

Examples:

```text
The median repeat-purchase interval is 31 days.
The middle 50% of repeat-purchase intervals fall between 18 and 55 days.
The distribution is right-skewed.
Repurchase timing is highly variable.
```

These statements are not AI predictions. They are rule-based summaries designed to help analysts interpret the numbers quickly.

---

# 10. `churn_analysis(threshold)`

Example:

```python
analysis.churn_analysis(90)
```

This step classifies purchasers using the selected inactivity threshold.

## Churn-rate formula

```text
churn rate = churned purchasers / all purchasers
```

Never-purchased users are excluded from the denominator.

Example:

```text
Total users        1,000,000
Purchasers           200,000
Churned               60,000

Churn Rate = 60,000 / 200,000 = 30%
```

Incorrect denominator:

```text
60,000 / 1,000,000
```

because users who never purchased were never part of the purchaser-risk population.

---

# 11. Churn Analysis KPIs

## Purchasers

All users with at least one purchase.

## Active Purchasers

Purchasers whose last purchase falls within the selected threshold.

## Churned Users

Purchasers whose inactivity exceeds the selected threshold.

## One-Time Purchasers

Purchasers with exactly one purchase event.

This segment often has a very different churn profile from repeat buyers.

## Churned One-Time Buyers

Users with one purchase whose inactivity exceeds the threshold.

## Churned Repeat Buyers

Users with multiple purchases whose inactivity exceeds the threshold.

## Churned Revenue Share

```text
historical revenue of churned users
-----------------------------------
historical revenue of all purchasers
```

This metric does **not** mean:

> “This is the revenue we lost.”

It shows the historical revenue share generated by users who are currently classified as churned. It is not a forecast of future lost revenue.

---

# 12. Status Diagnostics table

This table compares:

- active purchasers,
- churned purchasers,
- never-purchased users.

Columns include:

- Users
- Avg purchases
- Median purchases
- Avg revenue
- Median revenue
- Avg inactive days

## Why show both mean and median?

Purchase count and revenue distributions are often right-skewed.

Example:

```text
Active avg revenue    = 1,200
Active median revenue = 320
```

A small number of high-value users may be pulling the average upward.

Therefore, mean and median should be interpreted together.

---

# 13. Purchaser Status chart

Compares the absolute volume of active versus churned purchasers.

Example:

```text
Active   120,000
Churned   80,000
```

The bars show volume, not the business severity by themselves. Always interpret them together with churn rate and purchaser-base size.

---

# 14. Churn Rate by Purchase Frequency chart

Purchasers are grouped into:

```text
1 purchase
2 purchases
3–5 purchases
6+ purchases
```

Churn rate is calculated separately for each group.

## Why this matters

One-time buyers and highly repeat purchasers often have different retention patterns.

Example:

```text
1 purchase   → 52% churn
2 purchases  → 31% churn
3–5          → 18% churn
6+           → 9% churn
```

This may suggest that deeper historical purchase engagement is associated with lower churn.

However, this is correlation, not causality. You cannot conclude from this analysis alone that “making users purchase more will cause churn to decrease.”

---

# 15. Threshold Sensitivity chart

This is one of the most important controls in the toolkit.

Suppose the selected threshold is:

```text
90 days
```

The toolkit recalculates churn at nearby cutoffs.

Example:

```text
60 days  → 36%
75 days  → 31%
90 days  → 27%
105 days → 24%
120 days → 21%
150 days → 17%
```

## How to interpret it

As the threshold becomes larger, it becomes harder for a user to qualify as churned, so churn rate will generally decline.

The chart answers:

> How sensitive is my churn result to the cutoff assumption?

If:

```text
75 days = 30%
90 days = 29%
105 days = 28%
```

then the result is relatively stable.

If:

```text
75 days = 42%
90 days = 29%
105 days = 18%
```

then small threshold changes materially alter the result.

In that case, reporting a single churn rate as an absolute truth would be misleading.

---

# 16. Threshold Context / Gap Coverage

The churn output also shows where the selected threshold sits relative to historical purchase-gap behavior.

Example:

```text
Threshold = 90 days
Gap coverage = 91%
P90 = 86 days
```

This means the selected threshold is at least as long as about 91% of observed repeat-purchase intervals.

It is a behavioral sanity check, not a proof that 90 days is optimal.

---

# 17. How should a threshold be selected?

This basic toolkit deliberately does not choose the threshold automatically because churn definition depends on business context.

Review together:

1. Median purchase gap
2. P75 / P90 / P95
3. Purchase-gap histogram
4. Cumulative coverage
5. Threshold sensitivity
6. Business purchase cycle
7. Seasonality
8. Product category
9. Length of the historical observation window

### Simple example

Suppose:

```text
Median = 28
P75 = 48
P90 = 83
P95 = 125
```

Reasonable candidate tests might include:

```text
60
90
120
```

Then compare sensitivity and business plausibility.

> The toolkit does not automatically treat P90 as the churn threshold, and it should not. P90 is only one useful reference point.

---

# 18. HTML Dashboard

`churn_analysis()` creates:

```text
ga4_churn_dashboard.html
```

The dashboard includes:

- Selected threshold
- Purchasers
- Active purchasers
- Churned users
- Churn rate
- Gap coverage
- Churned historical revenue share
- Analytical insights
- Status diagnostics
- Churn by purchase frequency
- Threshold sensitivity

The dashboard is a presentation layer only. Its definitions are identical to the notebook outputs.

---

# 19. Important methodological limitations

## 19.1 `user_pseudo_id` is not necessarily a real person

GA4 `user_pseudo_id` is generally browser/device-instance oriented.

The same person can generate multiple identifiers across:

- multiple devices,
- multiple browsers,
- cookie resets.

Therefore, results should be interpreted at the implemented identity level, not automatically as “unique customers.”

---

## 19.2 Tracking errors directly affect churn metrics

Duplicate purchase events, missing purchase events, or incorrect revenue implementation affect:

- purchase count,
- revenue,
- purchase-gap calculations,
- churn classification.

---

## 19.3 Dataset start is not necessarily customer start

A user appearing on the first day of the dataset may have existed long before the export window began.

The toolkit only knows what is visible in the selected data.

---

## 19.4 Dataset freshness matters

Because:

```text
analysis_date = MAX(event_date)
```

an outdated source dataset produces an outdated churn snapshot.

---

## 19.5 Right censoring / observation-window effects

Users who purchased recently have not yet had enough time to demonstrate churn.

Example:

If threshold = 90 days but a user purchased 20 days ago, they are classified as active. The toolkit cannot know whether they will churn later.

---

## 19.6 Classification is not prediction

The toolkit does not answer:

```text
Who will churn next?
```

It answers:

```text
Which historical purchasers are currently classified as churned under the selected inactivity threshold?
```

---

## 19.7 No causal inference

If users with 6+ purchases have lower churn, you cannot conclude:

```text
Having six purchases causes lower churn.
```

The relationship is descriptive.

---

## 19.8 Seasonality is not modeled

The basic release does not explicitly control for:

- monthly seasonality,
- annual purchase cycles,
- promotional periods,
- product replacement cycles.

Industries with long or seasonal purchase cycles require additional business interpretation.

---

# 20. How should results be presented?

Instead of reporting only one churn rate, a more transparent summary is:

```text
Selected threshold: 90 days
Churn rate: 27%
Observed purchase-gap P90: 84 days
Gap coverage at 90 days: 91%
75-day sensitivity: 31%
105-day sensitivity: 24%
One-time purchaser churn: 43%
6+ purchase churn: 10%
```

This makes the threshold assumption visible instead of hiding it behind a single KPI.

---

# 21. Recommended analyst checklist

Before sharing results, verify:

- [ ] Correct GCP project selected
- [ ] Correct GA4 dataset selected
- [ ] Correct `table_id` / wildcard selected
- [ ] Latest event date is reasonably current
- [ ] Purchase tracking is reliable
- [ ] Revenue implementation is reliable
- [ ] Purchase-gap distribution has sufficient observations
- [ ] Median / P75 / P90 / P95 reviewed
- [ ] Threshold sensitivity reviewed
- [ ] One-time vs repeat purchaser behavior reviewed
- [ ] Churned revenue share is not presented as future lost revenue
- [ ] `user_pseudo_id` identity limitation is disclosed

---

# 22. Glossary

**Grain**  
What one row represents. For `churn_base`, grain = 1 `user_pseudo_id`.

**Purchaser**  
A user with at least one purchase event.

**Repeat purchaser**  
A user with more than one purchase.

**Purchase gap**  
Days between two consecutive distinct purchase dates for one user.

**Threshold**  
Maximum inactivity period allowed before a purchaser is classified as churned.

**Churned purchaser**  
A purchaser whose inactivity exceeds the selected threshold.

**Percentile**  
A value at or below which a given share of observations fall.

**P90**  
A value at or below which approximately 90% of observations fall.

**IQR**  
P75 − P25. Spread of the middle 50% of the distribution.

**Sensitivity analysis**  
Testing how much the churn result changes when the threshold assumption changes.

---

## Final interpretation framework

The intended analytical flow is:

```text
Understand historical purchase behavior
        ↓
Inspect the purchase-gap distribution
        ↓
Choose a business-plausible threshold
        ↓
Run churn classification
        ↓
Test threshold sensitivity
        ↓
Interpret frequency and revenue diagnostics
```

A churn rate is not the whole answer. The real analytical value comes from understanding **which behavioral distribution and which threshold assumption produced that churn rate**.
