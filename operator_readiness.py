import argparse
import importlib.util
import json
import os
import platform
import sys
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional

import FinanceDataReader as fdr
import requests
from dotenv import load_dotenv

from stock_telegram_bot import (
    AUTO_TRADE_CONFIRM_REAL_TRADING,
    AUTO_TRADE_DRY_RUN,
    AUTO_TRADE_ENABLED,
    AUTO_TRADE_MAX_ORDER_VALUE_KRW,
    AUTO_TRADE_MAX_PORTFOLIO_EXPOSURE_KRW,
    AUTO_TRADE_ORDER_BUDGET_KRW,
    AUTO_TRADE_RISK_PER_TRADE_KRW,
    CACHE_DIR,
    BOT_STATE_FILE,
    DataQualityValidator,
    DecisionPolicy,
    KISDataProvider,
    Notifier,
    active_strategy_profile,
    data_quality_min_score,
    env_bool,
    env_float,
    env_int,
    factor_score_minimum,
    format_market_cap,
    investment_thesis_minimum,
    mask_account,
    normalize_trading_env,
    radar_data_quality_min_score,
    radar_enabled,
    radar_factor_score_minimum,
    radar_investment_thesis_minimum,
    telegram_recommendation_limit,
    watchlist_data_quality_min_score,
    watchlist_enabled,
    watchlist_factor_score_minimum,
    watchlist_investment_thesis_minimum,
)


WORKSPACE = Path(__file__).resolve().parent
ENV_FILE = WORKSPACE / ".env"
GITIGNORE_FILE = WORKSPACE / ".gitignore"
README_FILE = WORKSPACE / "README.md"
LOCAL_CACHE_DIR = CACHE_DIR if CACHE_DIR.is_absolute() else WORKSPACE / CACHE_DIR
BACKTEST_SUMMARY_FILE = LOCAL_CACHE_DIR / "backtest_summary.json"
LOCAL_BOT_STATE_FILE = BOT_STATE_FILE if BOT_STATE_FILE.is_absolute() else WORKSPACE / BOT_STATE_FILE

STATUS_PASS = "PASS"
STATUS_WARN = "WARN"
STATUS_BLOCK = "BLOCK"


@dataclass
class CheckResult:
    category: str
    name: str
    status: str
    detail: str
    action: str = ""


@dataclass
class ReadinessReport:
    generated_at: str
    target: str
    mode: str
    score: int
    summary: str
    risk_policy: Dict[str, object]
    checks: List[CheckResult] = field(default_factory=list)
    next_actions: List[str] = field(default_factory=list)


