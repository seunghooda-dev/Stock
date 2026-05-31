import argparse
import json
import subprocess
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from stock_telegram_bot import (
    BOT_LOG_FILE,
    BOT_STATE_FILE,
    LATEST_RESEARCH_REPORT_FILE,
    NEWS_ALERT_FILE,
    PENDING_TRADE_FILE,
    REALTIME_CANDIDATE_FILE,
    SCHEDULER_LOCK_FILE,
    SCAN_LOCK_FILE,
    REALTIME_LOCK_FILE,
    NEWS_LOCK_FILE,
    TRADING_LOCK_FILE,
)


WORKSPACE = Path(__file__).resolve().parent


@dataclass
class FileStatus:
    path: str
    exists: bool
    updated_at: str = ""
    age_minutes: Optional[float] = None


@dataclass
class BotStatus:
    generated_at: str
    process_running: bool
    process_detail: str
    files: Dict[str, FileStatus]
    jobs: Dict[str, Dict[str, object]] = field(default_factory=dict)
    latest_research: Dict[str, object] = field(default_factory=dict)
    realtime_candidates: Dict[str, object] = field(default_factory=dict)
    pending_trades: Dict[str, object] = field(default_factory=dict)
    news_alerts: Dict[str, object] = field(default_factory=dict)
    locks: List[Dict[str, object]] = field(default_factory=list)
    log_tail: List[str] = field(default_factory=list)


def main() -> None:
    args = parse_args()
    status = build_status(tail_lines=args.tail)
    if args.json:
        print(json.dumps(asdict(status), ensure_ascii=False, indent=2))
    else:
        print_human(status)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Show Stock Bot operational status")
    parser.add_argument("--json", action="store_true", help="JSON 형식으로 출력합니다.")
    parser.add_argument("--tail", type=int, default=12, help="마지막 로그 출력 줄 수. 기본값 12")
    return parser.parse_args()


def build_status(tail_lines: int = 12) -> BotStatus:
    process_running, process_detail = detect_process()
    files = {
        "bot_state": file_status(BOT_STATE_FILE),
        "latest_research": file_status(LATEST_RESEARCH_REPORT_FILE),
        "realtime_candidates": file_status(REALTIME_CANDIDATE_FILE),
        "pending_trades": file_status(PENDING_TRADE_FILE),
        "news_alerts": file_status(NEWS_ALERT_FILE),
        "bot_log": file_status(BOT_LOG_FILE),
    }
    state = read_json(BOT_STATE_FILE)
    latest_research = summarize_research(read_json(LATEST_RESEARCH_REPORT_FILE))
    return BotStatus(
        generated_at=datetime.now().isoformat(timespec="seconds"),
        process_running=process_running,
        process_detail=process_detail,
        files=files,
        jobs=summarize_jobs(state),
        latest_research=latest_research,
        realtime_candidates=summarize_realtime_candidates(read_json(REALTIME_CANDIDATE_FILE)),
        pending_trades=summarize_pending_trades(read_json(PENDING_TRADE_FILE)),
        news_alerts=summarize_news_alerts(read_json(NEWS_ALERT_FILE)),
        locks=summarize_locks(),
        log_tail=tail_file(BOT_LOG_FILE, max(0, tail_lines)),
    )


