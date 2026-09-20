from __future__ import annotations

from importlib import resources
from pathlib import Path
import html
import re

from google.cloud import bigquery

_PROJECT_RE = re.compile(r"^[a-z][a-z0-9\-:.]{4,62}[a-z0-9]$")
_ID_RE = re.compile(r"^[A-Za-z0-9_]+$")
_TABLE_RE = re.compile(r"^[A-Za-z0-9_*]+$")


class ChurnAnalysis:
    """Basic purchase-based churn analysis for GA4 BigQuery exports."""

    def __init__(self, project_id: str, dataset_id: str, table_id: str, output_dataset_id: str):
        self.project_id = project_id.strip()
        self.dataset_id = dataset_id.strip()
        self.table_id = table_id.strip()
        self.output_dataset_id = output_dataset_id.strip()
        self.last_churn_threshold: int | None = None
        self._validate()
        self.client = bigquery.Client(project=self.project_id)

    def _validate(self) -> None:
        if not _PROJECT_RE.match(self.project_id):
            raise ValueError("Invalid project_id")
        if not _ID_RE.match(self.dataset_id):
            raise ValueError("Invalid dataset_id")
        if not _TABLE_RE.match(self.table_id):
            raise ValueError("Invalid table_id")
        if not _ID_RE.match(self.output_dataset_id):
            raise ValueError("Invalid output_dataset_id")

    @staticmethod
    def _validate_threshold(churn_threshold: int) -> int:
        threshold = int(churn_threshold)
        if threshold < 1:
            raise ValueError("churn_threshold must be >= 1")
        return threshold

    @property
    def source(self) -> str:
        return f"{self.project_id}.{self.dataset_id}.{self.table_id}"

    @property
    def out(self) -> str:
        return f"{self.project_id}.{self.output_dataset_id}"

    def _ensure_output_dataset(self) -> None:
        source_ds = self.client.get_dataset(f"{self.project_id}.{self.dataset_id}")
        ds = bigquery.Dataset(self.out)
        ds.location = source_ds.location
        self.client.create_dataset(ds, exists_ok=True)

    def _sql(self, name: str) -> str:
        text = resources.files("ga4_churn").joinpath("sql").joinpath(name).read_text(encoding="utf-8")
        for k, v in {
            "{{PROJECT_ID}}": self.project_id,
            "{{DATASET_ID}}": self.dataset_id,
            "{{TABLE_ID}}": self.table_id,
            "{{OUTPUT_DATASET_ID}}": self.output_dataset_id,
        }.items():
            text = text.replace(k, v)
        return text

    def _run(self, sql_name: str, churn_threshold: int | None = None):
        self._ensure_output_dataset()
        params = []
        if churn_threshold is not None:
            params.append(bigquery.ScalarQueryParameter("churn_threshold", "INT64", self._validate_threshold(churn_threshold)))
        job = self.client.query(self._sql(sql_name), job_config=bigquery.QueryJobConfig(query_parameters=params))
        job.result()
        return job

    def _rows(self, sql: str) -> list[dict]:
        return [dict(r.items()) for r in self.client.query(sql).result()]

    def _one(self, sql: str) -> dict:
        rows = self._rows(sql)
        return rows[0] if rows else {}

    def dry_run(self) -> dict:
        queries = [
            ("Base table scan", f"SELECT * FROM `{self.source}`"),
            ("Purchase gap scan", f"SELECT user_pseudo_id,event_date FROM `{self.source}` WHERE event_name='purchase'"),
        ]
        details, total = [], 0
        for name, sql in queries:
            job = self.client.query(sql, job_config=bigquery.QueryJobConfig(dry_run=True, use_query_cache=False))
            processed = int(job.total_bytes_processed or 0)
            total += processed
            details.append({"name": name, "bytes": processed, "gb": round(processed / 1024**3, 3)})

        result = {"estimated_gb": round(total / 1024**3, 3), "details": details, "source": self.source}
        self._display_cards("Dry run", [("Estimated scan", f"{result['estimated_gb']:.3f} GB"), ("Source", self.source)], "No query has been executed yet.")
        self._display_table("Estimated scan by step", details, [("name", "Step"), ("gb", "Estimated GB")])
        return result

    def create_base_table(self) -> dict:
        job = self._run("01_base_table.sql")
        t = f"`{self.out}.churn_base`"
        result = self._one(f"""
            SELECT
              MAX(analysis_date) AS analysis_date,
              COUNT(*) AS users,
              COUNTIF(purchase_count > 0) AS purchasers,
              COUNTIF(purchase_count = 1) AS one_time_purchasers,
              COUNTIF(purchase_count > 1) AS repeat_purchasers,
              SUM(session_count) AS sessions,
              SUM(event_count) AS events,
              SUM(purchase_count) AS purchases,
              SUM(revenue) AS revenue,
              AVG(IF(purchase_count > 0, purchase_count, NULL)) AS avg_purchases_per_purchaser,
              AVG(IF(purchase_count > 0, revenue, NULL)) AS avg_revenue_per_purchaser,
              SAFE_DIVIDE(COUNTIF(purchase_count > 0), COUNT(*)) AS purchaser_rate,
              SAFE_DIVIDE(COUNTIF(purchase_count > 1), COUNTIF(purchase_count > 0)) AS repeat_rate
            FROM {t}
        """)
        result["job_id"] = job.job_id
        self._display_cards(
            "Create base table",
            [
                ("Users", self._fmt(result.get("users"))),
                ("Purchasers", self._fmt(result.get("purchasers"))),
                ("One-time purchasers", self._fmt(result.get("one_time_purchasers"))),
                ("Repeat purchasers", self._fmt(result.get("repeat_purchasers"))),
                ("Purchaser rate", self._pct(result.get("purchaser_rate"))),
                ("Repeat rate", self._pct(result.get("repeat_rate"))),
                ("Purchases", self._fmt(result.get("purchases"))),
                ("Revenue", self._fmt(result.get("revenue"), 2)),
            ],
            f"Analysis date: {result.get('analysis_date')} · Output: {self.out}.churn_base",
        )
        return result

    def purchase_day_distribution(self) -> dict:
        job = self._run("02_purchase_day_distribution.sql")
        t = f"`{self.out}.purchase_day_gaps`"

        stats = self._one(f"""
            WITH q AS (
              SELECT APPROX_QUANTILES(gap_days, 100) AS qt
              FROM {t}
            )
            SELECT
              COUNT(*) AS gap_observations,
              COUNT(DISTINCT user_pseudo_id) AS repeat_purchasers,
              MIN(gap_days) AS min_gap_days,
              AVG(gap_days) AS mean_gap_days,
              STDDEV_POP(gap_days) AS stddev_gap_days,
              MAX(gap_days) AS max_gap_days,
              ANY_VALUE(q.qt[OFFSET(10)]) AS p10,
              ANY_VALUE(q.qt[OFFSET(25)]) AS p25,
              ANY_VALUE(q.qt[OFFSET(50)]) AS median,
              ANY_VALUE(q.qt[OFFSET(75)]) AS p75,
              ANY_VALUE(q.qt[OFFSET(90)]) AS p90,
              ANY_VALUE(q.qt[OFFSET(95)]) AS p95,
              SAFE_DIVIDE(STDDEV_POP(gap_days), NULLIF(AVG(gap_days), 0)) AS coefficient_of_variation,
              SAFE_DIVIDE(COUNTIF(gap_days <= 30), COUNT(*)) AS share_within_30d,
              SAFE_DIVIDE(COUNTIF(gap_days <= 60), COUNT(*)) AS share_within_60d,
              SAFE_DIVIDE(COUNTIF(gap_days <= 90), COUNT(*)) AS share_within_90d
            FROM {t}
            CROSS JOIN q
        """)

        p25 = self._num(stats.get("p25"))
        p75 = self._num(stats.get("p75"))
        median = self._num(stats.get("median"))
        mean = self._num(stats.get("mean_gap_days"))
        stats["iqr"] = None if p25 is None or p75 is None else p75 - p25
        stats["mean_median_ratio"] = None if mean is None or median in (None, 0) else mean / median
        stats["avg_gaps_per_repeat_purchaser"] = (
            None if not stats.get("repeat_purchasers") else float(stats.get("gap_observations") or 0) / float(stats["repeat_purchasers"])
        )

        hist = self._rows(self._hist_sql(t))
        ecdf = self._rows(f"""
            WITH thresholds AS (
              SELECT threshold_days
              FROM UNNEST([7,14,30,45,60,90,120,180,365]) AS threshold_days
            )
            SELECT
              threshold_days,
              SAFE_DIVIDE(COUNTIF(g.gap_days <= threshold_days), COUNT(*)) AS cumulative_share
            FROM {t} g
            CROSS JOIN thresholds
            GROUP BY threshold_days
            ORDER BY threshold_days
        """)

        insights = self._purchase_gap_insights(stats)
        result = {"stats": stats, "histogram": hist, "cumulative_distribution": ecdf, "insights": insights, "job_id": job.job_id}

        self._display_cards(
            "Purchase day distribution",
            [
                ("Gap observations", self._fmt(stats.get("gap_observations"))),
                ("Repeat purchasers", self._fmt(stats.get("repeat_purchasers"))),
                ("Mean", f"{self._fmt(stats.get('mean_gap_days'), 1)} d"),
                ("Median", f"{self._fmt(stats.get('median'))} d"),
                ("P75", f"{self._fmt(stats.get('p75'))} d"),
                ("P90", f"{self._fmt(stats.get('p90'))} d"),
                ("P95", f"{self._fmt(stats.get('p95'))} d"),
                ("Std. dev.", f"{self._fmt(stats.get('stddev_gap_days'), 1)} d"),
                ("IQR", f"{self._fmt(stats.get('iqr'), 1)} d"),
                ("≤ 90 days", self._pct(stats.get("share_within_90d"))),
            ],
            "Distinct purchase dates are used. Same-day purchases do not create a zero-day repeat interval.",
        )
        self._display_table(
            "Distribution statistics",
            [{
                "min": stats.get("min_gap_days"), "p10": stats.get("p10"), "p25": stats.get("p25"),
                "median": stats.get("median"), "p75": stats.get("p75"), "p90": stats.get("p90"),
                "p95": stats.get("p95"), "max": stats.get("max_gap_days"),
            }],
            [("min", "Min"), ("p10", "P10"), ("p25", "P25"), ("median", "P50"),
             ("p75", "P75"), ("p90", "P90"), ("p95", "P95"), ("max", "Max")],
        )
        self._display_bars("Purchase-gap histogram", hist, "bucket", "gaps")
        self._display_rate_bars("Cumulative repeat-purchase coverage", ecdf, "threshold_days", "cumulative_share", label_suffix=" days")
        self._display_insights("Purchase behavior insights", insights)
        return result

    def churn_analysis(self, churn_threshold: int) -> dict:
        threshold = self._validate_threshold(churn_threshold)
        self.last_churn_threshold = threshold

        job = self._run("03_churn_analysis.sql", churn_threshold=threshold)
        churn_t = f"`{self.out}.churn_users`"
        base_t = f"`{self.out}.churn_base`"
        gaps_t = f"`{self.out}.purchase_day_gaps`"

        overall = self._one(f"""
            SELECT
              MAX(analysis_date) AS analysis_date,
              COUNT(*) AS total_users,
              COUNTIF(churn_status = 'never_purchased') AS never_purchased,
              COUNTIF(churn_status != 'never_purchased') AS purchasers,
              COUNTIF(churn_status = 'active_purchaser') AS active_purchasers,
              COUNTIF(churn_status = 'churned') AS churned_users,
              SAFE_DIVIDE(COUNTIF(churn_status = 'churned'), COUNTIF(churn_status != 'never_purchased')) AS churn_rate,
              COUNTIF(purchase_count = 1 AND churn_status != 'never_purchased') AS one_time_purchasers,
              COUNTIF(purchase_count > 1) AS repeat_purchasers,
              COUNTIF(churn_status = 'churned' AND purchase_count = 1) AS churned_one_time_buyers,
              COUNTIF(churn_status = 'churned' AND purchase_count > 1) AS churned_repeat_buyers,
              SUM(IF(churn_status = 'churned', revenue, 0)) AS churned_historical_revenue,
              SUM(IF(churn_status != 'never_purchased', revenue, 0)) AS purchaser_historical_revenue,
              SAFE_DIVIDE(SUM(IF(churn_status = 'churned', revenue, 0)), SUM(IF(churn_status != 'never_purchased', revenue, 0))) AS churned_revenue_share
            FROM {churn_t}
        """)

        by_status = self._rows(f"""
            SELECT
              churn_status,
              COUNT(*) AS users,
              AVG(purchase_count) AS avg_purchases,
              APPROX_QUANTILES(purchase_count,100)[OFFSET(50)] AS median_purchases,
              AVG(revenue) AS avg_revenue,
              APPROX_QUANTILES(revenue,100)[OFFSET(50)] AS median_revenue,
              AVG(days_since_last_purchase) AS avg_days_since_last_purchase,
              APPROX_QUANTILES(days_since_last_purchase,100)[OFFSET(50)] AS median_days_since_last_purchase,
              SUM(revenue) AS historical_revenue
            FROM {churn_t}
            GROUP BY churn_status
            ORDER BY CASE churn_status WHEN 'active_purchaser' THEN 1 WHEN 'churned' THEN 2 ELSE 3 END
        """)

        frequency = self._rows(f"""
            SELECT
              CASE
                WHEN purchase_count = 1 THEN '1 purchase'
                WHEN purchase_count = 2 THEN '2 purchases'
                WHEN purchase_count BETWEEN 3 AND 5 THEN '3-5 purchases'
                ELSE '6+ purchases'
              END AS purchase_frequency,
              CASE
                WHEN purchase_count = 1 THEN 1
                WHEN purchase_count = 2 THEN 2
                WHEN purchase_count BETWEEN 3 AND 5 THEN 3
                ELSE 4
              END AS ord,
              COUNT(*) AS purchasers,
              COUNTIF(days_since_last_purchase > {threshold}) AS churned_users,
              SAFE_DIVIDE(COUNTIF(days_since_last_purchase > {threshold}), COUNT(*)) AS churn_rate,
              AVG(revenue) AS avg_revenue
            FROM {base_t}
            WHERE purchase_count > 0
            GROUP BY purchase_frequency, ord
            ORDER BY ord
        """)

        sensitivity_thresholds = sorted({max(1, threshold - 60), max(1, threshold - 30), max(1, threshold - 15), threshold, threshold + 15, threshold + 30, threshold + 60})
        threshold_array = ",".join(str(x) for x in sensitivity_thresholds)
        sensitivity = self._rows(f"""
            WITH thresholds AS (
              SELECT threshold_days FROM UNNEST([{threshold_array}]) threshold_days
            )
            SELECT
              threshold_days,
              COUNTIF(b.days_since_last_purchase > threshold_days) AS churned_users,
              SAFE_DIVIDE(COUNTIF(b.days_since_last_purchase > threshold_days), COUNT(*)) AS churn_rate
            FROM {base_t} b
            CROSS JOIN thresholds
            WHERE b.purchase_count > 0
            GROUP BY threshold_days
            ORDER BY threshold_days
        """)

        threshold_context = self._one(f"""
            SELECT
              COUNT(*) AS gap_observations,
              SAFE_DIVIDE(COUNTIF(gap_days <= {threshold}), COUNT(*)) AS observed_gap_coverage,
              APPROX_QUANTILES(gap_days,100)[OFFSET(50)] AS gap_median,
              APPROX_QUANTILES(gap_days,100)[OFFSET(75)] AS gap_p75,
              APPROX_QUANTILES(gap_days,100)[OFFSET(90)] AS gap_p90,
              APPROX_QUANTILES(gap_days,100)[OFFSET(95)] AS gap_p95
            FROM {gaps_t}
        """)

        insights = self._churn_insights(threshold, overall, frequency, sensitivity, threshold_context)

        self._display_cards(
            "Churn analysis",
            [
                ("Threshold", f"{threshold} d"),
                ("Purchasers", self._fmt(overall.get("purchasers"))),
                ("Active purchasers", self._fmt(overall.get("active_purchasers"))),
                ("Churned users", self._fmt(overall.get("churned_users"))),
                ("Churn rate", self._pct(overall.get("churn_rate"))),
                ("One-time purchasers", self._fmt(overall.get("one_time_purchasers"))),
                ("Churned one-time", self._fmt(overall.get("churned_one_time_buyers"))),
                ("Churned repeat", self._fmt(overall.get("churned_repeat_buyers"))),
                ("Churned revenue share", self._pct(overall.get("churned_revenue_share"))),
                ("Gap coverage", self._pct(threshold_context.get("observed_gap_coverage"))),
            ],
            f"Analysis date: {overall.get('analysis_date')} · Never-purchased users are excluded from churn rate.",
        )
        self._display_table(
            "Status diagnostics",
            by_status,
            [
                ("churn_status", "Status"), ("users", "Users"), ("avg_purchases", "Avg purchases"),
                ("median_purchases", "Median purchases"), ("avg_revenue", "Avg revenue"),
                ("median_revenue", "Median revenue"), ("avg_days_since_last_purchase", "Avg inactive days"),
                ("median_days_since_last_purchase", "Median inactive days"),
            ],
        )
        self._display_bars("Purchaser status", by_status[:2], "churn_status", "users")
        self._display_rate_bars("Churn rate by purchase frequency", frequency, "purchase_frequency", "churn_rate")
        self._display_rate_bars("Threshold sensitivity", sensitivity, "threshold_days", "churn_rate", label_suffix=" days")
        self._display_insights("Churn insights", insights)

        dashboard = Path("ga4_churn_dashboard.html").resolve()
        dashboard.write_text(self._dashboard_html(threshold, overall, by_status, frequency, sensitivity, threshold_context, insights), encoding="utf-8")
        try:
            from IPython.display import FileLink, display
            display(FileLink(str(dashboard)))
        except Exception:
            print(f"Dashboard: {dashboard}")

        return {
            "threshold": threshold,
            "overall": overall,
            "by_status": by_status,
            "purchase_frequency": frequency,
            "threshold_sensitivity": sensitivity,
            "threshold_context": threshold_context,
            "insights": insights,
            "job_id": job.job_id,
            "dashboard_path": str(dashboard),
        }

    def _purchase_gap_insights(self, stats: dict) -> list[str]:
        if not stats or not stats.get("gap_observations"):
            return ["No repeat-purchase gaps were found. At least two distinct purchase days per user are required."]
        median = self._num(stats.get("median"))
        p25 = self._num(stats.get("p25"))
        p75 = self._num(stats.get("p75"))
        p90 = self._num(stats.get("p90"))
        mean = self._num(stats.get("mean_gap_days"))
        cv = self._num(stats.get("coefficient_of_variation"))
        coverage90 = self._num(stats.get("share_within_90d"))
        insights = []
        if median is not None:
            insights.append(f"The median repeat-purchase interval is {median:.0f} days.")
        if p25 is not None and p75 is not None:
            insights.append(f"The middle 50% of repeat-purchase intervals fall between {p25:.0f} and {p75:.0f} days.")
        if p90 is not None:
            insights.append(f"90% of observed repeat-purchase intervals are at or below approximately {p90:.0f} days.")
        if coverage90 is not None:
            insights.append(f"{coverage90*100:.1f}% of observed repeat-purchase intervals occur within 90 days.")
        if mean is not None and median not in (None, 0):
            if mean / median >= 1.35:
                insights.append("The distribution is right-skewed: long repurchase intervals pull the mean above the median.")
            else:
                insights.append("Mean and median are relatively close, so extreme long gaps are not dominating the distribution.")
        if cv is not None:
            if cv >= 1:
                insights.append("Repurchase timing is highly variable; a single inactivity cutoff should be interpreted cautiously.")
            elif cv >= 0.5:
                insights.append("Repurchase timing shows moderate variability across observed intervals.")
            else:
                insights.append("Repurchase timing is relatively concentrated around its average.")
        return insights

    def _churn_insights(self, threshold: int, overall: dict, frequency: list[dict], sensitivity: list[dict], threshold_context: dict) -> list[str]:
        insights = []
        churn_rate = self._num(overall.get("churn_rate"))
        gap_coverage = self._num(threshold_context.get("observed_gap_coverage"))
        p90 = self._num(threshold_context.get("gap_p90"))
        if churn_rate is not None:
            insights.append(f"At a {threshold}-day cutoff, {churn_rate*100:.1f}% of historical purchasers are classified as churned.")
        if gap_coverage is not None:
            insights.append(f"The selected cutoff is longer than or equal to {gap_coverage*100:.1f}% of observed repeat-purchase intervals.")
        if p90 is not None:
            relation = "above" if threshold > p90 else "below"
            insights.append(f"The selected threshold ({threshold} days) is {relation} the observed P90 repeat-purchase interval ({p90:.0f} days).")
        churned = float(overall.get("churned_users") or 0)
        churned_one = float(overall.get("churned_one_time_buyers") or 0)
        if churned > 0:
            insights.append(f"One-time buyers account for {churned_one/churned*100:.1f}% of churned purchasers.")
        rev_share = self._num(overall.get("churned_revenue_share"))
        if rev_share is not None:
            insights.append(f"Users currently classified as churned represent {rev_share*100:.1f}% of historical purchaser revenue in the analyzed data.")
        one_time = next((r for r in frequency if r.get("purchase_frequency") == "1 purchase"), None)
        repeat6 = next((r for r in frequency if r.get("purchase_frequency") == "6+ purchases"), None)
        if one_time and repeat6:
            r1 = self._num(one_time.get("churn_rate"))
            r6 = self._num(repeat6.get("churn_rate"))
            if r1 is not None and r6 is not None:
                insights.append(f"Churn rate is {r1*100:.1f}% for one-time purchasers versus {r6*100:.1f}% for users with 6+ purchases.")
        lower = [r for r in sensitivity if int(r.get("threshold_days")) < threshold]
        higher = [r for r in sensitivity if int(r.get("threshold_days")) > threshold]
        if lower and higher:
            lo, hi = lower[-1], higher[0]
            lo_rate, hi_rate = self._num(lo.get("churn_rate")), self._num(hi.get("churn_rate"))
            if lo_rate is not None and hi_rate is not None:
                insights.append(f"Sensitivity check: {int(lo['threshold_days'])} days gives {lo_rate*100:.1f}% churn; {int(hi['threshold_days'])} days gives {hi_rate*100:.1f}% churn.")
        return insights

    def _hist_sql(self, table: str) -> str:
        return f"""
        SELECT bucket, COUNT(*) AS gaps
        FROM (
          SELECT
            CASE
              WHEN gap_days <= 7 THEN '0-7'
              WHEN gap_days <= 14 THEN '8-14'
              WHEN gap_days <= 30 THEN '15-30'
              WHEN gap_days <= 60 THEN '31-60'
              WHEN gap_days <= 90 THEN '61-90'
              WHEN gap_days <= 180 THEN '91-180'
              WHEN gap_days <= 365 THEN '181-365'
              ELSE '366+'
            END AS bucket,
            CASE
              WHEN gap_days <= 7 THEN 1 WHEN gap_days <= 14 THEN 2 WHEN gap_days <= 30 THEN 3
              WHEN gap_days <= 60 THEN 4 WHEN gap_days <= 90 THEN 5 WHEN gap_days <= 180 THEN 6
              WHEN gap_days <= 365 THEN 7 ELSE 8
            END AS ord
          FROM {table}
        )
        GROUP BY bucket, ord
        ORDER BY ord
        """

    @staticmethod
    def _num(v):
        if v is None:
            return None
        try:
            return float(v)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _fmt(v, d=0):
        if v is None:
            return "—"
        return f"{float(v):,.{d}f}"

    @staticmethod
    def _pct(v):
        return "—" if v is None else f"{float(v)*100:.1f}%"

    def _display_cards(self, title, cards, subtitle=""):
        try:
            from IPython.display import HTML, display
            body = "".join(
                "<div style='border:1px solid #e2e8f0;border-radius:12px;padding:14px'>"
                f"<div style='font-size:12px;color:#64748b'>{html.escape(str(k))}</div>"
                f"<div style='font-size:22px;font-weight:700'>{html.escape(str(v))}</div></div>"
                for k, v in cards
            )
            display(HTML(
                "<div style='font-family:Arial;max-width:1150px'>"
                f"<h2 style='margin-bottom:4px'>{html.escape(title)}</h2>"
                f"<div style='color:#64748b;font-size:12px'>{html.escape(str(subtitle))}</div>"
                "<div style='display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:10px;margin:12px 0'>"
                f"{body}</div></div>"
            ))
        except Exception:
            print(title, cards)

    def _display_table(self, title, rows, columns):
        if not rows:
            return
        try:
            from IPython.display import HTML, display
            head = "".join(f"<th>{html.escape(label)}</th>" for _, label in columns)
            body = ""
            for row in rows:
                body += "<tr>"
                for key, _ in columns:
                    value = row.get(key)
                    if isinstance(value, float):
                        value = f"{value:,.2f}"
                    body += f"<td>{html.escape(str(value if value is not None else '—'))}</td>"
                body += "</tr>"
            display(HTML(
                "<div style='font-family:Arial;max-width:1150px;margin:14px 0'>"
                f"<h3>{html.escape(title)}</h3>"
                "<table style='width:100%;border-collapse:collapse'>"
                f"<thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>"
                "<style>th,td{padding:9px 10px;border-bottom:1px solid #e2e8f0;text-align:right}"
                "th:first-child,td:first-child{text-align:left}th{background:#f8fafc}</style></div>"
            ))
        except Exception:
            pass

    def _display_bars(self, title, rows, label_key, value_key):
        try:
            from IPython.display import HTML, display
            maximum = max([float(r.get(value_key) or 0) for r in rows] or [1])
            bars = "".join(
                "<div style='display:grid;grid-template-columns:160px 1fr 90px;gap:8px;margin:8px 0;align-items:center'>"
                f"<span>{html.escape(str(r.get(label_key)))}</span>"
                "<div style='height:13px;background:#e2e8f0;border-radius:8px'>"
                f"<div style='height:13px;width:{0 if maximum == 0 else float(r.get(value_key) or 0)/maximum*100:.1f}%;background:#334155;border-radius:8px'></div></div>"
                f"<span>{self._fmt(r.get(value_key))}</span></div>"
                for r in rows
            )
            display(HTML(f"<div style='font-family:Arial;max-width:950px'><h3>{html.escape(title)}</h3>{bars}</div>"))
        except Exception:
            pass

    def _display_rate_bars(self, title, rows, label_key, value_key, label_suffix=""):
        try:
            from IPython.display import HTML, display
            bars = "".join(
                "<div style='display:grid;grid-template-columns:160px 1fr 90px;gap:8px;margin:8px 0;align-items:center'>"
                f"<span>{html.escape(str(r.get(label_key)) + label_suffix)}</span>"
                "<div style='height:13px;background:#e2e8f0;border-radius:8px'>"
                f"<div style='height:13px;width:{max(0,min(100,float(r.get(value_key) or 0)*100)):.1f}%;background:#475569;border-radius:8px'></div></div>"
                f"<span>{self._pct(r.get(value_key))}</span></div>"
                for r in rows
            )
            display(HTML(f"<div style='font-family:Arial;max-width:950px'><h3>{html.escape(title)}</h3>{bars}</div>"))
        except Exception:
            pass

    def _display_insights(self, title, insights):
        try:
            from IPython.display import HTML, display
            items = "".join(f"<li style='margin:8px 0'>{html.escape(str(x))}</li>" for x in insights)
            display(HTML(
                "<div style='font-family:Arial;max-width:1050px;border:1px solid #e2e8f0;border-radius:14px;"
                "padding:14px 18px;margin:16px 0;background:#f8fafc'>"
                f"<h3 style='margin-top:0'>{html.escape(title)}</h3><ul>{items}</ul></div>"
            ))
        except Exception:
            for insight in insights:
                print("-", insight)

    def _dashboard_html(self, threshold, overall, by_status, frequency, sensitivity, threshold_context, insights):
        diagnostic_rows = "".join(
            f"<tr><td>{html.escape(str(r.get('churn_status')))}</td>"
            f"<td>{self._fmt(r.get('users'))}</td>"
            f"<td>{self._fmt(r.get('avg_purchases'),2)}</td>"
            f"<td>{self._fmt(r.get('median_purchases'),1)}</td>"
            f"<td>{self._fmt(r.get('avg_revenue'),2)}</td>"
            f"<td>{self._fmt(r.get('median_revenue'),2)}</td>"
            f"<td>{self._fmt(r.get('avg_days_since_last_purchase'),1)}</td></tr>"
            for r in by_status
        )
        frequency_rows = "".join(
            f"<tr><td>{html.escape(str(r.get('purchase_frequency')))}</td>"
            f"<td>{self._fmt(r.get('purchasers'))}</td>"
            f"<td>{self._fmt(r.get('churned_users'))}</td>"
            f"<td>{self._pct(r.get('churn_rate'))}</td>"
            f"<td>{self._fmt(r.get('avg_revenue'),2)}</td></tr>"
            for r in frequency
        )
        sensitivity_rows = "".join(
            f"<tr><td>{self._fmt(r.get('threshold_days'))}</td>"
            f"<td>{self._fmt(r.get('churned_users'))}</td>"
            f"<td>{self._pct(r.get('churn_rate'))}</td></tr>"
            for r in sensitivity
        )
        insight_items = "".join(f"<li>{html.escape(str(x))}</li>" for x in insights)
        cards = [
            ("Threshold", f"{threshold} days"),
            ("Purchasers", self._fmt(overall.get("purchasers"))),
            ("Active purchasers", self._fmt(overall.get("active_purchasers"))),
            ("Churned users", self._fmt(overall.get("churned_users"))),
            ("Churn rate", self._pct(overall.get("churn_rate"))),
            ("Gap coverage", self._pct(threshold_context.get("observed_gap_coverage"))),
            ("Churned revenue share", self._pct(overall.get("churned_revenue_share"))),
        ]
        card_html = "".join(
            f"<div class='card'><div class='label'>{html.escape(k)}</div><div class='value'>{html.escape(v)}</div></div>"
            for k, v in cards
        )
        return f"""<!doctype html>
<html><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'>
<title>GA4 Basic Churn Dashboard</title>
<style>
body{{font-family:Arial,sans-serif;background:#f8fafc;margin:0;color:#0f172a}}main{{max-width:1180px;margin:auto;padding:28px}}
header{{background:#0f172a;color:white;padding:26px;border-radius:18px}}.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(155px,1fr));gap:12px;margin:18px 0}}
.card,.panel{{background:white;border:1px solid #e2e8f0;border-radius:14px;padding:16px}}.value{{font-size:26px;font-weight:700;margin-top:4px}}.label{{font-size:12px;color:#64748b}}
.panel{{margin-top:14px}}table{{width:100%;border-collapse:collapse}}th,td{{padding:10px;border-bottom:1px solid #e2e8f0;text-align:right}}th:first-child,td:first-child{{text-align:left}}
th{{background:#f8fafc;font-size:12px;color:#475569}}li{{margin:9px 0;line-height:1.45}}.small{{font-size:12px;color:#cbd5e1}}
</style></head><body><main>
<header><h1 style='margin:0 0 8px'>GA4 Basic Churn Dashboard</h1><div>{html.escape(self.source)}</div><div class='small'>Analysis date {html.escape(str(overall.get('analysis_date')))} · Purchase-based churn</div></header>
<section class='grid'>{card_html}</section>
<section class='panel'><h2>Analytical insights</h2><ul>{insight_items}</ul></section>
<section class='panel'><h2>Status diagnostics</h2><table><thead><tr><th>Status</th><th>Users</th><th>Avg purchases</th><th>Median purchases</th><th>Avg revenue</th><th>Median revenue</th><th>Avg inactive days</th></tr></thead><tbody>{diagnostic_rows}</tbody></table></section>
<section class='panel'><h2>Churn by purchase frequency</h2><table><thead><tr><th>Purchase frequency</th><th>Purchasers</th><th>Churned</th><th>Churn rate</th><th>Avg revenue</th></tr></thead><tbody>{frequency_rows}</tbody></table></section>
<section class='panel'><h2>Threshold sensitivity</h2><table><thead><tr><th>Threshold days</th><th>Churned users</th><th>Churn rate</th></tr></thead><tbody>{sensitivity_rows}</tbody></table></section>
<section class='panel'><b>Definition.</b> A user with at least one purchase is churned when days since last purchase &gt; {threshold}. Never-purchased users are excluded from the churn-rate denominator.</section>
</main></body></html>"""