class OperatorReadinessAuditor:
    def __init__(self, target: str, network: bool, send_telegram_test: bool) -> None:
        load_dotenv(ENV_FILE)
        self.target = target
        self.network = network
        self.send_telegram_test = send_telegram_test
        self.checks: List[CheckResult] = []
        self.next_actions: List[str] = []

    def run(self) -> ReadinessReport:
        self._check_runtime()
        self._check_local_files()
        self._check_environment()
        self._check_strategy_policy()
        self._check_news_policy()
        self._check_telegram()
        self._check_kis()
        self._check_market_data()
        self._check_backtest_artifacts()
        self._check_bot_state()
        self._check_operating_scripts()

        blocks = sum(1 for check in self.checks if check.status == STATUS_BLOCK)
        warnings = sum(1 for check in self.checks if check.status == STATUS_WARN)
        score = max(0, min(100, 100 - blocks * 25 - warnings * 5))
        mode = self._mode(blocks)
        summary = self._summary(mode, blocks, warnings)
        return ReadinessReport(
            generated_at=datetime.now().isoformat(timespec="seconds"),
            target=self.target,
            mode=mode,
            score=score,
            summary=summary,
            risk_policy=self._risk_policy(),
            checks=self.checks,
            next_actions=self.next_actions[:10],
        )

    def _check_runtime(self) -> None:
        version = sys.version_info
        if version >= (3, 10):
            self._pass("Runtime", "Python", f"{platform.python_version()} ({platform.system()})")
        else:
            self._block("Runtime", "Python", f"{platform.python_version()}은 낮습니다.", "Python 3.10 이상을 설치하세요.")

        required_modules = {
            "FinanceDataReader": "FinanceDataReader",
            "html5lib": "html5lib",
            "pandas": "pandas",
            "pykrx": "pykrx",
            "python-dotenv": "dotenv",
            "ta": "ta",
            "requests": "requests",
            "schedule": "schedule",
            "yfinance": "yfinance",
        }
        missing = [name for name, module in required_modules.items() if importlib.util.find_spec(module) is None]
        if missing:
            self._block(
                "Runtime",
                "Dependencies",
                "누락: " + ", ".join(missing),
                r".\.venv\Scripts\python.exe -m pip install -r requirements.txt",
            )
        else:
            self._pass("Runtime", "Dependencies", "필수 패키지 import 가능")

    def _check_local_files(self) -> None:
        required_files = [
            "stock_telegram_bot.py",
            "backtest_stock_bot.py",
            "validate_data_sources.py",
            "test_kis_connection.py",
            "status_stock_bot.py",
            "requirements.txt",
            "README.md",
        ]
        missing = [name for name in required_files if not (WORKSPACE / name).exists()]
        if missing:
            self._block("Files", "Project files", "누락: " + ", ".join(missing), "GitHub 저장소를 다시 pull/clone 하세요.")
        else:
            self._pass("Files", "Project files", "핵심 실행 파일 확인")

        if ENV_FILE.exists():
            self._pass("Files", ".env", ".env 존재. 실제 비밀값은 출력하지 않습니다.")
        else:
            self._block("Files", ".env", ".env가 없습니다.", "Copy-Item .env.example .env 후 값을 채우세요.")

        ignored = self._gitignore_patterns()
        missing_ignores = [pattern for pattern in [".env", ".env.*", "cache/", "logs/"] if pattern not in ignored]
        if missing_ignores:
            self._block(
                "Security",
                ".gitignore",
                "민감/로컬 파일 차단 누락: " + ", ".join(missing_ignores),
                ".gitignore에 .env, .env.*, cache/, logs/를 추가하세요.",
            )
        else:
            self._pass("Security", ".gitignore", ".env/cache/logs Git 제외 확인")

    def _check_environment(self) -> None:
        profile = active_strategy_profile()
        self._pass("Config", "Strategy profile", profile)

        if self.target == "live-trading" and profile == "aggressive":
            self._warn(
                "Config",
                "Strategy profile",
                "실전 자동매매 목표에서 aggressive 프로파일은 과감합니다.",
                "실전 전환 전 conservative 또는 institutional을 권장합니다.",
            )

        auto_enabled = env_bool("AUTO_TRADE_ENABLED", AUTO_TRADE_ENABLED)
        dry_run = env_bool("AUTO_TRADE_DRY_RUN", AUTO_TRADE_DRY_RUN)
        trading_env = normalize_trading_env(os.getenv("KIS_TRADING_ENV", "real"))
        confirm = os.getenv("AUTO_TRADE_CONFIRM_REAL_TRADING", AUTO_TRADE_CONFIRM_REAL_TRADING).strip()

        if self.target == "alert":
            self._pass("Config", "Target mode", "알림/리서치 모드")
        elif self.target == "demo-trading":
            self._pass("Config", "Target mode", "모의 자동매매 검증 모드")
            if trading_env != "demo":
                self._block("Config", "Demo trading", "KIS_TRADING_ENV가 demo가 아닙니다.", "모의연습은 KIS_TRADING_ENV=demo가 필요합니다.")
            if not auto_enabled:
                self._block("Config", "Auto trade", "AUTO_TRADE_ENABLED=false", "모의 주문까지 검증하려면 true로 바꾸세요.")
            if not dry_run:
                self._warn("Config", "Dry run", "AUTO_TRADE_DRY_RUN=false", "모의 계좌 주문 전송 단계입니다. dry-run 로그 검증 후 사용하세요.")
        elif self.target == "live-trading":
            self._pass("Config", "Target mode", "실전 자동매매 전환 검증 모드")
            if trading_env != "real":
                self._block("Config", "Live trading", "KIS_TRADING_ENV가 real이 아닙니다.", "실전은 KIS_TRADING_ENV=real이 필요합니다.")
            if not auto_enabled:
                self._block("Config", "Live trading", "AUTO_TRADE_ENABLED=false", "실전 자동매매 의도가 확실할 때만 true로 바꾸세요.")
            if dry_run:
                self._block("Config", "Live trading", "AUTO_TRADE_DRY_RUN=true", "실전 주문 전송은 false가 필요합니다.")
            if confirm != "YES":
                self._block("Config", "Live trading", "실전 주문 확인값이 없습니다.", "AUTO_TRADE_CONFIRM_REAL_TRADING=YES를 명시해야 합니다.")

    def _check_strategy_policy(self) -> None:
        policy = DecisionPolicy()
        self._pass(
            "Policy",
            "Alert gate",
            (
                f"최소점수 {factor_score_minimum():.1f}, "
                f"투자 가설 {investment_thesis_minimum():.1f}, "
                f"최소 데이터 신뢰도 {data_quality_min_score():.1f}"
            ),
        )
        self._pass(
            "Policy",
            "Recommendation limit",
            f"전체 리서치 후 텔레그램 상위 {telegram_recommendation_limit()}개만 표시",
        )
        if watchlist_enabled():
            self._pass(
                "Policy",
                "Watchlist gate",
                (
                    f"관찰 점수 {watchlist_factor_score_minimum():.1f}, "
                    f"관찰 가설 {watchlist_investment_thesis_minimum():.1f}, "
                    f"관찰 DQ {watchlist_data_quality_min_score():.1f}"
                ),
            )
        else:
            self._warn(
                "Policy",
                "Watchlist gate",
                "관찰 후보 발굴이 비활성화되어 있습니다.",
                "후보 부족 시 WATCHLIST_ENABLED=true를 권장합니다.",
            )
        if radar_enabled():
            self._pass(
                "Policy",
                "Research radar",
                (
                    f"레이더 점수 {radar_factor_score_minimum():.1f}, "
                    f"레이더 가설 {radar_investment_thesis_minimum():.1f}, "
                    f"레이더 DQ {radar_data_quality_min_score():.1f}"
                ),
            )
        else:
            self._warn(
                "Policy",
                "Research radar",
                "리서치 레이더 후보가 비활성화되어 있습니다.",
                "후보가 0개로 자주 끝나면 RADAR_ENABLED=true를 권장합니다.",
            )
        self._pass(
            "Policy",
            "Trade gate",
            (
                f"자동매매 점수 {policy.trade_ready_score:.1f}, DQ {policy.auto_min_data_quality:.1f}, "
                f"손절폭 {policy.max_stop_loss_pct:.1f}%"
            ),
        )
        self._pass(
            "Policy",
            "Sub-score gate",
            (
                f"재무 {policy.min_financial_score:.1f}, 수급 {policy.min_accumulation_score:.1f}, "
                f"기술 {policy.min_technical_score:.1f}, 리스크 {policy.min_risk_score:.1f}"
            ),
        )

        risk_per_trade = env_float("AUTO_TRADE_RISK_PER_TRADE_KRW", AUTO_TRADE_RISK_PER_TRADE_KRW)
        order_budget = env_float("AUTO_TRADE_ORDER_BUDGET_KRW", AUTO_TRADE_ORDER_BUDGET_KRW)
        max_order_value = env_float("AUTO_TRADE_MAX_ORDER_VALUE_KRW", AUTO_TRADE_MAX_ORDER_VALUE_KRW)
        max_exposure = env_float("AUTO_TRADE_MAX_PORTFOLIO_EXPOSURE_KRW", AUTO_TRADE_MAX_PORTFOLIO_EXPOSURE_KRW)
        if risk_per_trade <= 0:
            self._block("Policy", "Risk sizing", "종목당 위험한도가 0 이하입니다.", "AUTO_TRADE_RISK_PER_TRADE_KRW를 양수로 설정하세요.")
        elif risk_per_trade > order_budget * 0.35:
            self._warn(
                "Policy",
                "Risk sizing",
                f"종목당 위험 {risk_per_trade:,.0f}원이 주문예산 대비 큽니다.",
                "초기 운영은 주문예산의 10~20% 이하 위험을 권장합니다.",
            )
        else:
            self._pass("Policy", "Risk sizing", f"종목당 위험한도 {risk_per_trade:,.0f}원")

        if max_order_value > max_exposure:
            self._warn(
                "Policy",
                "Exposure",
                "종목당 최대 주문금액이 총 노출 한도보다 큽니다.",
                "AUTO_TRADE_MAX_ORDER_VALUE_KRW <= AUTO_TRADE_MAX_PORTFOLIO_EXPOSURE_KRW로 맞추세요.",
            )
        else:
            self._pass("Policy", "Exposure", f"종목당 {max_order_value:,.0f}원, 총 {max_exposure:,.0f}원")

    def _check_news_policy(self) -> None:
        enabled = env_bool("NEWS_ALERT_ENABLED", True)
        interval = env_int("NEWS_SCAN_INTERVAL_SECONDS", 300)
        block_auto_trade = env_bool("NEWS_BLOCK_AUTO_TRADE_ON_RISK", True)
        if not enabled:
            self._warn("News", "News radar", "뉴스 속보 감시가 비활성화되어 있습니다.", "NEWS_ALERT_ENABLED=true를 권장합니다.")
            return
        if interval > 600:
            self._warn("News", "News latency", f"뉴스 확인 간격 {interval}초", "속보 반영을 위해 300초 이하를 권장합니다.")
        else:
            self._pass("News", "News latency", f"{interval}초 간격")
        if block_auto_trade:
            self._pass("News", "Trade guard", "악재 뉴스 감지 시 자동매매 주문 차단")
        else:
            self._warn("News", "Trade guard", "뉴스 악재 주문 차단이 꺼져 있습니다.", "NEWS_BLOCK_AUTO_TRADE_ON_RISK=true를 권장합니다.")

    def _check_telegram(self) -> None:
        token = os.getenv("TELEGRAM_TOKEN", "").strip()
        chat_id = os.getenv("TELEGRAM_CHAT_ID", "").strip()
        if not token or not chat_id:
            self._block("Telegram", "Credentials", "텔레그램 토큰 또는 채팅 ID가 비어 있습니다.", "BotFather 토큰과 본인 chat_id를 .env에 넣으세요.")
            return

        self._pass("Telegram", "Credentials", "토큰/채팅 ID 설정됨")
        if not self.network:
            self._warn("Telegram", "Network", "네트워크 확인 생략", "--no-network 없이 다시 실행하면 API 연결을 확인합니다.")
            return

        try:
            response = requests.get(f"https://api.telegram.org/bot{token}/getMe", timeout=12)
            response.raise_for_status()
            payload = response.json()
            if payload.get("ok"):
                username = (payload.get("result") or {}).get("username", "unknown")
                self._pass("Telegram", "Bot API", f"봇 확인: @{username}")
            else:
                self._block("Telegram", "Bot API", "getMe 응답이 ok=false입니다.", "텔레그램 토큰을 다시 확인하세요.")
        except requests.RequestException as exc:
            self._block("Telegram", "Bot API", f"연결 실패: {exc}", "네트워크 또는 TELEGRAM_TOKEN을 확인하세요.")

        if self.send_telegram_test:
            message = (
                "✅ Stock Bot readiness check\n"
                f"시간: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
                "민감정보는 포함하지 않았습니다."
            )
            sent = Notifier(token=token, chat_id=chat_id).send(message)
            if sent:
                self._pass("Telegram", "Test message", "테스트 메시지 전송 성공")
            else:
                self._block("Telegram", "Test message", "테스트 메시지 전송 실패", "TELEGRAM_CHAT_ID를 확인하세요.")

    def _check_kis(self) -> None:
        provider = KISDataProvider()
        if not provider.enabled:
            status = STATUS_WARN if self.target == "alert" else STATUS_BLOCK
            self._add(
                status,
                "KIS",
                "Credentials",
                "KIS_APP_KEY/KIS_APP_SECRET 미설정",
                "한국투자증권 API 값을 .env에 넣으세요.",
            )
            return

        account = mask_account(provider.account_no, provider.account_product_code)
        detail = f"{provider.trading_env}, 계좌 {account}, trading_ready={provider.trading_ready}"
        if self.target in {"demo-trading", "live-trading"} and not provider.trading_ready:
            self._block("KIS", "Account", detail, "KIS_ACCOUNT_NO와 KIS_ACCOUNT_PRODUCT_CODE를 확인하세요.")
        else:
            self._pass("KIS", "Account", detail)

        if not self.network:
            self._warn("KIS", "Network", "네트워크 확인 생략", "--no-network 없이 다시 실행하면 현재가 조회를 확인합니다.")
            return

        try:
            quote = provider.fetch_current_price("005930")
            price = quote.get("current_price")
            trading_value = quote.get("trading_value")
            self._pass(
                "KIS",
                "Current price",
                f"삼성전자 현재가 {price:,.0f}원, 거래대금 {format_market_cap(trading_value)}",
            )
        except Exception as exc:
            status = STATUS_WARN if self.target == "alert" else STATUS_BLOCK
            self._add(status, "KIS", "Current price", f"조회 실패: {exc}", "KIS API 키/도메인/모의투자 환경을 확인하세요.")

    def _check_market_data(self) -> None:
        if not self.network:
            self._warn("Data", "Market data", "네트워크 확인 생략", "실전 운영 전 네트워크 점검을 실행하세요.")
            return

        try:
            listing = fdr.StockListing("KRX")
            count = int(len(listing))
            if count >= 2000:
                self._pass("Data", "KRX universe", f"{count:,}개 종목 로드")
            else:
                self._warn("Data", "KRX universe", f"{count:,}개 종목만 로드", "FinanceDataReader/KRX 응답을 확인하세요.")
        except Exception as exc:
            self._block("Data", "KRX universe", f"로드 실패: {exc}", "네트워크와 FinanceDataReader를 확인하세요.")

        try:
            start_date = (datetime.now() - timedelta(days=180)).strftime("%Y-%m-%d")
            frame = fdr.DataReader("005930", start_date)
            quality = DataQualityValidator.validate_price_frame(frame, "FDR 일봉", min_rows=30)
            if quality.passed:
                self._pass("Data", "FDR daily price", f"{quality.score:.1f}/100({quality.grade})")
            else:
                self._block(
                    "Data",
                    "FDR daily price",
                    f"{quality.score:.1f}/100({quality.grade})",
                    "; ".join(quality.warnings[:3]),
                )
        except Exception as exc:
            self._block("Data", "FDR daily price", f"조회 실패: {exc}", "FinanceDataReader 연결을 확인하세요.")

    def _check_backtest_artifacts(self) -> None:
        if not BACKTEST_SUMMARY_FILE.exists():
            self._warn(
                "Validation",
                "Backtest",
                "최근 백테스트 결과 파일이 없습니다.",
                r".\.venv\Scripts\python.exe backtest_stock_bot.py --years 3 --max-stocks 200",
            )
            return

        try:
            with BACKTEST_SUMMARY_FILE.open("r", encoding="utf-8") as file:
                summary = json.load(file)
            trades = int(summary.get("trades", 0))
            win_rate = summary.get("win_rate_pct", "N/A")
            avg_return = summary.get("avg_return_pct", "N/A")
            if trades < 20:
                self._warn(
                    "Validation",
                    "Backtest",
                    f"표본 {trades}건, 승률 {win_rate}%, 평균 {avg_return}%",
                    "실전 전환 전 더 긴 기간과 더 많은 종목으로 재검증하세요.",
                )
            else:
                self._pass("Validation", "Backtest", f"표본 {trades}건, 승률 {win_rate}%, 평균 {avg_return}%")
        except Exception as exc:
            self._warn("Validation", "Backtest", f"결과 파일 읽기 실패: {exc}", "백테스트를 다시 실행하세요.")

    def _check_bot_state(self) -> None:
        if not LOCAL_BOT_STATE_FILE.exists():
            self._warn(
                "Operations",
                "Bot state",
                "운영 상태 파일이 아직 없습니다.",
                "봇을 1회 실행하면 cache/bot_state.json에 최근 작업 상태가 기록됩니다.",
            )
            return

        try:
            with LOCAL_BOT_STATE_FILE.open("r", encoding="utf-8") as file:
                state = json.load(file)
            jobs = state.get("jobs", {}) if isinstance(state, dict) else {}
            daily = jobs.get("daily_research", {}) if isinstance(jobs, dict) else {}
            status = str(daily.get("status", "unknown"))
            updated_at_text = str(daily.get("updated_at") or daily.get("finished_at") or "")
            if not updated_at_text:
                self._warn("Operations", "Bot state", f"최근 리서치 상태 {status}, 갱신시간 없음", "봇을 다시 실행해 상태 파일을 갱신하세요.")
                return

            updated_at = datetime.fromisoformat(updated_at_text)
            age_hours = (datetime.now() - updated_at).total_seconds() / 3600
            details = daily.get("details", {}) if isinstance(daily.get("details"), dict) else {}
            recommendation_count = details.get("recommendation_count", "N/A")
            total_candidates = details.get("total_candidates", "N/A")
            if status == "failed":
                self._warn(
                    "Operations",
                    "Bot state",
                    f"마지막 리서치 실패: {details.get('error', '원인 미기록')}",
                    "logs/bot.log와 cache/bot_state.json을 확인하세요.",
                )
            elif status == "running" and age_hours > 3:
                self._warn(
                    "Operations",
                    "Bot state",
                    f"리서치가 {age_hours:.1f}시간째 running 상태입니다.",
                    "중복 실행 락이 남아 있으면 stop_stock_bot.bat 실행 후 다시 시작하세요.",
                )
            elif age_hours > 36:
                self._warn(
                    "Operations",
                    "Bot state",
                    f"마지막 리서치 갱신 {age_hours:.1f}시간 전",
                    "상시 운영 PC가 켜져 있는지, 작업 스케줄러가 동작하는지 확인하세요.",
                )
            else:
                self._pass(
                    "Operations",
                    "Bot state",
                    f"최근 리서치 {status}, 후보 {total_candidates}개, 전송 {recommendation_count}개, {age_hours:.1f}시간 전",
                )
        except Exception as exc:
            self._warn("Operations", "Bot state", f"상태 파일 읽기 실패: {exc}", "cache/bot_state.json을 삭제 후 봇을 다시 실행하세요.")

    def _check_operating_scripts(self) -> None:
        scripts = [
            "setup_windows_pc.bat",
            "run_stock_bot.bat",
            "run_stock_bot_headless.bat",
            "stop_stock_bot.bat",
            "install_startup_task.bat",
            "uninstall_startup_task.bat",
            "run_readiness_check.bat",
            "show_stock_bot_status.bat",
        ]
        missing = [script for script in scripts if not (WORKSPACE / script).exists()]
        if missing:
            self._warn("Operations", "Windows scripts", "누락: " + ", ".join(missing), "저장소를 최신 상태로 pull 하세요.")
        else:
            self._pass("Operations", "Windows scripts", "설치/실행/종료/자동시작/점검 스크립트 확인")

        if README_FILE.exists() and "의사결정 등급" in README_FILE.read_text(encoding="utf-8"):
            self._pass("Operations", "Runbook", "README 운영 설명 확인")
        else:
            self._warn("Operations", "Runbook", "README 운영 설명이 부족합니다.", "README를 최신 버전으로 pull 하세요.")

    def _risk_policy(self) -> Dict[str, object]:
        policy = DecisionPolicy()
        return {
            "strategy_profile": active_strategy_profile(),
            "target": self.target,
            "min_factor_score": factor_score_minimum(),
            "min_investment_thesis_score": investment_thesis_minimum(),
            "min_data_quality": data_quality_min_score(),
            "telegram_recommendation_limit": telegram_recommendation_limit(),
            "watchlist_enabled": watchlist_enabled(),
            "watchlist_min_factor_score": watchlist_factor_score_minimum(),
            "watchlist_min_investment_thesis_score": watchlist_investment_thesis_minimum(),
            "watchlist_min_data_quality": watchlist_data_quality_min_score(),
            "radar_enabled": radar_enabled(),
            "radar_min_factor_score": radar_factor_score_minimum(),
            "radar_min_investment_thesis_score": radar_investment_thesis_minimum(),
            "radar_min_data_quality": radar_data_quality_min_score(),
            "strong_buy_score": policy.strong_buy_score,
            "auto_trade_min_score": policy.trade_ready_score,
            "auto_trade_min_data_quality": policy.auto_min_data_quality,
            "auto_trade_max_stop_loss_pct": policy.max_stop_loss_pct,
            "auto_trade_sub_score_minimums": {
                "financial": policy.min_financial_score,
                "accumulation": policy.min_accumulation_score,
                "technical": policy.min_technical_score,
                "risk": policy.min_risk_score,
            },
            "order_budget_krw": env_float("AUTO_TRADE_ORDER_BUDGET_KRW", AUTO_TRADE_ORDER_BUDGET_KRW),
            "max_order_value_krw": env_float("AUTO_TRADE_MAX_ORDER_VALUE_KRW", AUTO_TRADE_MAX_ORDER_VALUE_KRW),
            "max_portfolio_exposure_krw": env_float(
                "AUTO_TRADE_MAX_PORTFOLIO_EXPOSURE_KRW",
                AUTO_TRADE_MAX_PORTFOLIO_EXPOSURE_KRW,
            ),
            "risk_per_trade_krw": env_float("AUTO_TRADE_RISK_PER_TRADE_KRW", AUTO_TRADE_RISK_PER_TRADE_KRW),
            "auto_trade_enabled": env_bool("AUTO_TRADE_ENABLED", AUTO_TRADE_ENABLED),
            "auto_trade_dry_run": env_bool("AUTO_TRADE_DRY_RUN", AUTO_TRADE_DRY_RUN),
            "kis_trading_env": normalize_trading_env(os.getenv("KIS_TRADING_ENV", "real")),
        }

    def _mode(self, blocks: int) -> str:
        if blocks:
            return "ACTION_REQUIRED"
        if self.target == "live-trading":
            return "LIVE_TRADE_READY"
        if self.target == "demo-trading":
            return "DEMO_TRADE_READY"
        return "ALERT_READY"

    @staticmethod
    def _summary(mode: str, blocks: int, warnings: int) -> str:
        if blocks:
            return f"차단 항목 {blocks}개, 경고 {warnings}개가 있습니다. 차단 항목부터 해결하세요."
        if warnings:
            return f"치명적 차단은 없지만 경고 {warnings}개가 있습니다. 운영 전 확인이 필요합니다."
        return f"{mode}: 운영 준비 완료"

    def _gitignore_patterns(self) -> List[str]:
        if not GITIGNORE_FILE.exists():
            return []
        return [
            line.strip()
            for line in GITIGNORE_FILE.read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.strip().startswith("#")
        ]

    def _pass(self, category: str, name: str, detail: str) -> None:
        self._add(STATUS_PASS, category, name, detail)

    def _warn(self, category: str, name: str, detail: str, action: str = "") -> None:
        self._add(STATUS_WARN, category, name, detail, action)

    def _block(self, category: str, name: str, detail: str, action: str = "") -> None:
        self._add(STATUS_BLOCK, category, name, detail, action)

    def _add(self, status: str, category: str, name: str, detail: str, action: str = "") -> None:
        self.checks.append(CheckResult(category=category, name=name, status=status, detail=detail, action=action))
        if action and status in {STATUS_WARN, STATUS_BLOCK}:
            self.next_actions.append(f"[{category}] {name}: {action}")