def print_human(status: BotStatus) -> None:
    print("=== Stock Bot Status ===")
    print(f"Generated : {status.generated_at}")
    print(f"Process   : {'RUNNING' if status.process_running else 'STOPPED'} ({status.process_detail})")
    print()

    print("Jobs")
    if status.jobs:
        for name, job in status.jobs.items():
            detail = job.get("details", {})
            duration = job.get("duration_seconds", "N/A")
            print(
                f"- {name}: {job.get('status', 'unknown')} / "
                f"updated {job.get('updated_at', 'N/A')} / duration {duration}s / {compact_detail(detail)}"
            )
    else:
        print("- 기록 없음")
    print()

    research = status.latest_research
    print("Latest Research")
    if research:
        print(
            f"- generated: {research.get('generated_at', 'N/A')} / "
            f"candidates {research.get('candidate_count', 'N/A')} / "
            f"pool {research.get('research_pool_count', 'N/A')} / "
            f"recommendations {research.get('recommendation_count', 'N/A')}"
        )
        print(f"- score range: {research.get('score_range', 'N/A')}")
        if research.get("pipeline"):
            print(f"- pipeline: {research.get('pipeline')}")
        if research.get("bottlenecks"):
            print(f"- bottlenecks: {research.get('bottlenecks')}")
        for item in research.get("top", []):
            print(
                f"  TOP {item.get('rank')}: {item.get('name')}({item.get('code')}) "
                f"{item.get('score')}점 / {item.get('stage_label')} / {item.get('decision')}"
            )
    else:
        print("- 최신 리서치 파일 없음")
    print()

    realtime = status.realtime_candidates
    print("Realtime Pool")
    print(
        f"- created: {realtime.get('created_at', 'N/A')} / "
        f"candidates {realtime.get('candidate_count', 0)}"
    )
    print()

    pending = status.pending_trades
    print("Pending Trades")
    print(
        f"- created: {pending.get('created_at', 'N/A')} / "
        f"plans {pending.get('plan_count', 0)} / "
        f"dry_run {pending.get('dry_run', 'N/A')}"
    )
    print()

    news = status.news_alerts
    print("News Alerts")
    print(f"- stored alerts {news.get('alert_count', 0)} / latest {news.get('latest_title', 'N/A')}")
    print()

    print("Locks")
    if status.locks:
        for lock in status.locks:
            print(f"- {lock['name']}: {lock['age_minutes']}분 / {lock['path']}")
    else:
        print("- 활성 락 없음")

    if status.log_tail:
        print()
        print("Log Tail")
        for line in status.log_tail:
            print(line)


