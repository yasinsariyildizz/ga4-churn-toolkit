from __future__ import annotations

from pathlib import Path
from google.cloud import bigquery

from .pipeline import ChurnAnalysis as _BaseChurnAnalysis


class ChurnAnalysis(_BaseChurnAnalysis):
    """GA4 purchase churn analysis using user_id with active/pre-churn/churn states."""

    @staticmethod
    def _validate_thresholds(pre_churn_threshold: int, churn_threshold: int) -> tuple[int, int]:
        pre, churn = int(pre_churn_threshold), int(churn_threshold)
        if pre < 1 or churn < 1:
            raise ValueError("Thresholds must be >= 1")
        if pre >= churn:
            raise ValueError("pre_churn_threshold must be smaller than churn_threshold")
        return pre, churn

    def _run_with_thresholds(self, sql_name: str, pre: int, churn: int):
        self._ensure_output_dataset()
        pre, churn = self._validate_thresholds(pre, churn)
        config = bigquery.QueryJobConfig(query_parameters=[
            bigquery.ScalarQueryParameter("pre_churn_threshold", "INT64", pre),
            bigquery.ScalarQueryParameter("churn_threshold", "INT64", churn),
        ])
        job = self.client.query(self._sql(sql_name), job_config=config)
        job.result()
        return job

    def dry_run(self) -> dict:
        queries = [
            ("Base table scan", f"SELECT user_id,event_date,event_name,event_params,ecommerce FROM `{self.source}` WHERE user_id IS NOT NULL"),
            ("Purchase gap scan", f"SELECT user_id,event_date FROM `{self.source}` WHERE event_name='purchase' AND user_id IS NOT NULL"),
        ]
        details, total = [], 0
        for name, sql in queries:
            job = self.client.query(sql, job_config=bigquery.QueryJobConfig(dry_run=True, use_query_cache=False))
            processed = int(job.total_bytes_processed or 0)
            total += processed
            details.append({"name": name, "bytes": processed, "gb": round(processed / 1024**3, 3)})
        result = {"estimated_gb": round(total / 1024**3, 3), "details": details, "source": self.source}
        self._display_cards("Dry run", [("Estimated scan", f"{result['estimated_gb']:.3f} GB"), ("Identity", "user_id")], "user_id boş kayıtlar analize alınmaz.")
        self._display_table("Estimated scan by step", details, [("name", "Step"), ("gb", "Estimated GB")])
        return result

    def create_base_table(self) -> dict:
        result = super().create_base_table()
        result["identity"] = "user_id"
        return result

    def purchase_day_distribution(self) -> dict:
        job = self._run("02_purchase_day_distribution.sql")
        t = f"`{self.out}.purchase_day_gaps`"
        stats = self._one(f"""
            WITH q AS (SELECT APPROX_QUANTILES(gap_days,100) qt FROM {t})
            SELECT COUNT(*) gap_observations, COUNT(DISTINCT user_id) repeat_purchasers,
              MIN(gap_days) min_gap_days, AVG(gap_days) mean_gap_days,
              STDDEV_POP(gap_days) stddev_gap_days, MAX(gap_days) max_gap_days,
              ANY_VALUE(q.qt[OFFSET(10)]) p10, ANY_VALUE(q.qt[OFFSET(25)]) p25,
              ANY_VALUE(q.qt[OFFSET(50)]) median, ANY_VALUE(q.qt[OFFSET(75)]) p75,
              ANY_VALUE(q.qt[OFFSET(90)]) p90, ANY_VALUE(q.qt[OFFSET(95)]) p95,
              SAFE_DIVIDE(STDDEV_POP(gap_days),NULLIF(AVG(gap_days),0)) coefficient_of_variation,
              SAFE_DIVIDE(COUNTIF(gap_days<=30),COUNT(*)) share_within_30d,
              SAFE_DIVIDE(COUNTIF(gap_days<=60),COUNT(*)) share_within_60d,
              SAFE_DIVIDE(COUNTIF(gap_days<=90),COUNT(*)) share_within_90d
            FROM {t} CROSS JOIN q
        """)
        p25, p75 = self._num(stats.get("p25")), self._num(stats.get("p75"))
        stats["iqr"] = None if p25 is None or p75 is None else p75 - p25
        hist = self._rows(self._hist_sql(t))
        coverage = self._rows(f"""
            WITH x AS (SELECT d FROM UNNEST([7,14,30,45,60,90,120,180,365]) d)
            SELECT d threshold_days, SAFE_DIVIDE(COUNTIF(gap_days<=d),COUNT(*)) cumulative_share
            FROM {t} CROSS JOIN x GROUP BY d ORDER BY d
        """)
        insights = self._purchase_gap_insights(stats)
        self._display_cards("Purchase day distribution", [
            ("Gap observations", self._fmt(stats.get("gap_observations"))),
            ("Repeat purchasers", self._fmt(stats.get("repeat_purchasers"))),
            ("Mean", f"{self._fmt(stats.get('mean_gap_days'),1)} d"),
            ("Median", f"{self._fmt(stats.get('median'))} d"),
            ("P75", f"{self._fmt(stats.get('p75'))} d"),
            ("P90", f"{self._fmt(stats.get('p90'))} d"),
            ("P95", f"{self._fmt(stats.get('p95'))} d"),
            ("IQR", f"{self._fmt(stats.get('iqr'),1)} d"),
        ], "Hesaplamalar yalnızca user_id bulunan kullanıcılardan yapılır.")
        self._display_table("Distribution statistics", [stats], [("min_gap_days","Min"),("p10","P10"),("p25","P25"),("median","P50"),("p75","P75"),("p90","P90"),("p95","P95"),("max_gap_days","Max")])
        self._display_bars("Purchase-gap histogram", hist, "bucket", "gaps")
        self._display_rate_bars("Cumulative repeat-purchase coverage", coverage, "threshold_days", "cumulative_share", label_suffix=" days")
        self._display_insights("Purchase behavior insights", insights)
        return {"stats": stats, "histogram": hist, "cumulative_distribution": coverage, "insights": insights, "job_id": job.job_id}

    def churn_analysis(self, pre_churn_threshold: int, churn_threshold: int) -> dict:
        pre, churn = self._validate_thresholds(pre_churn_threshold, churn_threshold)
        job = self._run_with_thresholds("03_churn_analysis.sql", pre, churn)
        ct = f"`{self.out}.churn_users`"
        bt = f"`{self.out}.churn_base`"
        gt = f"`{self.out}.purchase_day_gaps`"

        overall = self._one(f"""
            SELECT MAX(analysis_date) analysis_date,
              COUNTIF(churn_status!='never_purchased') purchasers,
              COUNTIF(churn_status='active_purchaser') active_purchasers,
              COUNTIF(churn_status='pre_churn') pre_churn_users,
              COUNTIF(churn_status='churned') churned_users,
              SAFE_DIVIDE(COUNTIF(churn_status='pre_churn'),COUNTIF(churn_status!='never_purchased')) pre_churn_rate,
              SAFE_DIVIDE(COUNTIF(churn_status='churned'),COUNTIF(churn_status!='never_purchased')) churn_rate,
              COUNTIF(churn_status='pre_churn' AND purchase_count=1) pre_churn_one_time_buyers,
              COUNTIF(churn_status='pre_churn' AND purchase_count>1) pre_churn_repeat_buyers,
              COUNTIF(churn_status='churned' AND purchase_count=1) churned_one_time_buyers,
              COUNTIF(churn_status='churned' AND purchase_count>1) churned_repeat_buyers,
              SAFE_DIVIDE(SUM(IF(churn_status='pre_churn',revenue,0)),SUM(IF(churn_status!='never_purchased',revenue,0))) pre_churn_revenue_share,
              SAFE_DIVIDE(SUM(IF(churn_status='churned',revenue,0)),SUM(IF(churn_status!='never_purchased',revenue,0))) churned_revenue_share
            FROM {ct}
        """)
        by_status = self._rows(f"""
            SELECT churn_status, COUNT(*) users,
              AVG(purchase_count) avg_purchases,
              APPROX_QUANTILES(purchase_count,100)[OFFSET(50)] median_purchases,
              AVG(revenue) avg_revenue,
              APPROX_QUANTILES(revenue,100)[OFFSET(50)] median_revenue,
              AVG(days_since_last_purchase) avg_days_since_last_purchase,
              APPROX_QUANTILES(days_since_last_purchase,100)[OFFSET(50)] median_days_since_last_purchase
            FROM {ct}
            GROUP BY churn_status
            ORDER BY CASE churn_status WHEN 'active_purchaser' THEN 1 WHEN 'pre_churn' THEN 2 WHEN 'churned' THEN 3 ELSE 4 END
        """)
        frequency = self._rows(f"""
            SELECT CASE WHEN purchase_count=1 THEN '1 purchase' WHEN purchase_count=2 THEN '2 purchases' WHEN purchase_count BETWEEN 3 AND 5 THEN '3-5 purchases' ELSE '6+ purchases' END purchase_frequency,
              CASE WHEN purchase_count=1 THEN 1 WHEN purchase_count=2 THEN 2 WHEN purchase_count BETWEEN 3 AND 5 THEN 3 ELSE 4 END ord,
              COUNT(*) purchasers,
              SAFE_DIVIDE(COUNTIF(days_since_last_purchase>{pre} AND days_since_last_purchase<={churn}),COUNT(*)) pre_churn_rate,
              SAFE_DIVIDE(COUNTIF(days_since_last_purchase>{churn}),COUNT(*)) churn_rate
            FROM {bt} WHERE purchase_count>0
            GROUP BY purchase_frequency,ord ORDER BY ord
        """)
        sensitivity_days = sorted({max(pre+1,churn-60),max(pre+1,churn-30),max(pre+1,churn-15),churn,churn+15,churn+30,churn+60})
        arr = ",".join(map(str,sensitivity_days))
        sensitivity = self._rows(f"""
            WITH x AS (SELECT d FROM UNNEST([{arr}]) d)
            SELECT d threshold_days, SAFE_DIVIDE(COUNTIF(days_since_last_purchase>d),COUNT(*)) churn_rate
            FROM {bt} CROSS JOIN x WHERE purchase_count>0 GROUP BY d ORDER BY d
        """)
        context = self._one(f"""
            SELECT SAFE_DIVIDE(COUNTIF(gap_days<={pre}),COUNT(*)) pre_churn_gap_coverage,
              SAFE_DIVIDE(COUNTIF(gap_days<={churn}),COUNT(*)) churn_gap_coverage,
              APPROX_QUANTILES(gap_days,100)[OFFSET(90)] gap_p90,
              APPROX_QUANTILES(gap_days,100)[OFFSET(95)] gap_p95
            FROM {gt}
        """)
        insights = [
            f"{self._pct(overall.get('pre_churn_rate'))} of purchasers are in the pre-churn window ({pre+1}-{churn} days).",
            f"{self._pct(overall.get('churn_rate'))} of purchasers are churned at the {churn}-day definition.",
            f"The pre-churn cutoff covers {self._pct(context.get('pre_churn_gap_coverage'))} of observed repeat-purchase intervals.",
            f"The churn cutoff covers {self._pct(context.get('churn_gap_coverage'))} of observed repeat-purchase intervals.",
        ]
        self._display_cards("Churn analysis", [
            ("Pre-churn threshold",f"{pre} d"),("Churn threshold",f"{churn} d"),
            ("Purchasers",self._fmt(overall.get("purchasers"))),("Active",self._fmt(overall.get("active_purchasers"))),
            ("Pre-churn",self._fmt(overall.get("pre_churn_users"))),("Pre-churn rate",self._pct(overall.get("pre_churn_rate"))),
            ("Churned",self._fmt(overall.get("churned_users"))),("Churn rate",self._pct(overall.get("churn_rate"))),
            ("Pre-churn revenue share",self._pct(overall.get("pre_churn_revenue_share"))),("Churned revenue share",self._pct(overall.get("churned_revenue_share"))),
        ], f"Active ≤ {pre} gün · Pre-churn {pre+1}-{churn} gün · Churned > {churn} gün · user_id bazlı")
        self._display_table("Status diagnostics", by_status, [("churn_status","Status"),("users","Users"),("avg_purchases","Avg purchases"),("median_purchases","Median purchases"),("avg_revenue","Avg revenue"),("median_revenue","Median revenue"),("avg_days_since_last_purchase","Avg inactive days"),("median_days_since_last_purchase","Median inactive days")])
        self._display_bars("Purchaser status", [r for r in by_status if r.get("churn_status")!="never_purchased"], "churn_status", "users")
        self._display_rate_bars("Pre-churn rate by purchase frequency", frequency, "purchase_frequency", "pre_churn_rate")
        self._display_rate_bars("Churn rate by purchase frequency", frequency, "purchase_frequency", "churn_rate")
        self._display_rate_bars("Churn threshold sensitivity", sensitivity, "threshold_days", "churn_rate", label_suffix=" days")
        self._display_insights("Analysis notes", insights)

        dashboard = Path("ga4_churn_dashboard.html").resolve()
        rows = "".join(f"<tr><td>{r['churn_status']}</td><td>{self._fmt(r['users'])}</td><td>{self._fmt(r.get('avg_purchases'),2)}</td><td>{self._fmt(r.get('avg_revenue'),2)}</td><td>{self._fmt(r.get('avg_days_since_last_purchase'),1)}</td></tr>" for r in by_status)
        dashboard.write_text(f"""<!doctype html><meta charset='utf-8'><style>body{{font-family:Arial;background:#f8fafc;color:#0f172a}}main{{max-width:1100px;margin:auto;padding:28px}}header,.panel{{border-radius:14px;padding:20px;margin-bottom:14px}}header{{background:#0f172a;color:white}}.panel{{background:white;border:1px solid #e2e8f0}}table{{width:100%;border-collapse:collapse}}td,th{{padding:9px;border-bottom:1px solid #e2e8f0}}</style><main><header><h1>GA4 Churn Dashboard</h1><div>Identity: user_id · Active ≤ {pre} gün · Pre-churn {pre+1}-{churn} gün · Churned &gt; {churn} gün</div></header><div class='panel'><h2>Özet</h2><p>Purchasers: {self._fmt(overall.get('purchasers'))} · Active: {self._fmt(overall.get('active_purchasers'))} · Pre-churn: {self._fmt(overall.get('pre_churn_users'))} ({self._pct(overall.get('pre_churn_rate'))}) · Churned: {self._fmt(overall.get('churned_users'))} ({self._pct(overall.get('churn_rate'))})</p></div><div class='panel'><h2>Durum karşılaştırması</h2><table><tr><th>Status</th><th>Users</th><th>Avg purchases</th><th>Avg revenue</th><th>Avg inactive days</th></tr>{rows}</table></div></main>""",encoding="utf-8")
        return {"pre_churn_threshold":pre,"churn_threshold":churn,"overall":overall,"by_status":by_status,"purchase_frequency":frequency,"threshold_sensitivity":sensitivity,"threshold_context":context,"insights":insights,"job_id":job.job_id,"dashboard_path":str(dashboard)}