def print_human(report: ReadinessReport) -> None:
    print("=== Stock Bot Operator Readiness ===")
    print(f"Generated : {report.generated_at}")
    print(f"Target    : {report.target}")
    print(f"Mode      : {report.mode}")
    print(f"Score     : {report.score}/100")
    print(f"Summary   : {report.summary}")
    print()

    for check in report.checks:
        print(f"[{check.status}] {check.category} / {check.name}: {check.detail}")
        if check.action:
            print(f"        Action: {check.action}")

    print()
    print("Risk Policy")
    for key, value in report.risk_policy.items():
        print(f"- {key}: {value}")

    if report.next_actions:
        print()
        print("Next Actions")
        for action in report.next_actions:
            print(f"- {action}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Operator readiness check for Stock Telegram Bot")
    parser.add_argument(
        "--target",
        choices=["alert", "demo-trading", "live-trading"],
        default="alert",
        help="운영 목표. 기본값은 알림/리서치 모드입니다.",
    )
    parser.add_argument("--no-network", action="store_true", help="Telegram/KIS/FDR 네트워크 점검을 생략합니다.")
    parser.add_argument("--send-telegram-test", action="store_true", help="점검 완료 테스트 메시지를 텔레그램으로 보냅니다.")
    parser.add_argument("--json", action="store_true", help="사람용 출력 대신 JSON으로 출력합니다.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    report = OperatorReadinessAuditor(
        target=args.target,
        network=not args.no_network,
        send_telegram_test=args.send_telegram_test,
    ).run()
    if args.json:
        print(json.dumps(asdict(report), ensure_ascii=False, indent=2))
    else:
        print_human(report)

    if report.mode == "ACTION_REQUIRED":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