def detect_process() -> tuple[bool, str]:
    command = (
        "Get-CimInstance Win32_Process | "
        "Where-Object { $_.Name -like 'python*' -and $_.CommandLine -like '*stock_telegram_bot.py*' } | "
        "Select-Object -ExpandProperty ProcessId"
    )
    try:
        result = subprocess.run(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", command],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        pids = [line.strip() for line in result.stdout.splitlines() if line.strip()]
        if pids:
            return True, "pid " + ", ".join(pids)
        return False, "no stock_telegram_bot.py process"
    except Exception as exc:
        return False, f"process check failed: {exc}"


def file_status(path: Path) -> FileStatus:
    full_path = resolve_path(path)
    if not full_path.exists():
        return FileStatus(path=str(path), exists=False)
    mtime = datetime.fromtimestamp(full_path.stat().st_mtime)
    age_minutes = round((datetime.now() - mtime).total_seconds() / 60, 1)
    return FileStatus(path=str(path), exists=True, updated_at=mtime.isoformat(timespec="seconds"), age_minutes=age_minutes)


def read_json(path: Path) -> Dict[str, object]:
    full_path = resolve_path(path)
    if not full_path.exists():
        return {}
    try:
        with full_path.open("r", encoding="utf-8") as file:
            payload = json.load(file)
        return payload if isinstance(payload, dict) else {}
    except Exception:
        return {}


def summarize_jobs(state: Dict[str, object]) -> Dict[str, Dict[str, object]]:
    jobs = state.get("jobs", {}) if isinstance(state, dict) else {}
    return jobs if isinstance(jobs, dict) else {}


def summarize_research(payload: Dict[str, object]) -> Dict[str, object]:
    if not payload:
        return {}
    summary = payload.get("summary", {}) if isinstance(payload.get("summary"), dict) else {}
    pipeline = summary.get("discovery_pipeline", {}) if isinstance(summary.get("discovery_pipeline"), dict) else {}
    top = payload.get("recommendations", []) if isinstance(payload.get("recommendations"), list) else []
    return {
        "generated_at": payload.get("generated_at", ""),
        "job_name": payload.get("job_name", ""),
        "candidate_count": payload.get("candidate_count", summary.get("total_candidates", "N/A")),
        "research_pool_count": summary.get("research_pool_count", "N/A"),
        "recommendation_count": summary.get("recommendation_count", len(top)),
        "score_range": (
            f"highest {summary.get('highest_score', 'N/A')}, "
            f"cutoff {summary.get('cutoff_score', 'N/A')}, "
            f"lowest {summary.get('lowest_score', 'N/A')}"
        ),
        "stage_counts": summary.get("stage_counts", {}),
        "pipeline": summarize_pipeline(pipeline),
        "bottlenecks": summarize_bottlenecks(pipeline),
        "top": [
            {
                "rank": item.get("rank"),
                "code": item.get("code"),
                "name": item.get("name"),
                "score": item.get("score"),
                "stage_label": item.get("stage_label"),
                "decision": item.get("decision"),
            }
            for item in top[:3]
            if isinstance(item, dict)
        ],
    }


def summarize_pipeline(pipeline: Dict[str, object]) -> str:
    if not pipeline:
        return ""
    return (
        f"universe {pipeline.get('universe_count', 0)} -> "
        f"financial {pipeline.get('financial_pass_count', 0)} -> "
        f"final {pipeline.get('final_candidate_count', 0)}"
    )


def summarize_bottlenecks(pipeline: Dict[str, object]) -> str:
    rejections = pipeline.get("rejections", {}) if isinstance(pipeline, dict) else {}
    if not isinstance(rejections, dict) or not rejections:
        return ""
    labels = {
        "technical_failed": "technical",
        "factor_score_failed": "factor",
        "thesis_failed": "thesis",
        "data_quality_failed": "data_quality",
        "smart_money_failed": "smart_money",
        "decision_hold": "decision_hold",
        "market_risk_off": "market",
    }
    top = [
        (labels.get(str(key), str(key)), int(value or 0))
        for key, value in sorted(rejections.items(), key=lambda item: int(item[1] or 0), reverse=True)
        if int(value or 0) > 0
    ][:3]
    return ", ".join(f"{name} {count}" for name, count in top)


def summarize_realtime_candidates(payload: Dict[str, object]) -> Dict[str, object]:
    candidates = payload.get("candidates", []) if isinstance(payload, dict) else []
    return {
        "created_at": payload.get("created_at", "") if isinstance(payload, dict) else "",
        "candidate_count": len(candidates) if isinstance(candidates, list) else 0,
    }


def summarize_pending_trades(payload: Dict[str, object]) -> Dict[str, object]:
    plans = payload.get("plans", []) if isinstance(payload, dict) else []
    return {
        "created_at": payload.get("created_at", "") if isinstance(payload, dict) else "",
        "trading_env": payload.get("trading_env", "") if isinstance(payload, dict) else "",
        "dry_run": payload.get("dry_run", "") if isinstance(payload, dict) else "",
        "plan_count": len(plans) if isinstance(plans, list) else 0,
    }


def summarize_news_alerts(payload: Dict[str, object]) -> Dict[str, object]:
    alerts = payload.get("alerts", []) if isinstance(payload, dict) else []
    latest = alerts[-1] if isinstance(alerts, list) and alerts else {}
    return {
        "alert_count": len(alerts) if isinstance(alerts, list) else 0,
        "latest_title": latest.get("title", "") if isinstance(latest, dict) else "",
        "latest_time": latest.get("published_at", "") if isinstance(latest, dict) else "",
    }


def summarize_locks() -> List[Dict[str, object]]:
    locks = []
    lock_paths = {
        "scheduler": SCHEDULER_LOCK_FILE,
        "research": SCAN_LOCK_FILE,
        "realtime": REALTIME_LOCK_FILE,
        "news": NEWS_LOCK_FILE,
        "trading": TRADING_LOCK_FILE,
    }
    for name, path in lock_paths.items():
        full_path = resolve_path(path)
        if not full_path.exists():
            continue
        mtime = datetime.fromtimestamp(full_path.stat().st_mtime)
        locks.append(
            {
                "name": name,
                "path": str(path),
                "updated_at": mtime.isoformat(timespec="seconds"),
                "age_minutes": round((datetime.now() - mtime).total_seconds() / 60, 1),
            }
        )
    return locks


def tail_file(path: Path, line_count: int) -> List[str]:
    full_path = resolve_path(path)
    if line_count <= 0 or not full_path.exists():
        return []
    try:
        with full_path.open("r", encoding="utf-8", errors="replace") as file:
            lines = file.read().splitlines()
        return lines[-line_count:]
    except Exception as exc:
        return [f"log read failed: {exc}"]


def compact_detail(detail: object) -> str:
    if not isinstance(detail, dict) or not detail:
        return "no detail"
    parts = []
    for key in ["total_candidates", "recommendation_count", "research_pool_count", "signals", "impacts", "orders", "reason"]:
        if key in detail:
            parts.append(f"{key}={detail[key]}")
    return ", ".join(parts) if parts else "detail saved"


def resolve_path(path: Path) -> Path:
    return path if path.is_absolute() else WORKSPACE / path


if __name__ == "__main__":
    main()
