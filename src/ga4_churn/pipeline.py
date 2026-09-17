from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from importlib import resources
import re

from google.cloud import bigquery


_IDENTIFIER_PROJECT = re.compile(r"^[a-z][a-z0-9\-:.]{4,62}[a-z0-9]$")
_IDENTIFIER_DATASET = re.compile(r"^[A-Za-z0-9_]+$")


@dataclass(frozen=True)
class SQLStep:
    number: int
    filename: str
    name: str
    output_table: str
    is_result: bool
    cost_check: bool
    sql: str


class GA4Analysis:
    """Thin notebook-facing orchestration layer.

    The Python engine stays generic. Analysis logic lives in packaged SQL files.
    To turn this demo into the churn version later, replace the SQL files under
    ga4_churn/sql/ while preserving their metadata headers.
    """

    def __init__(
        self,
        project_id: str,
        dataset_id: str,
        output_dataset: str,
        start_date: str,
        end_date: str,
        billing_project_id: str | None = None,
    ):
        self.project_id = project_id.strip()
        self.dataset_id = dataset_id.strip()
        self.output_dataset = output_dataset.strip()
        self.start_date = str(start_date)
        self.end_date = str(end_date)
        self.billing_project_id = (billing_project_id or project_id).strip()

        self._validate_inputs()
        self.client = bigquery.Client(project=self.billing_project_id)
        self.steps = self._load_steps()

    def _validate_inputs(self) -> None:
        if not _IDENTIFIER_PROJECT.match(self.project_id):
            raise ValueError("Invalid GCP project_id.")
        if not _IDENTIFIER_PROJECT.match(self.billing_project_id):
            raise ValueError("Invalid billing_project_id.")
        if not _IDENTIFIER_DATASET.match(self.dataset_id):
            raise ValueError("Invalid GA4 dataset_id.")
        if not _IDENTIFIER_DATASET.match(self.output_dataset):
            raise ValueError("Invalid output_dataset.")
        if date.fromisoformat(self.start_date) > date.fromisoformat(self.end_date):
            raise ValueError("start_date must be <= end_date.")

    @staticmethod
    def _header_value(sql: str, key: str) -> str | None:
        m = re.search(rf"(?mi)^\s*--\s*{re.escape(key)}\s*:\s*(.+?)\s*$", sql)
        return m.group(1).strip() if m else None

    def _load_steps(self) -> list[SQLStep]:
        sql_root = resources.files("ga4_churn").joinpath("sql")
        files = sorted(
            [p for p in sql_root.iterdir() if p.name.endswith(".sql")],
            key=lambda p: p.name,
        )
        steps: list[SQLStep] = []
        for i, path in enumerate(files, start=1):
            sql = path.read_text(encoding="utf-8")
            name = self._header_value(sql, "name") or path.name
            output_table = self._header_value(sql, "output_table")
            if not output_table:
                raise ValueError(f"{path.name} is missing -- output_table:")
            is_result = (self._header_value(sql, "result") or "false").lower() == "true"
            cost_check = (self._header_value(sql, "cost_check") or "true").lower() == "true"
            steps.append(
                SQLStep(
                    number=i,
                    filename=path.name,
                    name=name,
                    output_table=output_table,
                    is_result=is_result,
                    cost_check=cost_check,
                    sql=sql,
                )
            )
        if not steps:
            raise RuntimeError("No SQL steps found in package.")
        return steps

    def _ensure_output_dataset(self) -> None:
        source = self.client.get_dataset(f"{self.project_id}.{self.dataset_id}")
        output_ref = bigquery.Dataset(f"{self.project_id}.{self.output_dataset}")
        output_ref.location = source.location
        self.client.create_dataset(output_ref, exists_ok=True)

    def _render_sql(self, sql: str) -> str:
        replacements = {
            "{{PROJECT_ID}}": self.project_id,
            "{{DATASET_ID}}": self.dataset_id,
            "{{OUTPUT_DATASET}}": self.output_dataset,
        }
        for key, value in replacements.items():
            sql = sql.replace(key, value)
        return sql

    @property
    def _query_parameters(self):
        return [
            bigquery.ScalarQueryParameter(
                "start_suffix", "STRING", self.start_date.replace("-", "")
            ),
            bigquery.ScalarQueryParameter(
                "end_suffix", "STRING", self.end_date.replace("-", "")
            ),
        ]

    def validate(self) -> dict:
        self.client.get_dataset(f"{self.project_id}.{self.dataset_id}")
        return {
            "status": "ok",
            "source": f"{self.project_id}.{self.dataset_id}.events_*",
            "billing_project": self.billing_project_id,
            "date_range": f"{self.start_date} → {self.end_date}",
            "steps": len(self.steps),
        }

    def dry_run(self) -> dict:
        self._ensure_output_dataset()
        total_bytes = 0
        details = []
        for step in self.steps:
            if not step.cost_check:
                details.append({"step": step.number, "name": step.name, "bytes": 0, "skipped": True})
                continue
            sql = self._render_sql(step.sql)
            job_config = bigquery.QueryJobConfig(
                dry_run=True,
                use_query_cache=False,
                query_parameters=self._query_parameters,
            )
            job = self.client.query(sql, job_config=job_config)
            processed = int(job.total_bytes_processed or 0)
            total_bytes += processed
            details.append(
                {
                    "step": step.number,
                    "name": step.name,
                    "bytes": processed,
                }
            )
        return {
            "total_bytes": total_bytes,
            "total_gb": round(total_bytes / (1024**3), 3),
            "steps": details,
        }

    def run_step(self, step_number: int) -> dict:
        self._ensure_output_dataset()
        try:
            step = next(s for s in self.steps if s.number == step_number)
        except StopIteration as exc:
            raise ValueError(f"Unknown step number: {step_number}") from exc

        sql = self._render_sql(step.sql)
        job_config = bigquery.QueryJobConfig(
            query_parameters=self._query_parameters
        )
        job = self.client.query(sql, job_config=job_config)
        job.result()

        result = {
            "step": step.number,
            "name": step.name,
            "status": "completed",
            "job_id": job.job_id,
            "output_table": (
                f"{self.project_id}.{self.output_dataset}.{step.output_table}"
            ),
        }
        self._display_step(result)
        if step.is_result:
            self._display_result_table()
        return result

    def run_all(self) -> list[dict]:
        self._display_title("GA4 PIPELINE")
        results = [self.run_step(step.number) for step in self.steps]
        return results

    def result_rows(self, limit: int = 20) -> list[dict]:
        result_steps = [s for s in self.steps if s.is_result]
        step = result_steps[-1] if result_steps else self.steps[-1]
        table = f"`{self.project_id}.{self.output_dataset}.{step.output_table}`"
        rows = self.client.query(
            f"SELECT * FROM {table} LIMIT {int(limit)}"
        ).result()
        return [dict(row.items()) for row in rows]

    def _display_result_table(self) -> None:
        rows = self.result_rows(limit=20)
        if not rows:
            print("No result rows.")
            return

        try:
            from IPython.display import HTML, display
        except ImportError:
            print(rows)
            return

        columns = list(rows[0].keys())
        head = "".join(f"<th>{c}</th>" for c in columns)
        body = "".join(
            "<tr>" + "".join(f"<td>{row.get(c, '')}</td>" for c in columns) + "</tr>"
            for row in rows
        )
        html = f"""
        <div style="font-family:Arial,sans-serif;margin:12px 0 22px">
          <div style="font-size:18px;font-weight:700;margin-bottom:10px">Result</div>
          <table style="border-collapse:collapse;width:100%;max-width:920px">
            <thead><tr>{head}</tr></thead>
            <tbody>{body}</tbody>
          </table>
          <style>
            th,td{{padding:9px 12px;border-bottom:1px solid #e5e7eb;text-align:left}}
            th{{background:#f8fafc;font-weight:600}}
          </style>
        </div>
        """
        display(HTML(html))

    @staticmethod
    def _display_title(text: str) -> None:
        try:
            from IPython.display import HTML, display
        except ImportError:
            print(text)
            return
        display(
            HTML(
                f"<div style='font-family:Arial,sans-serif;font-size:22px;"
                f"font-weight:700;margin:8px 0 14px'>{text}</div>"
            )
        )

    @staticmethod
    def _display_step(result: dict) -> None:
        try:
            from IPython.display import HTML, display
        except ImportError:
            print(result)
            return

        display(
            HTML(
                f"""
                <div style="font-family:Arial,sans-serif;border:1px solid #e5e7eb;
                            border-radius:10px;padding:12px 14px;margin:7px 0;
                            max-width:920px">
                  <div style="font-weight:700">
                    ✓ Step {result['step']} — {result['name']}
                  </div>
                  <div style="font-size:12px;color:#64748b;margin-top:5px">
                    {result['output_table']}
                  </div>
                </div>
                """
            )
        )
