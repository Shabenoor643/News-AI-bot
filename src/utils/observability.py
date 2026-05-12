import asyncio
import os
import time
from dataclasses import dataclass, field
from datetime import datetime
from threading import Lock

import pandas as pd
from openpyxl import load_workbook

from src.config.config import CONFIG
from src.utils.logger import create_logger

try:
    import mlflow
except Exception:
    mlflow = None


logger = create_logger("observability")

LOG_COLUMNS = [
    "timestamp",
    "agent_name",
    "action",
    "input_summary",
    "output_summary",
    "tokens_used",
    "cost",
    "status",
]

_FILE_LOCK = Lock()


def clip_summary(value: str) -> str:
    text = str(value or "").strip()
    if len(text) <= CONFIG.Observability.summary_max_chars:
        return text
    return text[: CONFIG.Observability.summary_max_chars - 3].rstrip() + "..."


def estimate_text_cost_inr(prompt_tokens: int, completion_tokens: int) -> float:
    input_cost = (
        prompt_tokens / 1_000_000
    ) * CONFIG.Observability.text_input_cost_usd_per_million
    output_cost = (
        completion_tokens / 1_000_000
    ) * CONFIG.Observability.text_output_cost_usd_per_million
    return round((input_cost + output_cost) * CONFIG.Observability.usd_to_inr, 4)


def estimate_image_cost_inr(image_count: int) -> float:
    return round(
        image_count * CONFIG.Observability.image_cost_usd * CONFIG.Observability.usd_to_inr,
        4,
    )


def _ensure_excel_file() -> None:
    path = CONFIG.Paths.excel_log_path
    if os.path.exists(path):
        return
    directory = os.path.dirname(path)
    if directory:
        os.makedirs(directory, exist_ok=True)
    pd.DataFrame(columns=LOG_COLUMNS).to_excel(path, index=False, engine="openpyxl")


def _append_excel_row(row: dict) -> None:
    with _FILE_LOCK:
        _ensure_excel_file()
        workbook = load_workbook(CONFIG.Paths.excel_log_path)
        worksheet = workbook.active
        worksheet.append([row.get(column, "") for column in LOG_COLUMNS])
        workbook.save(CONFIG.Paths.excel_log_path)
        workbook.close()


def _log_mlflow(row: dict, extra_params: dict | None = None) -> None:
    if not CONFIG.Observability.mlflow_enabled or mlflow is None:
        return

    try:
        mlflow.set_tracking_uri(CONFIG.Observability.tracking_uri)
        mlflow.set_experiment(CONFIG.Observability.experiment_name)
        execution_time = float(extra_params.get("execution_time", 0) if extra_params else 0)
        with mlflow.start_run(
            run_name=f"{row.get('agent_name')}-{row.get('action')}",
            nested=mlflow.active_run() is not None,
        ):
            mlflow.log_param("agent_name", row.get("agent_name", "unknown"))
            mlflow.log_param("action", row.get("action", "unknown"))
            mlflow.log_param("status", row.get("status", "unknown"))
            if extra_params:
                for key, value in extra_params.items():
                    if value is None:
                        continue
                    mlflow.log_param(key, clip_summary(value))
            mlflow.log_metric("tokens_used", float(row.get("tokens_used", 0) or 0))
            mlflow.log_metric("cost_inr", float(row.get("cost", 0) or 0))
            mlflow.log_metric("execution_time", execution_time)
    except Exception as error:
        logger.warning("MLflow logging skipped", extra={"error": str(error)})


def _record_sync(row: dict, extra_params: dict | None = None) -> None:
    normalized = {
        "timestamp": row.get("timestamp") or datetime.utcnow().isoformat(),
        "agent_name": row.get("agent_name") or "unknown",
        "action": row.get("action") or "unknown",
        "input_summary": clip_summary(row.get("input_summary", "")),
        "output_summary": clip_summary(row.get("output_summary", "")),
        "tokens_used": int(row.get("tokens_used", 0) or 0),
        "cost": float(row.get("cost", 0) or 0),
        "status": row.get("status") or "unknown",
    }
    _append_excel_row(normalized)
    _log_mlflow(normalized, extra_params=extra_params)


async def record_agent_run(row: dict, extra_params: dict | None = None) -> None:
    await asyncio.to_thread(_record_sync, row, extra_params)


def count_logged_actions(agent_name: str, action: str, day: str) -> int:
    path = CONFIG.Paths.excel_log_path
    if not os.path.exists(path):
        return 0
    try:
        dataframe = pd.read_excel(path, engine="openpyxl")
    except Exception as error:
        logger.warning("Failed to read Excel log", extra={"error": str(error)})
        return 0

    if dataframe.empty:
        return 0
    required_columns = {"timestamp", "agent_name", "action", "status"}
    if not required_columns.issubset(set(dataframe.columns)):
        return 0

    timestamp_series = dataframe["timestamp"].astype(str).fillna("")
    mask = (
        dataframe["agent_name"].astype(str).eq(agent_name)
        & dataframe["action"].astype(str).eq(action)
        & dataframe["status"].astype(str).eq("success")
        & timestamp_series.str.startswith(day)
    )
    return int(mask.sum())


@dataclass
class AgentTrace:
    agent_name: str
    action: str
    input_summary: str = ""
    output_summary: str = ""
    status: str = "success"
    tokens_used: int = 0
    cost_inr: float = 0.0
    started_at: float = field(default_factory=time.perf_counter)
    extra_params: dict = field(default_factory=dict)

    def add_usage(self, usage) -> None:
        if usage is None:
            return
        self.tokens_used += int(getattr(usage, "total_tokens", 0) or 0)
        self.cost_inr += float(getattr(usage, "cost_inr", 0.0) or 0.0)

    def fail(self, error: Exception | str) -> None:
        self.status = "failed"
        self.output_summary = clip_summary(error)

    async def flush(self) -> None:
        execution_time = round(time.perf_counter() - self.started_at, 4)
        extra = {**self.extra_params, "execution_time": execution_time}
        await record_agent_run(
            {
                "agent_name": self.agent_name,
                "action": self.action,
                "input_summary": self.input_summary,
                "output_summary": self.output_summary,
                "tokens_used": self.tokens_used,
                "cost": round(self.cost_inr, 4),
                "status": self.status,
            },
            extra_params=extra,
        )
