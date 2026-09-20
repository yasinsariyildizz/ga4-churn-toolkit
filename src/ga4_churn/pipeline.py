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
    """Very basic purchase-based churn analysis for GA4 BigQuery exports."""

    def __init__(self, project_id: str, dataset_id: str, table_id: str,
                 output_dataset_id: str, churn_threshold: int):
        self.project_id = project_id.strip()
        self.dataset_id = dataset_id.strip()
        self.table_id = table_id.strip()
        self.output_dataset_id = output_dataset_id.strip()
        self.churn_threshold = int(churn_threshold)
        self._validate()
        self.client = bigquery.Client(project=self.project_id)

    def _validate(self):
        if not _PROJECT_RE.match(self.project_id): raise ValueError("Invalid project_id")
        if not _ID_RE.match(self.dataset_id): raise ValueError("Invalid dataset_id")
        if not _TABLE_RE.match(self.table_id): raise ValueError("Invalid table_id")
        if not _ID_RE.match(self.output_dataset_id): raise ValueError("Invalid output_dataset_id")
        if self.churn_threshold < 1: raise ValueError("churn_threshold must be >= 1")

    @property
    def source(self):
        return f"{self.project_id}.{self.dataset_id}.{self.table_id}"

    @property
    def out(self):
        return f"{self.project_id}.{self.output_dataset_id}"

    def _ensure_output_dataset(self):
        source_ds = self.client.get_dataset(f"{self.project_id}.{self.dataset_id}")
        ds = bigquery.Dataset(self.out)
        ds.location = source_ds.location
        self.client.create_dataset(ds, exists_ok=True)

    def _sql(self, name: str):
        text = resources.files("ga4_churn").joinpath("sql").joinpath(name).read_text(encoding="utf-8")
        for k, v in {
            "{{PROJECT_ID}}": self.project_id,
            "{{DATASET_ID}}": self.dataset_id,
            "{{TABLE_ID}}": self.table_id,
            "{{OUTPUT_DATASET_ID}}": self.output_dataset_id,
        }.items():
            text = text.replace(k, v)
        return text

    def _run(self, sql_name: str, threshold=False):
        self._ensure_output_dataset()
        params = [bigquery.ScalarQueryParameter("churn_threshold", "INT64", self.churn_threshold)] if threshold else []
        job = self.client.query(self._sql(sql_name), job_config=bigquery.QueryJobConfig(query_parameters=params))
        job.result()
        return job

    def _rows(self, sql: str):
        return [dict(r.items()) for r in self.client.query(sql).result()]

    def _one(self, sql: str):
        rows = self._rows(sql)
        return rows[0] if rows else {}

    def dry_run(self):
        q1 = f"SELECT COUNT(*) FROM `{self.source}`"
        q2 = f"SELECT user_pseudo_id,event_date FROM `{self.source}` WHERE event_name='purchase'"
        details, total = [], 0
        for name, sql in [("Base table scan", q1), ("Purchase gap scan", q2)]:
            job = self.client.query(sql, job_config=bigquery.QueryJobConfig(dry_run=True, use_query_cache=False))
            b = int(job.total_bytes_processed or 0)
            total += b
            details.append({"name": name, "gb": round(b/1024**3, 3)})
        result = {"estimated_gb": round(total/1024**3, 3), "details": details, "source": self.source}
        self._display_cards("Dry run", [("Estimated scan", f"{result['estimated_gb']:.3f} GB"), ("Threshold", f"{self.churn_threshold} days")])
        return result

    def base_table(self):
        job = self._run("01_base_table.sql")
        t = f"`{self.out}.churn_base`"
        result = self._one(f"""
            SELECT MAX(analysis_date) analysis_date, COUNT(*) users,
                   COUNTIF(purchase_count>0) purchasers,
                   COUNTIF(purchase_count>1) repeat_purchasers,
                   SUM(session_count) sessions, SUM(event_count) events,
                   SUM(purchase_count) purchases, SUM(revenue) revenue,
                   SAFE_DIVIDE(COUNTIF(purchase_count>0),COUNT(*)) purchaser_rate,
                   SAFE_DIVIDE(COUNTIF(purchase_count>1),COUNTIF(purchase_count>0)) repeat_rate
            FROM {t}
        """)
        result["job_id"] = job.job_id
        self._display_cards("Base table", [
            ("Users", self._fmt(result.get("users"))),
            ("Purchasers", self._fmt(result.get("purchasers"))),
            ("Repeat purchasers", self._fmt(result.get("repeat_purchasers"))),
            ("Sessions", self._fmt(result.get("sessions"))),
            ("Purchases", self._fmt(result.get("purchases"))),
            ("Revenue", self._fmt(result.get("revenue"),2)),
        ], f"Analysis date: {result.get('analysis_date')} · Output: {self.out}.churn_base")
        return result

    def purchase_day_distribution(self):
        job = self._run("02_purchase_day_distribution.sql")
        t = f"`{self.out}.purchase_day_gaps`"
        stats = self._one(f"""
            SELECT COUNT(*) gap_observations, COUNT(DISTINCT user_pseudo_id) repeat_purchasers,
                   AVG(gap_days) mean_gap_days, STDDEV_POP(gap_days) stddev_gap_days,
                   APPROX_QUANTILES(gap_days,100)[OFFSET(25)] p25,
                   APPROX_QUANTILES(gap_days,100)[OFFSET(50)] median,
                   APPROX_QUANTILES(gap_days,100)[OFFSET(75)] p75,
                   APPROX_QUANTILES(gap_days,100)[OFFSET(90)] p90,
                   APPROX_QUANTILES(gap_days,100)[OFFSET(95)] p95,
                   MAX(gap_days) max_gap_days
            FROM {t}
        """)
        hist = self._rows(self._hist_sql(t))
        result = {"stats": stats, "histogram": hist, "job_id": job.job_id}
        self._display_cards("Purchase day distribution", [
            ("Mean gap", f"{self._fmt(stats.get('mean_gap_days'),1)} d"),
            ("Median", f"{self._fmt(stats.get('median'))} d"),
            ("P75", f"{self._fmt(stats.get('p75'))} d"),
            ("P90", f"{self._fmt(stats.get('p90'))} d"),
            ("P95", f"{self._fmt(stats.get('p95'))} d"),
            ("Selected threshold", f"{self.churn_threshold} d"),
        ])
        self._display_bars("Purchase-gap histogram", hist, "bucket", "gaps")
        return result

    def churn_analysis(self):
        job = self._run("03_churn_analysis.sql", threshold=True)
        t = f"`{self.out}.churn_users`"
        overall = self._one(f"""
            SELECT MAX(analysis_date) analysis_date,
                   COUNTIF(churn_status!='never_purchased') purchasers,
                   COUNTIF(churn_status='active_purchaser') active_purchasers,
                   COUNTIF(churn_status='churned') churned_users,
                   SAFE_DIVIDE(COUNTIF(churn_status='churned'),COUNTIF(churn_status!='never_purchased')) churn_rate,
                   COUNTIF(churn_status='churned' AND purchase_count=1) churned_one_time_buyers
            FROM {t}
        """)
        by_status = self._rows(f"""
            SELECT churn_status, COUNT(*) users, AVG(purchase_count) avg_purchases,
                   AVG(revenue) avg_revenue, AVG(days_since_last_purchase) avg_days_since_last_purchase,
                   SUM(revenue) historical_revenue
            FROM {t}
            GROUP BY churn_status
            ORDER BY CASE churn_status WHEN 'active_purchaser' THEN 1 WHEN 'churned' THEN 2 ELSE 3 END
        """)
        self._display_cards("Churn analysis", [
            ("Purchasers", self._fmt(overall.get("purchasers"))),
            ("Active purchasers", self._fmt(overall.get("active_purchasers"))),
            ("Churned users", self._fmt(overall.get("churned_users"))),
            ("Churn rate", self._pct(overall.get("churn_rate"))),
            ("Churned one-time buyers", self._fmt(overall.get("churned_one_time_buyers"))),
        ], f"Threshold: {self.churn_threshold} days · Analysis date: {overall.get('analysis_date')}")
        self._display_bars("User status", by_status, "churn_status", "users")
        dashboard = Path("ga4_churn_dashboard.html").resolve()
        dashboard.write_text(self._dashboard_html(overall, by_status), encoding="utf-8")
        try:
            from IPython.display import FileLink, display
            display(FileLink(str(dashboard)))
        except Exception:
            print(f"Dashboard: {dashboard}")
        return {"overall": overall, "by_status": by_status, "job_id": job.job_id, "dashboard_path": str(dashboard)}

    def _hist_sql(self, table):
        return f"""
        SELECT bucket, COUNT(*) gaps FROM (
          SELECT CASE WHEN gap_days<=7 THEN '0-7' WHEN gap_days<=14 THEN '8-14'
                      WHEN gap_days<=30 THEN '15-30' WHEN gap_days<=60 THEN '31-60'
                      WHEN gap_days<=90 THEN '61-90' WHEN gap_days<=180 THEN '91-180' ELSE '181+' END bucket,
                 CASE WHEN gap_days<=7 THEN 1 WHEN gap_days<=14 THEN 2 WHEN gap_days<=30 THEN 3
                      WHEN gap_days<=60 THEN 4 WHEN gap_days<=90 THEN 5 WHEN gap_days<=180 THEN 6 ELSE 7 END ord
          FROM {table}
        ) GROUP BY bucket,ord ORDER BY ord
        """

    @staticmethod
    def _fmt(v, d=0):
        if v is None: return "—"
        return f"{float(v):,.{d}f}"

    @staticmethod
    def _pct(v):
        return "—" if v is None else f"{float(v)*100:.1f}%"

    def _display_cards(self, title, cards, subtitle=""):
        try:
            from IPython.display import HTML, display
            body = "".join(f"<div style='border:1px solid #e2e8f0;border-radius:12px;padding:14px'><div style='font-size:12px;color:#64748b'>{html.escape(k)}</div><div style='font-size:22px;font-weight:700'>{html.escape(str(v))}</div></div>" for k,v in cards)
            display(HTML(f"<div style='font-family:Arial;max-width:1050px'><h2 style='margin-bottom:4px'>{html.escape(title)}</h2><div style='color:#64748b;font-size:12px'>{html.escape(subtitle)}</div><div style='display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:10px;margin:12px 0'>{body}</div></div>"))
        except Exception:
            print(title, cards)

    def _display_bars(self, title, rows, label_key, value_key):
        try:
            from IPython.display import HTML, display
            m = max([float(r.get(value_key) or 0) for r in rows] or [1])
            bars = "".join(f"<div style='display:grid;grid-template-columns:140px 1fr 80px;gap:8px;margin:8px 0;align-items:center'><span>{html.escape(str(r.get(label_key)))}</span><div style='height:12px;background:#e2e8f0;border-radius:8px'><div style='height:12px;width:{0 if m==0 else float(r.get(value_key) or 0)/m*100:.1f}%;background:#334155;border-radius:8px'></div></div><span>{self._fmt(r.get(value_key))}</span></div>" for r in rows)
            display(HTML(f"<div style='font-family:Arial;max-width:900px'><h3>{html.escape(title)}</h3>{bars}</div>"))
        except Exception:
            pass

    def _dashboard_html(self, overall, by_status):
        rows = "".join(f"<tr><td>{html.escape(str(r.get('churn_status')))}</td><td>{self._fmt(r.get('users'))}</td><td>{self._fmt(r.get('avg_purchases'),2)}</td><td>{self._fmt(r.get('avg_revenue'),2)}</td><td>{self._fmt(r.get('avg_days_since_last_purchase'),1)}</td></tr>" for r in by_status)
        return f"""<!doctype html><html><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'><title>GA4 Basic Churn Dashboard</title><style>body{{font-family:Arial;background:#f8fafc;margin:0;color:#0f172a}}main{{max-width:1100px;margin:auto;padding:28px}}header{{background:#0f172a;color:white;padding:24px;border-radius:18px}}.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));gap:12px;margin:18px 0}}.card,.panel{{background:white;border:1px solid #e2e8f0;border-radius:14px;padding:16px}}.value{{font-size:26px;font-weight:700}}.label{{font-size:12px;color:#64748b}}table{{width:100%;border-collapse:collapse}}th,td{{padding:10px;border-bottom:1px solid #e2e8f0;text-align:right}}th:first-child,td:first-child{{text-align:left}}</style></head><body><main><header><h1>GA4 Basic Churn Dashboard</h1><div>{html.escape(self.source)} · threshold {self.churn_threshold} days · analysis date {html.escape(str(overall.get('analysis_date')))}</div></header><section class='grid'><div class='card'><div class='label'>Purchasers</div><div class='value'>{self._fmt(overall.get('purchasers'))}</div></div><div class='card'><div class='label'>Active purchasers</div><div class='value'>{self._fmt(overall.get('active_purchasers'))}</div></div><div class='card'><div class='label'>Churned users</div><div class='value'>{self._fmt(overall.get('churned_users'))}</div></div><div class='card'><div class='label'>Churn rate</div><div class='value'>{self._pct(overall.get('churn_rate'))}</div></div></section><section class='panel'><h2>Status diagnostics</h2><table><thead><tr><th>Status</th><th>Users</th><th>Avg purchases</th><th>Avg revenue</th><th>Avg inactive days</th></tr></thead><tbody>{rows}</tbody></table></section><section class='panel' style='margin-top:14px'>Definition: users with at least one purchase are churned when days since last purchase &gt; {self.churn_threshold}. Never-purchased users are excluded from churn rate.</section></main></body></html>"""
