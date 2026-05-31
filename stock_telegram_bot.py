import json
import logging
import os
import time
import importlib
import hashlib
import xml.etree.ElementTree as ET
from contextlib import redirect_stderr, redirect_stdout
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta
from email.utils import parsedate_to_datetime
from html import unescape
from io import StringIO
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Dict, List, Optional
from urllib.parse import quote_plus

import FinanceDataReader as fdr
import pandas as pd
import requests
import schedule
import yfinance as yf
from dotenv import load_dotenv
from ta.momentum import RSIIndicator
from ta.volatility import AverageTrueRange


# Telegram settings: fill these directly, or set TELEGRAM_TOKEN / TELEGRAM_CHAT_ID env vars.
TELEGRAM_TOKEN = ""
CHAT_ID = ""
TELEGRAM_MAX_RETRIES = 3
TELEGRAM_RETRY_DELAY_SECONDS = 2.0
TELEGRAM_TIMEOUT_SECONDS = 20.0

# Korea Investment Securities Open API settings.
# Fill these directly, or set KIS_APP_KEY / KIS_APP_SECRET env vars.
KIS_APP_KEY = ""
KIS_APP_SECRET = ""
KIS_BASE_URL = "https://openapi.koreainvestment.com:9443"
KIS_ACCOUNT_NO = ""
KIS_ACCOUNT_PRODUCT_CODE = "01"
KIS_TRADING_ENV = "real"
KIS_MAX_RETRIES = 2
KIS_RETRY_DELAY_SECONDS = 1.0
KIS_DAILY_PRICE_ENABLED = False

# Scanner settings
STRATEGY_PROFILE = "institutional"  # conservative, institutional, balanced, aggressive
RUN_TIME_KST = "16:00"
LOOKBACK_DAYS = 220
MIN_HISTORY_DAYS = 80
MAX_REPORTS = 20
TELEGRAM_RECOMMENDATION_LIMIT = 3
REQUEST_DELAY_SECONDS = 0.15
RUN_LOCK_STALE_MINUTES = 180
SCHEDULER_LOCK_STALE_MINUTES = 720
KIS_DAILY_CHUNK_DAYS = 60
FUNDAMENTAL_CACHE_DAYS = 7
FAILURE_CACHE_DAYS = 3
KRX_FUNDAMENTAL_LOOKBACK_DAYS = 10
ENABLE_PYKRX_FUNDAMENTALS = True
STRICT_DATA_VALIDATION = True
MIN_DATA_QUALITY_SCORE = 70.0
ENABLE_PRICE_CROSSCHECK = True
MAX_PRICE_STALENESS_DAYS = 7
MAX_INVESTOR_DATA_STALENESS_DAYS = 10
MAX_CROSS_SOURCE_CLOSE_DIFF_PCT = 2.5
MAX_OHLC_ANOMALY_RATIO = 0.02
MAX_SINGLE_DAY_MOVE_PCT = 35.0
IMMEDIATE_ALERTS_ENABLED = False
IMMEDIATE_ALERT_COOLDOWN_HOURS = 20

# Intraday realtime scanner settings.
REALTIME_SCAN_ENABLED = True
REALTIME_CANDIDATE_RUN_TIME_KST = "08:40"
REALTIME_SCAN_START_KST = "09:20"
REALTIME_SCAN_END_KST = "14:50"
REALTIME_SCAN_INTERVAL_SECONDS = 180
REALTIME_MAX_WATCHLIST = 50
REALTIME_ALERT_COOLDOWN_HOURS = 3
REALTIME_MIN_VOLUME_PACE = 1.20
REALTIME_MIN_INTRADAY_CHANGE_PCT = -1.0
REALTIME_MAX_INTRADAY_RISE_PCT = 15.0
REALTIME_VI_GUARD_ENABLED = True
REALTIME_VI_SUSPECT_CHANGE_PCT = 10.0
REALTIME_BLOCK_MARGIN_RATE = 100.0

# News pulse monitor settings.
NEWS_ALERT_ENABLED = True
NEWS_SCAN_INTERVAL_SECONDS = 300
NEWS_LOOKBACK_MINUTES = 90
NEWS_ALERT_COOLDOWN_HOURS = 6
NEWS_MAX_STOCK_QUERIES = 10
NEWS_MAX_ITEMS_PER_SCAN = 15
NEWS_MIN_IMPACT_SCORE = 4.0
NEWS_BLOCK_AUTO_TRADE_ON_RISK = True
NEWS_TRADE_BLOCK_LOOKBACK_HOURS = 6
NEWS_TRADE_BLOCK_MIN_SCORE = 6.0
NEWS_MARKET_QUERIES = [
    "코스피 코스닥 증시 속보",
    "한국 증시 환율 금리 속보",
    "반도체 방산 조선 주식 수주 실적",
]
NEWS_HIGH_RISK_KEYWORDS = [
    "거래정지",
    "상장폐지",
    "횡령",
    "배임",
    "감사의견",
    "불성실공시",
    "관리종목",
    "압수수색",
]
NEWS_NEGATIVE_KEYWORDS = [
    "유상증자",
    "전환사채",
    "실적 쇼크",
    "적자전환",
    "영업손실",
    "하한가",
    "리콜",
    "소송",
    "제재",
    "과징금",
    "화재",
    "급락",
]
NEWS_POSITIVE_KEYWORDS = [
    "수주",
    "공급계약",
    "어닝 서프라이즈",
    "흑자전환",
    "자사주",
    "배당",
    "목표가 상향",
    "증설",
    "인수",
]

# Auto-trading settings. Real orders are blocked unless explicitly enabled in .env.
AUTO_TRADE_ENABLED = False
AUTO_TRADE_DRY_RUN = True
AUTO_TRADE_CONFIRM_REAL_TRADING = "NO"
AUTO_TRADE_RUN_TIME_KST = "09:05"
AUTO_TRADE_MAX_ORDERS_PER_RUN = 2
AUTO_TRADE_ORDER_BUDGET_KRW = 300_000
AUTO_TRADE_MAX_ORDER_VALUE_KRW = 500_000
AUTO_TRADE_MAX_PORTFOLIO_EXPOSURE_KRW = 1_000_000
AUTO_TRADE_COOLDOWN_HOURS = 20
AUTO_TRADE_PENDING_MAX_AGE_HOURS = 20
AUTO_TRADE_ORDER_TYPE = "00"  # 00: limit, 01: market
AUTO_TRADE_EXCHANGE = "KRX"
AUTO_TRADE_USE_HASHKEY = True
AUTO_TRADE_USE_RISK_SIZING = True
AUTO_TRADE_RISK_PER_TRADE_KRW = 50_000

# Liquidity guardrails
MIN_MARKET_CAP = 50_000_000_000
MIN_DAILY_TRADING_VALUE = 500_000_000

# Market regime filter
MARKET_INDEX_CODE = "KS11"
KOSDAQ_MARKET_INDEX_CODE = "229200"
MARKET_REGIME_LOOKBACK_DAYS = 320
MARKET_REGIME_MA = 200
MAX_RELATIVE_VOLATILITY = 1.10

# Smart money accumulation filter
ENABLE_SMART_MONEY_FILTER = True
ACCUMULATION_LOOKBACK_DAYS = 20
ACCUMULATION_PAGES = 5
MIN_ACCUMULATION_RATIO = 0.001
MIN_ACCUMULATION_POSITIVE_DAYS = 10
MAX_SIDEWAYS_PRICE_CHANGE = 0.05
MIN_ACCUMULATION_AMOUNT_TO_MARKET_CAP = 0.0005

# Financial filters
MAX_DEBT_TO_EQUITY = 100.0
MIN_CURRENT_RATIO = 150.0
MAX_PBR = 1.5
REQUIRED_PROFIT_YEARS = 3
ENABLE_VALUE_TRAP_GUARD = True
MIN_ROE = 5.0
MIN_OPERATING_MARGIN = 3.0
MIN_REVENUE_GROWTH_YOY = -5.0
MIN_OPERATING_INCOME_GROWTH_YOY = -20.0
MIN_FACTOR_SCORE = 60.0

# Discovery tier settings. Watchlist candidates are allowed to be wider, but
# auto-trading still goes through the strict gates below.
WATCHLIST_ENABLED = True
WATCHLIST_MIN_FACTOR_SCORE = 58.0
WATCHLIST_MIN_INVESTMENT_THESIS_SCORE = 55.0
WATCHLIST_MIN_DATA_QUALITY_SCORE = 68.0
WATCHLIST_REQUIRE_SMART_MONEY = False
WATCHLIST_MAX_DEBT_TO_EQUITY = 180.0
WATCHLIST_MIN_CURRENT_RATIO = 100.0
WATCHLIST_MAX_PBR = 2.5
WATCHLIST_REQUIRED_PROFIT_YEARS = 2
WATCHLIST_MIN_FINANCIAL_DATA_QUALITY_SCORE = 58.0
WATCHLIST_MIN_ROE = 0.0
WATCHLIST_MIN_OPERATING_MARGIN = 0.0
WATCHLIST_MIN_REVENUE_GROWTH_YOY = -20.0
WATCHLIST_MIN_OPERATING_INCOME_GROWTH_YOY = -50.0
RADAR_ENABLED = True
RADAR_MIN_FACTOR_SCORE = 35.0
RADAR_MIN_INVESTMENT_THESIS_SCORE = 35.0
RADAR_MIN_DATA_QUALITY_SCORE = 50.0

# Technical filters
RSI_WINDOW = 14
ATR_WINDOW = 14
ATR_STOP_MULTIPLIER = 2.0
MA_SHORT = 20
MA_LONG = 60
MIN_RSI = 40.0
MAX_RSI = 55.0
MA_SUPPORT_BAND = 0.03
MAX_DISTANCE_ABOVE_MA20 = 0.08
MIN_RELATIVE_STRENGTH_60D = 0.0
MIN_RETURN_20D = -8.0
MAX_RETURN_20D = 25.0
MAX_RETURN_120D = 120.0
MAX_DRAWDOWN_60D = 25.0
ENABLE_INVESTMENT_THESIS_FILTER = True
MIN_INVESTMENT_THESIS_SCORE = 70.0
MIN_INTERMEDIATE_MOMENTUM_120_20D = -5.0
MIN_HIGH_PROXIMITY_180D = 65.0
MAX_HIGH_PROXIMITY_180D = 104.0
MIN_RISK_REWARD_RATIO = 1.15
WATCHLIST_MIN_RSI = 30.0
WATCHLIST_MAX_RSI = 65.0
WATCHLIST_MA_SUPPORT_BAND = 0.10
WATCHLIST_MAX_DISTANCE_ABOVE_MA20 = 0.20
WATCHLIST_MAX_RELATIVE_VOLATILITY = 1.60
WATCHLIST_MIN_RELATIVE_STRENGTH_60D = -5.0
WATCHLIST_MIN_RETURN_20D = -18.0
WATCHLIST_MAX_RETURN_20D = 45.0
WATCHLIST_MAX_RETURN_120D = 180.0
WATCHLIST_MAX_DRAWDOWN_60D = 40.0
WATCHLIST_MIN_INTERMEDIATE_MOMENTUM_120_20D = -25.0
WATCHLIST_MIN_HIGH_PROXIMITY_180D = 45.0
WATCHLIST_MIN_RISK_REWARD_RATIO = 0.50
RADAR_MIN_RSI = 20.0
RADAR_MAX_RSI = 80.0
RADAR_MA_SUPPORT_BAND = 0.25
RADAR_MAX_DISTANCE_ABOVE_MA20 = 0.40
RADAR_MAX_RELATIVE_VOLATILITY = 2.50
RADAR_MIN_RELATIVE_STRENGTH_60D = -20.0
RADAR_MIN_RETURN_20D = -35.0
RADAR_MAX_RETURN_20D = 80.0
RADAR_MAX_RETURN_120D = 250.0
RADAR_MAX_DRAWDOWN_60D = 65.0
RADAR_MIN_INTERMEDIATE_MOMENTUM_120_20D = -60.0
RADAR_MIN_HIGH_PROXIMITY_180D = 20.0
RADAR_MIN_RISK_REWARD_RATIO = 0.10

# Real-order gates are stricter than alert gates.
AUTO_TRADE_MIN_SCORE = 80.0
AUTO_TRADE_MIN_DATA_QUALITY = 85.0
AUTO_TRADE_MAX_STOP_LOSS_PCT = 8.0
AUTO_TRADE_MIN_FINANCIAL_SCORE = 20.0
AUTO_TRADE_MIN_ACCUMULATION_SCORE = 12.0
AUTO_TRADE_MIN_TECHNICAL_SCORE = 17.0
AUTO_TRADE_MIN_RISK_SCORE = 13.0
SIGNAL_STRONG_BUY_SCORE = 78.0

MARKETS = {"KOSPI", "KOSDAQ"}
EXCLUDE_NAME_KEYWORDS = ["스팩", "ETF", "ETN", "리츠"]
EXCLUDE_DEPT_KEYWORDS = ["관리종목", "투자주의환기", "SPAC"]
CACHE_DIR = Path("cache")
LOG_DIR = Path("logs")
BOT_LOG_FILE = LOG_DIR / "bot.log"
BOT_LOG_MAX_BYTES = 2_000_000
BOT_LOG_BACKUP_COUNT = 5
FUNDAMENTAL_CACHE_FILE = CACHE_DIR / "fundamentals.json"
ALERT_CACHE_FILE = CACHE_DIR / "alerts.json"
KIS_TOKEN_CACHE_FILE = CACHE_DIR / "kis_token.json"
PENDING_TRADE_FILE = CACHE_DIR / "pending_trades.json"
TRADE_HISTORY_FILE = CACHE_DIR / "trade_history.json"
REALTIME_CANDIDATE_FILE = CACHE_DIR / "realtime_candidates.json"
REALTIME_ALERT_FILE = CACHE_DIR / "realtime_alerts.json"
NEWS_ALERT_FILE = CACHE_DIR / "news_alerts.json"
BOT_STATE_FILE = CACHE_DIR / "bot_state.json"
SCHEDULER_LOCK_FILE = CACHE_DIR / "scheduler.lock"
SCAN_LOCK_FILE = CACHE_DIR / "research_scan.lock"
REALTIME_LOCK_FILE = CACHE_DIR / "realtime_scan.lock"
NEWS_LOCK_FILE = CACHE_DIR / "news_scan.lock"
TRADING_LOCK_FILE = CACHE_DIR / "trading.lock"


def configure_logging() -> None:
    formatter = logging.Formatter(
        fmt="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)

    if not root_logger.handlers:
        stream_handler = logging.StreamHandler()
        stream_handler.setFormatter(formatter)
        root_logger.addHandler(stream_handler)

    try:
        LOG_DIR.mkdir(exist_ok=True)
        log_path = str(BOT_LOG_FILE.resolve())
        has_file_handler = any(
            isinstance(handler, RotatingFileHandler)
            and getattr(handler, "baseFilename", "") == log_path
            for handler in root_logger.handlers
        )
        if not has_file_handler:
            file_handler = RotatingFileHandler(
                BOT_LOG_FILE,
                maxBytes=BOT_LOG_MAX_BYTES,
                backupCount=BOT_LOG_BACKUP_COUNT,
                encoding="utf-8",
            )
            file_handler.setFormatter(formatter)
            root_logger.addHandler(file_handler)
    except Exception as exc:
        root_logger.warning("파일 로그 설정 실패: %s", exc)


configure_logging()
logger = logging.getLogger("financial-health-scanner")


@dataclass
class StockMeta:
    code: str
    name: str
    market: str
    market_cap: Optional[float]
    shares: Optional[float]
    trading_value: Optional[float]
    dept: str = ""


@dataclass
class DataQualityReport:
    source: str
    score: float
    grade: str
    passed: bool
    checks: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)


@dataclass
class FinancialMetrics:
    code: str
    name: str
    yahoo_symbol: str
    debt_to_equity: float
    current_ratio: float
    pbr: float
    operating_income_years: List[float]
    operating_margin: Optional[float]
    market_cap: Optional[float]
    per: Optional[float] = None
    roe: Optional[float] = None
    bps: Optional[float] = None
    eps: Optional[float] = None
    revenue_growth_yoy: Optional[float] = None
    operating_income_growth_yoy: Optional[float] = None
    financial_source: str = "yfinance"
    quality_notes: List[str] = field(default_factory=list)
    data_quality_score: float = 0.0
    data_quality_grade: str = "N/A"
    data_quality_warnings: List[str] = field(default_factory=list)
    signal_stage: str = "strict"


@dataclass
class TechnicalSnapshot:
    current_price: float
    rsi: float
    ma20: float
    ma60: float
    atr: float
    stop_loss: float
    volatility: float
    market_volatility: float
    trend_summary: str
    previous_close: float = 0.0
    volume: float = 0.0
    avg_volume20: float = 0.0
    return_20d: float = 0.0
    return_60d: float = 0.0
    return_120d: float = 0.0
    market_return_60d: float = 0.0
    relative_strength_60d: float = 0.0
    max_drawdown_60d: float = 0.0
    momentum_120_20d: float = 0.0
    high_180d: float = 0.0
    low_180d: float = 0.0
    high_proximity_180d: float = 0.0
    distance_to_180d_high_pct: float = 0.0
    target_price: float = 0.0
    risk_reward_ratio: float = 0.0
    price_source: str = ""
    data_quality_score: float = 0.0
    data_quality_grade: str = "N/A"
    data_quality_warnings: List[str] = field(default_factory=list)
    signal_stage: str = "strict"


@dataclass
class AccumulationSnapshot:
    days: int
    foreign_net_buy: float
    institutional_net_buy: float
    combined_net_buy: float
    net_buy_ratio: float
    positive_days: int
    price_change: float
    summary: str
    foreign_net_buy_amount: float = 0.0
    institutional_net_buy_amount: float = 0.0
    combined_net_buy_amount: float = 0.0
    net_buy_amount_to_market_cap: Optional[float] = None
    net_buy_amount_to_trading_value: Optional[float] = None
    data_quality_score: float = 0.0
    data_quality_grade: str = "N/A"
    data_quality_warnings: List[str] = field(default_factory=list)


@dataclass
class MarketRegime:
    index_code: str
    current: float
    ma200: float
    volatility: float
    risk_on: bool
    summary: str
    return_20d: float = 0.0
    return_60d: float = 0.0
    return_120d: float = 0.0


@dataclass
class DiscoveryReport:
    stock: StockMeta
    financials: FinancialMetrics
    technicals: TechnicalSnapshot
    accumulation: Optional[AccumulationSnapshot]
    reason: str
    score: Optional["FactorScore"] = None
    data_quality_score: float = 0.0
    data_quality_grade: str = "N/A"
    data_quality_warnings: List[str] = field(default_factory=list)
    thesis: Optional["InvestmentThesis"] = None
    decision: Optional["SignalDecision"] = None
    signal_stage: str = "strict"


@dataclass
class FactorScore:
    financial: float
    accumulation: float
    technical: float
    risk: float
    total: float
    grade: str
    notes: List[str] = field(default_factory=list)


@dataclass
class SignalDecision:
    tier: str
    action: str
    trade_eligible: bool
    reasons: List[str] = field(default_factory=list)
    vetoes: List[str] = field(default_factory=list)


@dataclass
class InvestmentThesis:
    quality: float
    value: float
    momentum: float
    psychology: float
    asymmetry: float
    total: float
    label: str
    strengths: List[str] = field(default_factory=list)
    concerns: List[str] = field(default_factory=list)


@dataclass
class OrderPlan:
    side: str
    code: str
    name: str
    quantity: int
    estimated_price: float
    estimated_value: float
    stop_loss: float
    order_type: str
    exchange: str
    reason: str
    created_at: str
    risk_per_share: float = 0.0
    estimated_risk: float = 0.0


@dataclass
class OrderResult:
    plan: OrderPlan
    submitted: bool
    dry_run: bool
    status: str
    message: str
    order_number: Optional[str] = None


@dataclass
class RealtimeCandidate:
    stock: StockMeta
    financials: FinancialMetrics
    technicals: TechnicalSnapshot
    accumulation: Optional[AccumulationSnapshot]
    reason: str
    created_at: str
    score: Optional[FactorScore] = None
    data_quality_score: float = 0.0
    data_quality_grade: str = "N/A"
    data_quality_warnings: List[str] = field(default_factory=list)
    thesis: Optional[InvestmentThesis] = None
    decision: Optional[SignalDecision] = None
    signal_stage: str = "strict"


@dataclass
class RealtimeSignal:
    candidate: RealtimeCandidate
    current_price: float
    change_rate: float
    volume_ratio: float
    volume_pace_ratio: float
    market_regime: MarketRegime
    summary: str


@dataclass
class NewsImpact:
    query: str
    title: str
    link: str
    source: str
    published_at: str
    sentiment: str
    impact_score: float
    matched_terms: List[str] = field(default_factory=list)
    related_code: str = ""
    related_name: str = ""


@dataclass
class KrxFundamental:
    code: str
    per: Optional[float]
    pbr: Optional[float]
    eps: Optional[float]
    bps: Optional[float]
    roe: Optional[float]
    source_date: str


class BotLockError(RuntimeError):
    pass


class BotRunLock:
    def __init__(self, path: Path, name: str, stale_minutes: Optional[float] = None) -> None:
        self.path = path
        self.name = name
        self.stale_minutes = stale_minutes if stale_minutes is not None else RUN_LOCK_STALE_MINUTES
        self.token = f"{os.getpid()}:{time.time()}"

    def __enter__(self) -> "BotRunLock":
        CACHE_DIR.mkdir(exist_ok=True)
        payload = {
            "name": self.name,
            "pid": os.getpid(),
            "started_at": datetime.now().isoformat(timespec="seconds"),
            "token": self.token,
        }
        for _ in range(2):
            try:
                fd = os.open(str(self.path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                with os.fdopen(fd, "w", encoding="utf-8") as file:
                    json.dump(payload, file, ensure_ascii=False, indent=2)
                return self
            except FileExistsError:
                if self._remove_if_stale():
                    continue
                lock_info = self._read_lock_info()
                started_at = lock_info.get("started_at", "unknown")
                pid = lock_info.get("pid", "unknown")
                raise BotLockError(f"{self.name} 작업이 이미 실행 중입니다. pid={pid}, started_at={started_at}")
        raise BotLockError(f"{self.name} 실행 락을 확보하지 못했습니다.")

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        try:
            lock_info = self._read_lock_info()
            if lock_info.get("token") == self.token:
                self.path.unlink(missing_ok=True)
        except Exception as cleanup_exc:
            logger.debug("%s 락 정리 실패: %s", self.name, cleanup_exc)

    def _remove_if_stale(self) -> bool:
        lock_info = self._read_lock_info()
        started_at_text = str(lock_info.get("started_at", ""))
        try:
            started_at = datetime.fromisoformat(started_at_text)
        except ValueError:
            started_at = datetime.fromtimestamp(self.path.stat().st_mtime)
        age_minutes = (datetime.now() - started_at).total_seconds() / 60
        if age_minutes < max(1.0, self.stale_minutes):
            return False
        logger.warning("%s 오래된 실행 락 제거: %.1f분 경과", self.name, age_minutes)
        self.path.unlink(missing_ok=True)
        return True

    def _read_lock_info(self) -> Dict[str, object]:
        try:
            with self.path.open("r", encoding="utf-8") as file:
                payload = json.load(file)
            return payload if isinstance(payload, dict) else {}
        except Exception:
            return {}


class OperationStateStore:
    def __init__(self, path: Path = BOT_STATE_FILE) -> None:
        self.path = path

    def start_job(self, job_name: str, details: Optional[Dict[str, object]] = None) -> datetime:
        started_at = datetime.now()
        state = self._load()
        jobs = state.setdefault("jobs", {})
        jobs[job_name] = {
            "status": "running",
            "started_at": started_at.isoformat(timespec="seconds"),
            "updated_at": started_at.isoformat(timespec="seconds"),
            "details": details or {},
        }
        state["heartbeat_at"] = started_at.isoformat(timespec="seconds")
        self._save(state)
        return started_at

    def finish_job(
        self,
        job_name: str,
        started_at: datetime,
        status: str,
        details: Optional[Dict[str, object]] = None,
    ) -> None:
        finished_at = datetime.now()
        state = self._load()
        jobs = state.setdefault("jobs", {})
        jobs[job_name] = {
            "status": status,
            "started_at": started_at.isoformat(timespec="seconds"),
            "finished_at": finished_at.isoformat(timespec="seconds"),
            "updated_at": finished_at.isoformat(timespec="seconds"),
            "duration_seconds": round((finished_at - started_at).total_seconds(), 1),
            "details": details or {},
        }
        state["heartbeat_at"] = finished_at.isoformat(timespec="seconds")
        self._save(state)

    def heartbeat(self, details: Optional[Dict[str, object]] = None) -> None:
        now = datetime.now()
        state = self._load()
        state["heartbeat_at"] = now.isoformat(timespec="seconds")
        state["process"] = {
            "pid": os.getpid(),
            "updated_at": now.isoformat(timespec="seconds"),
            "details": details or {},
        }
        self._save(state)

    def _load(self) -> Dict[str, object]:
        if not self.path.exists():
            return {"version": 1, "jobs": {}}
        try:
            with self.path.open("r", encoding="utf-8") as file:
                payload = json.load(file)
            return payload if isinstance(payload, dict) else {"version": 1, "jobs": {}}
        except Exception as exc:
            logger.warning("운영 상태 파일 로드 실패: %s", exc)
            return {"version": 1, "jobs": {}}

    def _save(self, state: Dict[str, object]) -> None:
        try:
            CACHE_DIR.mkdir(exist_ok=True)
            with self.path.open("w", encoding="utf-8") as file:
                json.dump(state, file, ensure_ascii=False, indent=2)
        except Exception as exc:
            logger.warning("운영 상태 파일 저장 실패: %s", exc)


class KrxFundamentalProvider:
    def __init__(self) -> None:
        self.enabled = env_bool("ENABLE_PYKRX_FUNDAMENTALS", ENABLE_PYKRX_FUNDAMENTALS)
        self._stock_api = None
        self._frame: Optional[pd.DataFrame] = None
        self._source_date = ""

    def get(self, code: str) -> Optional[KrxFundamental]:
        if not self.enabled:
            return None

        frame = self._load_frame()
        if frame is None or frame.empty or code not in frame.index:
            return None

        row = frame.loc[code]
        per = to_float(row.get("PER"))
        pbr = to_float(row.get("PBR"))
        eps = to_float(row.get("EPS"))
        bps = to_float(row.get("BPS"))
        roe = None
        if eps is not None and bps and bps > 0:
            roe = eps / bps * 100

        return KrxFundamental(
            code=code,
            per=per,
            pbr=pbr,
            eps=eps,
            bps=bps,
            roe=roe,
            source_date=self._source_date,
        )

    def _load_frame(self) -> Optional[pd.DataFrame]:
        if self._frame is not None:
            return self._frame
        stock_api = self._load_stock_api()
        if stock_api is None:
            self.enabled = False
            return None

        last_error: Optional[Exception] = None
        root_logger = logging.getLogger()
        original_level = root_logger.level
        for offset in range(KRX_FUNDAMENTAL_LOOKBACK_DAYS + 1):
            date_text = (datetime.now() - timedelta(days=offset)).strftime("%Y%m%d")
            try:
                root_logger.setLevel(max(original_level, logging.ERROR))
                frame = self._fetch_by_date(stock_api, date_text)
                if frame is not None and not frame.empty:
                    frame.index = frame.index.map(lambda value: str(value).zfill(6))
                    self._frame = frame
                    self._source_date = date_text
                    logger.info("pykrx 재무 기초지표 로드 완료: %s, %d개", date_text, len(frame))
                    return self._frame
            except Exception as exc:
                last_error = exc
            finally:
                root_logger.setLevel(original_level)

        self.enabled = False
        if last_error:
            logger.warning("pykrx 재무 기초지표 로드 실패: %s", last_error)
        else:
            logger.warning("pykrx 재무 기초지표가 비어 있어 yfinance만 사용합니다.")
        return None

    def _load_stock_api(self):
        if not self.enabled:
            return None
        if self._stock_api is not None:
            return self._stock_api
        try:
            with redirect_stdout(StringIO()), redirect_stderr(StringIO()):
                self._stock_api = importlib.import_module("pykrx.stock")
            return self._stock_api
        except Exception as exc:
            logger.warning("pykrx 모듈 로드 실패, yfinance 재무 데이터만 사용합니다: %s", exc)
            self.enabled = False
            return None

    @staticmethod
    def _valid_fundamental_frame(frame: Optional[pd.DataFrame]) -> bool:
        if frame is None or frame.empty:
            return False
        return bool({"BPS", "PER", "PBR", "EPS"} & set(frame.columns))

    @classmethod
    def _fetch_by_date(cls, stock_api, date_text: str) -> Optional[pd.DataFrame]:
        try:
            with redirect_stdout(StringIO()), redirect_stderr(StringIO()):
                frame = stock_api.get_market_fundamental_by_ticker(date_text, market="ALL")
            if cls._valid_fundamental_frame(frame):
                return frame
        except Exception:
            pass

        frames: List[pd.DataFrame] = []
        for market in ("KOSPI", "KOSDAQ"):
            with redirect_stdout(StringIO()), redirect_stderr(StringIO()):
                frame = stock_api.get_market_fundamental_by_ticker(date_text, market=market)
            if cls._valid_fundamental_frame(frame):
                frames.append(frame)
        if not frames:
            return None
        return pd.concat(frames)


class DataQualityValidator:
    @staticmethod
    def validate_price_frame(
        data: pd.DataFrame,
        source: str,
        min_rows: int = MIN_HISTORY_DAYS,
    ) -> DataQualityReport:
        score = 100.0
        checks: List[str] = []
        warnings: List[str] = []

        if data is None or data.empty:
            return DataQualityValidator._report(source, 0.0, checks, ["가격 데이터가 비어 있습니다."])

        frame = data.copy()
        required = {"High", "Low", "Close"}
        missing = sorted(required - set(frame.columns))
        if missing:
            return DataQualityValidator._report(
                source,
                0.0,
                checks,
                [f"필수 가격 컬럼 누락: {', '.join(missing)}"],
            )
        checks.append("필수 OHLC 컬럼 확인")

        if not isinstance(frame.index, pd.DatetimeIndex):
            frame.index = pd.to_datetime(frame.index, errors="coerce")
        invalid_index_ratio = float(frame.index.isna().mean()) if len(frame) else 1.0
        if invalid_index_ratio > 0:
            score -= min(30.0, invalid_index_ratio * 100)
            warnings.append(f"날짜 인덱스 변환 실패 {invalid_index_ratio * 100:.1f}%")
        frame = frame[frame.index.notna()].sort_index()

        duplicate_count = int(frame.index.duplicated().sum())
        if duplicate_count:
            score -= min(15.0, duplicate_count / max(len(frame), 1) * 100)
            warnings.append(f"중복 날짜 {duplicate_count}건")
        else:
            checks.append("중복 날짜 없음")

        for column in ["Open", "High", "Low", "Close", "Volume"]:
            if column in frame.columns:
                frame[column] = pd.to_numeric(frame[column], errors="coerce")

        valid_rows = frame.dropna(subset=["High", "Low", "Close"])
        if len(valid_rows) < min_rows:
            score -= 45.0
            warnings.append(f"유효 가격 데이터 부족: {len(valid_rows)}일")
        else:
            checks.append(f"유효 가격 데이터 {len(valid_rows)}일")

        close = valid_rows["Close"].astype(float)
        positive_close_ratio = float((close > 0).mean()) if len(close) else 0.0
        if positive_close_ratio < 1.0:
            penalty = (1.0 - positive_close_ratio) * 80.0
            score -= penalty
            warnings.append(f"0 이하 종가 비율 {(1.0 - positive_close_ratio) * 100:.1f}%")

        ohlc_ok = (valid_rows["High"] >= valid_rows["Low"]) & (valid_rows["High"] >= valid_rows["Close"]) & (
            valid_rows["Low"] <= valid_rows["Close"]
        )
        if "Open" in valid_rows.columns:
            ohlc_ok = ohlc_ok & (valid_rows["High"] >= valid_rows["Open"]) & (valid_rows["Low"] <= valid_rows["Open"])
        anomaly_ratio = float((~ohlc_ok).mean()) if len(valid_rows) else 1.0
        if anomaly_ratio > MAX_OHLC_ANOMALY_RATIO:
            score -= min(35.0, anomaly_ratio * 100)
            warnings.append(f"OHLC 불일치 비율 {anomaly_ratio * 100:.1f}%")
        else:
            checks.append("OHLC 범위 정상")

        latest_date = valid_rows.index.max() if not valid_rows.empty else None
        if latest_date is not None:
            stale_days = (datetime.now().date() - latest_date.date()).days
            max_staleness_days = env_int("MAX_PRICE_STALENESS_DAYS", MAX_PRICE_STALENESS_DAYS)
            if stale_days > max_staleness_days:
                score -= min(40.0, (stale_days - max_staleness_days) * 6.0)
                warnings.append(f"최신 가격 데이터 지연 {stale_days}일")
            else:
                checks.append(f"최신 가격 데이터 {latest_date.strftime('%Y-%m-%d')}")

        if "Volume" in valid_rows.columns:
            volume = valid_rows["Volume"].dropna().astype(float)
            negative_volume = int((volume < 0).sum())
            if negative_volume:
                score -= 25.0
                warnings.append(f"음수 거래량 {negative_volume}건")
            zero_volume_ratio = float((volume <= 0).mean()) if len(volume) else 1.0
            if zero_volume_ratio > 0.2:
                score -= min(20.0, zero_volume_ratio * 40)
                warnings.append(f"0 거래량 비율 {zero_volume_ratio * 100:.1f}%")
        else:
            score -= 8.0
            warnings.append("거래량 컬럼 없음")

        returns = close.pct_change().abs().dropna()
        if not returns.empty and float(returns.max() * 100) > MAX_SINGLE_DAY_MOVE_PCT:
            warnings.append(f"단일 일간 변동률 {float(returns.max() * 100):.1f}% 감지")
            score -= 5.0

        return DataQualityValidator._report(source, score, checks, warnings)

    @staticmethod
    def compare_price_sources(
        primary: pd.DataFrame,
        secondary: pd.DataFrame,
        primary_source: str,
        secondary_source: str,
    ) -> DataQualityReport:
        source = f"{primary_source}+{secondary_source}"
        checks: List[str] = []
        warnings: List[str] = []
        score = 100.0

        if primary is None or primary.empty or secondary is None or secondary.empty:
            return DataQualityValidator._report(source, 55.0, checks, ["교차검증 소스 중 하나가 비어 있습니다."])

        left = primary.copy()
        right = secondary.copy()
        if not isinstance(left.index, pd.DatetimeIndex):
            left.index = pd.to_datetime(left.index, errors="coerce")
        if not isinstance(right.index, pd.DatetimeIndex):
            right.index = pd.to_datetime(right.index, errors="coerce")
        left = left[left.index.notna()].sort_index()
        right = right[right.index.notna()].sort_index()
        left = left[~left.index.duplicated(keep="last")]
        right = right[~right.index.duplicated(keep="last")]

        common_dates = left.index.intersection(right.index)
        if common_dates.empty:
            return DataQualityValidator._report(source, 45.0, checks, ["KIS/FDR 공통 거래일이 없습니다."])

        latest_left = left.index.max()
        latest_right = right.index.max()
        latest_gap_days = abs((latest_left.date() - latest_right.date()).days)
        if latest_gap_days:
            score -= min(25.0, latest_gap_days * 10.0)
            warnings.append(
                f"최신 거래일 불일치: {primary_source} {latest_left.strftime('%Y-%m-%d')}, "
                f"{secondary_source} {latest_right.strftime('%Y-%m-%d')}"
            )
        else:
            checks.append(f"최신 거래일 일치 {latest_left.strftime('%Y-%m-%d')}")

        latest = common_dates.max()
        left_close = to_float(left.loc[latest, "Close"])
        right_close = to_float(right.loc[latest, "Close"])
        if not left_close or not right_close or right_close <= 0:
            return DataQualityValidator._report(source, 50.0, checks, ["교차검증 종가를 해석하지 못했습니다."])

        diff_pct = abs(left_close / right_close - 1) * 100
        max_close_diff_pct = env_float("MAX_CROSS_SOURCE_CLOSE_DIFF_PCT", MAX_CROSS_SOURCE_CLOSE_DIFF_PCT)
        if diff_pct > max_close_diff_pct:
            score -= min(65.0, diff_pct * 8.0)
            warnings.append(f"{latest.strftime('%Y-%m-%d')} 종가 차이 {diff_pct:.2f}%")
        else:
            checks.append(f"{latest.strftime('%Y-%m-%d')} 종가 차이 {diff_pct:.2f}%")

        overlap_ratio = len(common_dates) / max(min(len(left), len(right)), 1)
        if overlap_ratio < 0.85:
            score -= (0.85 - overlap_ratio) * 40
            warnings.append(f"공통 거래일 비율 {overlap_ratio * 100:.1f}%")
        else:
            checks.append(f"공통 거래일 비율 {overlap_ratio * 100:.1f}%")

        return DataQualityValidator._report(source, score, checks, warnings)

    @staticmethod
    def merge_reports(source: str, reports: List[DataQualityReport], weights: Optional[List[float]] = None) -> DataQualityReport:
        valid_reports = [report for report in reports if report is not None]
        if not valid_reports:
            return DataQualityValidator._report(source, 0.0, [], ["데이터 품질 리포트가 없습니다."])
        if weights is None or len(weights) != len(valid_reports):
            weights = [1.0 / len(valid_reports)] * len(valid_reports)
        total_weight = sum(weights) or 1.0
        score = sum(report.score * weight for report, weight in zip(valid_reports, weights)) / total_weight
        checks: List[str] = []
        warnings: List[str] = []
        for report in valid_reports:
            checks.extend([f"{report.source}: {item}" for item in report.checks[:3]])
            warnings.extend([f"{report.source}: {item}" for item in report.warnings[:3]])
        return DataQualityValidator._report(source, score, checks, warnings)

    @staticmethod
    def _report(source: str, score: float, checks: List[str], warnings: List[str]) -> DataQualityReport:
        clean_score = round(clamp(score, 0.0, 100.0), 1)
        grade = quality_grade(clean_score)
        min_score = data_quality_min_score()
        passed = clean_score >= min_score or not env_bool("STRICT_DATA_VALIDATION", STRICT_DATA_VALIDATION)
        return DataQualityReport(
            source=source,
            score=clean_score,
            grade=grade,
            passed=passed,
            checks=checks[:8],
            warnings=warnings[:8],
        )


class FinancialScanner:
    def __init__(self) -> None:
        self.cache: Dict[str, Dict[str, object]] = self._load_cache()
        self.krx_fundamentals = KrxFundamentalProvider()

    def fetch_universe(self) -> List[StockMeta]:
        logger.info("KOSPI/KOSDAQ 전종목 목록 수집 시작")
        listing = fdr.StockListing("KRX")
        listing = listing[listing["Market"].isin(MARKETS)].copy()
        listing = listing.dropna(subset=["Code", "Name", "Market"])

        stocks: List[StockMeta] = []
        for row in listing.itertuples(index=False):
            code = str(row.Code).zfill(6)
            name = str(row.Name).strip()
            market = str(row.Market).strip()
            dept = str(getattr(row, "Dept", "") or "").strip()
            market_cap = self._safe_float(getattr(row, "Marcap", None))
            shares = self._safe_float(getattr(row, "Stocks", None))
            trading_value = self._safe_float(getattr(row, "Amount", None))

            if not self._is_common_stock(name, dept):
                continue
            if not self._passes_liquidity_filter(market_cap, trading_value):
                continue

            stocks.append(
                StockMeta(
                    code=code,
                    name=name,
                    market=market,
                    market_cap=market_cap,
                    shares=shares,
                    trading_value=trading_value,
                    dept=dept,
                )
            )

        logger.info("재무 스캔 대상 종목 수: %d개", len(stocks))
        return stocks

    def scan(self, stocks: List[StockMeta]) -> List[FinancialMetrics]:
        passed: List[FinancialMetrics] = []
        strict_count = 0
        watchlist_count = 0

        for index, stock_meta in enumerate(stocks, start=1):
            if index % 100 == 0:
                logger.info("재무 필터 진행률: %d/%d", index, len(stocks))
                self._save_cache()

            metrics = self.fetch_financial_metrics(stock_meta)
            if metrics is None:
                continue

            if self._passes_financial_filters(metrics):
                metrics.signal_stage = "strict"
                strict_count += 1
                passed.append(metrics)
            elif watchlist_enabled() and self._passes_watchlist_financial_filters(metrics):
                metrics.signal_stage = "watchlist"
                watchlist_count += 1
                passed.append(metrics)

            time.sleep(REQUEST_DELAY_SECONDS)

        logger.info(
            "재무 필터 통과 종목 수: %d개(정규 %d개, 관찰 %d개)",
            len(passed),
            strict_count,
            watchlist_count,
        )
        self._save_cache()
        return passed

    def fetch_financial_metrics(self, stock_meta: StockMeta) -> Optional[FinancialMetrics]:
        cached = self._get_cached_metrics(stock_meta.code)
        if cached:
            return cached
        if self._is_recent_failed_cache(stock_meta.code):
            return None

        yahoo_symbol = self._to_yahoo_symbol(stock_meta)
        try:
            krx_metrics = self.krx_fundamentals.get(stock_meta.code)
            ticker = yf.Ticker(yahoo_symbol)
            balance_sheet = ticker.balance_sheet
            financials = ticker.financials

            if balance_sheet.empty:
                raise ValueError("yfinance balance_sheet 데이터가 비어 있습니다.")
            if financials.empty:
                raise ValueError("yfinance financials 데이터가 비어 있습니다.")

            latest_balance = balance_sheet.iloc[:, 0]
            total_liabilities = self._get_statement_value(
                latest_balance,
                ["Total Liabilities Net Minority Interest", "Total Debt"],
            )
            equity = self._get_statement_value(
                latest_balance,
                ["Stockholders Equity", "Common Stock Equity", "Total Equity Gross Minority Interest"],
            )
            current_assets = self._get_statement_value(latest_balance, ["Current Assets"])
            current_liabilities = self._get_statement_value(latest_balance, ["Current Liabilities"])

            if not equity or equity <= 0:
                raise ValueError("자본총계가 없거나 0 이하입니다.")
            if not current_liabilities or current_liabilities <= 0:
                raise ValueError("유동부채가 없거나 0 이하입니다.")

            debt_to_equity = total_liabilities / equity * 100
            current_ratio = current_assets / current_liabilities * 100
            market_cap = stock_meta.market_cap or self._safe_float(ticker.get_info().get("marketCap"))
            if not market_cap or market_cap <= 0:
                raise ValueError("시가총액 데이터가 없습니다.")

            computed_pbr = market_cap / equity
            pbr = krx_metrics.pbr if krx_metrics and krx_metrics.pbr and krx_metrics.pbr > 0 else computed_pbr
            per = krx_metrics.per if krx_metrics else None
            eps = krx_metrics.eps if krx_metrics else None
            bps = krx_metrics.bps if krx_metrics else None
            roe = krx_metrics.roe if krx_metrics else None

            operating_income_years = self._get_recent_operating_income(
                financials,
                max(REQUIRED_PROFIT_YEARS, 4),
            )
            revenue_values = self._get_recent_financial_values(
                financials,
                ["Total Revenue", "Operating Revenue"],
                2,
            )
            revenue = revenue_values[0] if revenue_values else None
            operating_margin = None
            if revenue and revenue > 0:
                operating_margin = operating_income_years[0] / revenue * 100
            revenue_growth_yoy = self._growth_rate(revenue_values)
            operating_income_growth_yoy = self._growth_rate(operating_income_years[:2])
            financial_source = "pykrx+yfinance" if krx_metrics else "yfinance"
            quality_notes = self._build_quality_notes(
                pbr=pbr,
                roe=roe,
                operating_margin=operating_margin,
                revenue_growth_yoy=revenue_growth_yoy,
                operating_income_growth_yoy=operating_income_growth_yoy,
            )

            metrics = FinancialMetrics(
                code=stock_meta.code,
                name=stock_meta.name,
                yahoo_symbol=yahoo_symbol,
                debt_to_equity=debt_to_equity,
                current_ratio=current_ratio,
                pbr=pbr,
                operating_income_years=operating_income_years,
                operating_margin=operating_margin,
                market_cap=market_cap,
                per=per,
                roe=roe,
                bps=bps,
                eps=eps,
                revenue_growth_yoy=revenue_growth_yoy,
                operating_income_growth_yoy=operating_income_growth_yoy,
                financial_source=financial_source,
                quality_notes=quality_notes,
            )
            financial_quality = self._validate_financial_metrics(metrics, computed_pbr, krx_metrics)
            metrics.data_quality_score = financial_quality.score
            metrics.data_quality_grade = financial_quality.grade
            metrics.data_quality_warnings = financial_quality.warnings
            self.cache[stock_meta.code] = {
                "cached_at": datetime.now().isoformat(timespec="seconds"),
                "metrics": asdict(metrics),
            }
            return metrics
        except Exception as exc:
            logger.warning("%s(%s) 재무 데이터 분석 실패: %s", stock_meta.name, stock_meta.code, exc)
            self.cache[stock_meta.code] = {
                "cached_at": datetime.now().isoformat(timespec="seconds"),
                "error": str(exc),
            }
            return None

    def _passes_financial_filters(self, metrics: FinancialMetrics) -> bool:
        if metrics.debt_to_equity >= MAX_DEBT_TO_EQUITY:
            return False
        if metrics.current_ratio < MIN_CURRENT_RATIO:
            return False
        if metrics.pbr >= MAX_PBR:
            return False
        if len(metrics.operating_income_years) < REQUIRED_PROFIT_YEARS:
            return False
        if not all(value > 0 for value in metrics.operating_income_years[:REQUIRED_PROFIT_YEARS]):
            return False
        if metrics.data_quality_score < data_quality_min_score():
            return False
        if env_bool("ENABLE_VALUE_TRAP_GUARD", ENABLE_VALUE_TRAP_GUARD) and self._looks_like_value_trap(metrics):
            return False
        return True

    def _passes_watchlist_financial_filters(self, metrics: FinancialMetrics) -> bool:
        if metrics.debt_to_equity >= env_float("WATCHLIST_MAX_DEBT_TO_EQUITY", WATCHLIST_MAX_DEBT_TO_EQUITY):
            return False
        if metrics.current_ratio < env_float("WATCHLIST_MIN_CURRENT_RATIO", WATCHLIST_MIN_CURRENT_RATIO):
            return False
        if metrics.pbr >= env_float("WATCHLIST_MAX_PBR", WATCHLIST_MAX_PBR):
            return False

        required_years = max(1, env_int("WATCHLIST_REQUIRED_PROFIT_YEARS", WATCHLIST_REQUIRED_PROFIT_YEARS))
        positive_years = sum(1 for value in metrics.operating_income_years[: max(required_years, REQUIRED_PROFIT_YEARS)] if value > 0)
        if positive_years < required_years:
            return False

        min_quality = env_float(
            "WATCHLIST_MIN_FINANCIAL_DATA_QUALITY_SCORE",
            WATCHLIST_MIN_FINANCIAL_DATA_QUALITY_SCORE,
        )
        if metrics.data_quality_score < min_quality:
            return False

        if self._looks_like_severe_value_trap(metrics):
            return False
        return True

    @staticmethod
    def _validate_financial_metrics(
        metrics: FinancialMetrics,
        computed_pbr: float,
        krx_metrics: Optional[KrxFundamental],
    ) -> DataQualityReport:
        score = 100.0
        checks: List[str] = []
        warnings: List[str] = []

        if metrics.market_cap is None or metrics.market_cap <= 0:
            score -= 60.0
            warnings.append("시가총액 없음")
        else:
            checks.append("시가총액 확인")

        sanity_checks = [
            ("부채비율", metrics.debt_to_equity, 0.0, 1_000.0),
            ("유동비율", metrics.current_ratio, 0.0, 5_000.0),
            ("PBR", metrics.pbr, 0.0, 20.0),
        ]
        for label, value, minimum, maximum in sanity_checks:
            if value is None or value <= minimum or value > maximum:
                score -= 25.0
                warnings.append(f"{label} 비정상값 {value}")
            else:
                checks.append(f"{label} 범위 확인")

        if len(metrics.operating_income_years) < REQUIRED_PROFIT_YEARS:
            score -= 40.0
            warnings.append("영업이익 연속성 데이터 부족")
        elif not all(value > 0 for value in metrics.operating_income_years[:REQUIRED_PROFIT_YEARS]):
            score -= 35.0
            warnings.append("영업이익 흑자 연속성 실패")
        else:
            checks.append("영업이익 3년 연속 흑자")

        if krx_metrics is None:
            score -= 8.0
            warnings.append("pykrx 보강 데이터 없음")
        elif krx_metrics.pbr and computed_pbr > 0:
            pbr_diff_pct = abs(krx_metrics.pbr / computed_pbr - 1) * 100
            if pbr_diff_pct > 35.0:
                score -= min(25.0, pbr_diff_pct / 2)
                warnings.append(f"pykrx/yfinance PBR 차이 {pbr_diff_pct:.1f}%")
            else:
                checks.append(f"pykrx/yfinance PBR 차이 {pbr_diff_pct:.1f}%")

        optional_missing = []
        if metrics.roe is None:
            optional_missing.append("ROE")
        if metrics.revenue_growth_yoy is None:
            optional_missing.append("매출 YoY")
        if metrics.operating_income_growth_yoy is None:
            optional_missing.append("영업이익 YoY")
        if optional_missing:
            score -= min(15.0, len(optional_missing) * 4.0)
            warnings.append(f"보조 지표 누락: {', '.join(optional_missing)}")

        return DataQualityValidator._report(metrics.financial_source, score, checks, warnings)

    @staticmethod
    def _looks_like_value_trap(metrics: FinancialMetrics) -> bool:
        if metrics.roe is not None and metrics.roe < MIN_ROE:
            return True
        if metrics.operating_margin is not None and metrics.operating_margin < MIN_OPERATING_MARGIN:
            return True
        if metrics.revenue_growth_yoy is not None and metrics.revenue_growth_yoy < MIN_REVENUE_GROWTH_YOY:
            return True
        if (
            metrics.operating_income_growth_yoy is not None
            and metrics.operating_income_growth_yoy < MIN_OPERATING_INCOME_GROWTH_YOY
        ):
            return True
        return False

    @staticmethod
    def _looks_like_severe_value_trap(metrics: FinancialMetrics) -> bool:
        if metrics.roe is not None and metrics.roe < env_float("WATCHLIST_MIN_ROE", WATCHLIST_MIN_ROE):
            return True
        if (
            metrics.operating_margin is not None
            and metrics.operating_margin < env_float("WATCHLIST_MIN_OPERATING_MARGIN", WATCHLIST_MIN_OPERATING_MARGIN)
        ):
            return True
        if (
            metrics.revenue_growth_yoy is not None
            and metrics.revenue_growth_yoy < env_float("WATCHLIST_MIN_REVENUE_GROWTH_YOY", WATCHLIST_MIN_REVENUE_GROWTH_YOY)
        ):
            return True
        if (
            metrics.operating_income_growth_yoy is not None
            and metrics.operating_income_growth_yoy
            < env_float("WATCHLIST_MIN_OPERATING_INCOME_GROWTH_YOY", WATCHLIST_MIN_OPERATING_INCOME_GROWTH_YOY)
        ):
            return True
        return False

    def _get_cached_metrics(self, code: str) -> Optional[FinancialMetrics]:
        item = self.cache.get(code)
        if not item:
            return None

        try:
            cached_at = datetime.fromisoformat(str(item["cached_at"]))
            if datetime.now() - cached_at > timedelta(days=FUNDAMENTAL_CACHE_DAYS):
                return None

            if "metrics" not in item:
                return None

            metrics = item["metrics"]
            if "data_quality_score" not in metrics:
                return None
            return FinancialMetrics(
                code=str(metrics["code"]),
                name=str(metrics["name"]),
                yahoo_symbol=str(metrics["yahoo_symbol"]),
                debt_to_equity=float(metrics["debt_to_equity"]),
                current_ratio=float(metrics["current_ratio"]),
                pbr=float(metrics["pbr"]),
                operating_income_years=[float(value) for value in metrics["operating_income_years"]],
                operating_margin=self._safe_float(metrics.get("operating_margin")),
                market_cap=self._safe_float(metrics.get("market_cap")),
                per=self._safe_float(metrics.get("per")),
                roe=self._safe_float(metrics.get("roe")),
                bps=self._safe_float(metrics.get("bps")),
                eps=self._safe_float(metrics.get("eps")),
                revenue_growth_yoy=self._safe_float(metrics.get("revenue_growth_yoy")),
                operating_income_growth_yoy=self._safe_float(metrics.get("operating_income_growth_yoy")),
                financial_source=str(metrics.get("financial_source", "yfinance")),
                quality_notes=list(metrics.get("quality_notes") or []),
                data_quality_score=float(metrics.get("data_quality_score", 0.0)),
                data_quality_grade=str(metrics.get("data_quality_grade", "N/A")),
                data_quality_warnings=list(metrics.get("data_quality_warnings") or []),
                signal_stage=str(metrics.get("signal_stage", "strict")),
            )
        except Exception:
            return None

    def _is_recent_failed_cache(self, code: str) -> bool:
        item = self.cache.get(code)
        if not item or "error" not in item:
            return False

        try:
            cached_at = datetime.fromisoformat(str(item["cached_at"]))
            return datetime.now() - cached_at <= timedelta(days=FAILURE_CACHE_DAYS)
        except Exception:
            return False

    @staticmethod
    def _to_yahoo_symbol(stock_meta: StockMeta) -> str:
        suffix = ".KQ" if stock_meta.market == "KOSDAQ" else ".KS"
        return f"{stock_meta.code}{suffix}"

    @staticmethod
    def _get_statement_value(series: pd.Series, candidates: List[str]) -> float:
        for candidate in candidates:
            if candidate in series.index:
                value = FinancialScanner._safe_float(series.get(candidate))
                if value is not None:
                    return value
        raise ValueError(f"재무제표 항목을 찾지 못했습니다: {', '.join(candidates)}")

    @staticmethod
    def _get_recent_operating_income(financials: pd.DataFrame, count: int) -> List[float]:
        for row_name in ["Operating Income", "Total Operating Income As Reported", "EBIT"]:
            if row_name in financials.index:
                values = financials.loc[row_name].dropna().tolist()
                values = [float(value) for value in values if pd.notna(value)]
                if len(values) >= REQUIRED_PROFIT_YEARS:
                    return values[:count]
        raise ValueError("3년 영업이익 데이터를 찾지 못했습니다.")

    @staticmethod
    def _get_latest_financial_value(financials: pd.DataFrame, candidates: List[str]) -> Optional[float]:
        for candidate in candidates:
            if candidate in financials.index:
                values = financials.loc[candidate].dropna()
                if not values.empty:
                    return FinancialScanner._safe_float(values.iloc[0])
        return None

    @staticmethod
    def _get_recent_financial_values(financials: pd.DataFrame, candidates: List[str], count: int) -> List[float]:
        for candidate in candidates:
            if candidate not in financials.index:
                continue
            values: List[float] = []
            for value in financials.loc[candidate].dropna().tolist():
                numeric = FinancialScanner._safe_float(value)
                if numeric is not None:
                    values.append(numeric)
                if len(values) >= count:
                    return values
        return []

    @staticmethod
    def _growth_rate(values: List[float]) -> Optional[float]:
        if len(values) < 2:
            return None
        current, previous = values[0], values[1]
        if previous <= 0:
            return None
        return (current / previous - 1) * 100

    @staticmethod
    def _build_quality_notes(
        pbr: float,
        roe: Optional[float],
        operating_margin: Optional[float],
        revenue_growth_yoy: Optional[float],
        operating_income_growth_yoy: Optional[float],
    ) -> List[str]:
        notes: List[str] = []
        if pbr < 1.0:
            notes.append("PBR 1배 미만")
        if roe is not None:
            notes.append(f"ROE {roe:.1f}%")
        if operating_margin is not None:
            notes.append(f"영업이익률 {operating_margin:.1f}%")
        if revenue_growth_yoy is not None:
            notes.append(f"매출 YoY {revenue_growth_yoy:+.1f}%")
        if operating_income_growth_yoy is not None:
            notes.append(f"영업이익 YoY {operating_income_growth_yoy:+.1f}%")
        return notes

    @staticmethod
    def _safe_float(value: object) -> Optional[float]:
        try:
            if value is None or pd.isna(value):
                return None
            return float(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _is_common_stock(name: str, dept: str = "") -> bool:
        if any(keyword in name for keyword in EXCLUDE_NAME_KEYWORDS):
            return False
        if any(keyword in dept for keyword in EXCLUDE_DEPT_KEYWORDS):
            return False
        preferred_share_suffixes = ("우", "우B", "1우", "1우B", "2우", "2우B", "3우", "3우B")
        return not name.endswith(preferred_share_suffixes)

    @staticmethod
    def _passes_liquidity_filter(market_cap: Optional[float], trading_value: Optional[float]) -> bool:
        if market_cap is None or market_cap < MIN_MARKET_CAP:
            return False
        if trading_value is None or trading_value < MIN_DAILY_TRADING_VALUE:
            return False
        return True

    @staticmethod
    def _load_cache() -> Dict[str, Dict[str, object]]:
        if not FUNDAMENTAL_CACHE_FILE.exists():
            return {}
        try:
            with FUNDAMENTAL_CACHE_FILE.open("r", encoding="utf-8") as file:
                return json.load(file)
        except Exception as exc:
            logger.warning("재무 캐시 로드 실패: %s", exc)
            return {}

    def _save_cache(self) -> None:
        try:
            CACHE_DIR.mkdir(exist_ok=True)
            with FUNDAMENTAL_CACHE_FILE.open("w", encoding="utf-8") as file:
                json.dump(self.cache, file, ensure_ascii=False, indent=2)
        except Exception as exc:
            logger.warning("재무 캐시 저장 실패: %s", exc)


class MarketRegimeFilter:
    @property
    def start_date(self) -> str:
        return (datetime.now() - timedelta(days=MARKET_REGIME_LOOKBACK_DAYS)).strftime("%Y-%m-%d")

    @property
    def end_date(self) -> str:
        return datetime.now().strftime("%Y-%m-%d")

    def analyze(self, index_code: str = MARKET_INDEX_CODE, label: str = "KOSPI") -> MarketRegime:
        logger.info("Market Regime Filter: %s 200일선 확인 시작", label)
        data = fdr.DataReader(index_code, self.start_date, self.end_date)
        if data.empty or "Close" not in data.columns:
            raise RuntimeError(f"{label} 지수 데이터를 수집하지 못했습니다.")

        close = data["Close"].dropna().astype(float)
        if len(close) < MARKET_REGIME_MA:
            raise RuntimeError(f"{label} 200일 이동평균 계산에 필요한 데이터가 부족합니다.")

        current = float(close.iloc[-1])
        ma200 = float(close.rolling(MARKET_REGIME_MA).mean().iloc[-1])
        volatility = annualized_volatility(close)
        return_20d = return_over_period(close, 20)
        return_60d = return_over_period(close, 60)
        return_120d = return_over_period(close, 120)
        risk_on = current >= ma200
        summary = (
            f"{label} {current:,.2f}, 200일선 {ma200:,.2f}, "
            f"시장 변동성 {volatility * 100:.1f}%, 60일 수익률 {return_60d:+.1f}%"
        )
        logger.info("%s, Risk-On=%s", summary, risk_on)
        return MarketRegime(
            index_code=index_code,
            current=current,
            ma200=ma200,
            volatility=volatility,
            risk_on=risk_on,
            summary=summary,
            return_20d=return_20d,
            return_60d=return_60d,
            return_120d=return_120d,
        )

    def analyze_by_market(self) -> Dict[str, MarketRegime]:
        return {
            "KOSPI": self.analyze(MARKET_INDEX_CODE, "KOSPI"),
            "KOSDAQ": self.analyze(KOSDAQ_MARKET_INDEX_CODE, "KOSDAQ150"),
        }

    @staticmethod
    def select_for_market(market: str, regimes: Dict[str, MarketRegime]) -> MarketRegime:
        return regimes.get(market, regimes.get("KOSPI") or next(iter(regimes.values())))


class KISDataProvider:
    TOKEN_PATH = "/oauth2/tokenP"
    HASHKEY_PATH = "/uapi/hashkey"
    DAILY_PRICE_PATH = "/uapi/domestic-stock/v1/quotations/inquire-daily-itemchartprice"
    CURRENT_PRICE_PATH = "/uapi/domestic-stock/v1/quotations/inquire-price"
    ORDER_CASH_PATH = "/uapi/domestic-stock/v1/trading/order-cash"
    BUYABLE_ORDER_PATH = "/uapi/domestic-stock/v1/trading/inquire-psbl-order"

    def __init__(self) -> None:
        load_dotenv()
        self.app_key = KIS_APP_KEY or os.getenv("KIS_APP_KEY", "")
        self.app_secret = KIS_APP_SECRET or os.getenv("KIS_APP_SECRET", "")
        self.base_url = os.getenv("KIS_BASE_URL", KIS_BASE_URL).rstrip("/")
        self.trading_env = normalize_trading_env(os.getenv("KIS_TRADING_ENV", KIS_TRADING_ENV))
        account_no = KIS_ACCOUNT_NO or os.getenv("KIS_ACCOUNT_NO", "")
        account_product_code = KIS_ACCOUNT_PRODUCT_CODE or os.getenv("KIS_ACCOUNT_PRODUCT_CODE", "01")
        self.account_no, self.account_product_code = normalize_kis_account(account_no, account_product_code)
        self.session = requests.Session()

    @property
    def enabled(self) -> bool:
        return bool(self.app_key and self.app_secret)

    @property
    def trading_ready(self) -> bool:
        return bool(self.enabled and self.account_no and self.account_product_code)

    def fetch_daily_price(self, code: str, start_date: str, end_date: str) -> pd.DataFrame:
        if not self.enabled:
            raise RuntimeError("KIS_APP_KEY 또는 KIS_APP_SECRET이 설정되지 않았습니다.")

        rows: List[object] = []
        for chunk_start, chunk_end in date_chunks(start_date, end_date, KIS_DAILY_CHUNK_DAYS):
            rows.extend(self._fetch_daily_price_rows(code, chunk_start, chunk_end))
            time.sleep(REQUEST_DELAY_SECONDS)

        if not rows:
            raise ValueError(f"{code} KIS 일봉 데이터가 비어 있습니다.")

        records = []
        for row in rows:
            records.append(
                {
                    "Date": pd.to_datetime(str(row.get("stck_bsop_date")), format="%Y%m%d", errors="coerce"),
                    "Open": to_float(row.get("stck_oprc")),
                    "High": to_float(row.get("stck_hgpr")),
                    "Low": to_float(row.get("stck_lwpr")),
                    "Close": to_float(row.get("stck_clpr")),
                    "Volume": to_float(row.get("acml_vol")),
                    "Amount": to_float(row.get("acml_tr_pbmn")),
                }
            )

        data = pd.DataFrame(records).dropna(subset=["Date", "Open", "High", "Low", "Close"])
        if data.empty:
            raise ValueError(f"{code} KIS 일봉 데이터 파싱 결과가 비어 있습니다.")

        data = data.drop_duplicates(subset=["Date"]).set_index("Date").sort_index()
        return data[["Open", "High", "Low", "Close", "Volume", "Amount"]]

    def _fetch_daily_price_rows(self, code: str, start_date: str, end_date: str) -> List[object]:
        last_error: Optional[Exception] = None
        for adjusted_price in ("1", "0"):
            try:
                payload = self._get(
                    path=self.DAILY_PRICE_PATH,
                    tr_id="FHKST03010100",
                    params={
                        "FID_COND_MRKT_DIV_CODE": "J",
                        "FID_INPUT_ISCD": code,
                        "FID_INPUT_DATE_1": compact_date(start_date),
                        "FID_INPUT_DATE_2": compact_date(end_date),
                        "FID_PERIOD_DIV_CODE": "D",
                        "FID_ORG_ADJ_PRC": adjusted_price,
                    },
                )
                return list(payload.get("output2") or [])
            except Exception as exc:
                last_error = exc

        start = datetime.strptime(start_date, "%Y-%m-%d")
        end = datetime.strptime(end_date, "%Y-%m-%d")
        if start >= end:
            logger.debug("%s KIS 일봉 단일 날짜 조회 실패: %s, %s", code, start_date, last_error)
            return []

        midpoint = start + ((end - start) / 2)
        left_end = midpoint.strftime("%Y-%m-%d")
        right_start = (midpoint + timedelta(days=1)).strftime("%Y-%m-%d")
        logger.debug("%s KIS 일봉 구간 재시도: %s~%s", code, start_date, end_date)
        return self._fetch_daily_price_rows(code, start_date, left_end) + self._fetch_daily_price_rows(
            code,
            right_start,
            end_date,
        )

    def fetch_current_price(self, code: str) -> Dict[str, Optional[float]]:
        if not self.enabled:
            raise RuntimeError("KIS_APP_KEY 또는 KIS_APP_SECRET이 설정되지 않았습니다.")

        payload = self._get(
            path=self.CURRENT_PRICE_PATH,
            tr_id="FHKST01010100",
            params={
                "FID_COND_MRKT_DIV_CODE": "J",
                "FID_INPUT_ISCD": code,
            },
        )
        output = payload.get("output") or {}
        return {
            "current_price": to_float(output.get("stck_prpr")),
            "volume": to_float(output.get("acml_vol")),
            "trading_value": to_float(output.get("acml_tr_pbmn")),
            "change_rate": to_float(output.get("prdy_ctrt")),
            "change_amount": to_float(output.get("prdy_vrss")),
            "open": to_float(output.get("stck_oprc")),
            "high": to_float(output.get("stck_hgpr")),
            "low": to_float(output.get("stck_lwpr")),
            "upper_limit": to_float(output.get("stck_mxpr")),
            "lower_limit": to_float(output.get("stck_llam")),
            "margin_rate": to_float(output.get("marg_rate")),
            "vi_status": str(output.get("vi_cls_code") or output.get("vi_cls") or "").strip(),
        }

    def fetch_buyable_order(self, code: str, price: float, order_type: str = "01") -> Dict[str, object]:
        if not self.trading_ready:
            raise RuntimeError("KIS 계좌번호 또는 API 키가 설정되지 않았습니다.")

        params = {
            "CANO": self.account_no,
            "ACNT_PRDT_CD": self.account_product_code,
            "PDNO": code,
            "ORD_UNPR": str(int(price)),
            "ORD_DVSN": order_type,
            "CMA_EVLU_AMT_ICLD_YN": "N",
            "OVRS_ICLD_YN": "N",
        }
        retry_order_types = [order_type]
        if self.trading_env == "demo":
            retry_order_types.extend(order for order in ("00", "01") if order != order_type)

        last_error: Optional[Exception] = None
        for retry_order_type in retry_order_types:
            params["ORD_DVSN"] = retry_order_type
            try:
                payload = self._get(
                    path=self.BUYABLE_ORDER_PATH,
                    tr_id=self._buyable_order_tr_id(),
                    params=params,
                )
                break
            except Exception as exc:
                last_error = exc
                if retry_order_type != retry_order_types[-1]:
                    logger.warning("%s 모의 매수가능조회 %s 실패, 다른 주문구분 재조회", code, retry_order_type)
                    time.sleep(max(REQUEST_DELAY_SECONDS, 0.5))
        else:
            raise RuntimeError(f"KIS 매수가능조회 실패: {last_error}") from last_error

        output = payload.get("output") or {}
        return output if isinstance(output, dict) else {}

    def place_cash_order(
        self,
        side: str,
        code: str,
        quantity: int,
        price: float,
        order_type: str = "01",
        exchange: str = "KRX",
        use_hashkey: bool = True,
    ) -> Dict[str, object]:
        if not self.trading_ready:
            raise RuntimeError("KIS 계좌번호 또는 API 키가 설정되지 않았습니다.")
        if side not in {"buy", "sell"}:
            raise ValueError("side는 buy 또는 sell이어야 합니다.")
        if quantity <= 0:
            raise ValueError("주문 수량은 1주 이상이어야 합니다.")

        order_price = 0 if order_type == "01" else int(price)
        body = {
            "CANO": self.account_no,
            "ACNT_PRDT_CD": self.account_product_code,
            "PDNO": code,
            "ORD_DVSN": order_type,
            "ORD_QTY": str(int(quantity)),
            "ORD_UNPR": str(order_price),
            "EXCG_ID_DVSN_CD": exchange,
            "SLL_TYPE": "01" if side == "sell" else "",
            "CNDT_PRIC": "",
        }
        return self._post(
            path=self.ORDER_CASH_PATH,
            tr_id=self._cash_order_tr_id(side),
            body=body,
            include_hashkey=use_hashkey,
        )

    def _get(self, path: str, tr_id: str, params: Dict[str, str]) -> Dict[str, object]:
        token = self._get_access_token()
        response = self._request_with_retry(
            "GET",
            path,
            headers=self._build_headers(token=token, tr_id=tr_id),
            params=params,
            timeout=20,
        )
        self._raise_for_status(response, path)
        return self._validate_payload(response.json())

    def _post(
        self,
        path: str,
        tr_id: str,
        body: Dict[str, str],
        include_hashkey: bool = False,
    ) -> Dict[str, object]:
        token = self._get_access_token()
        headers = self._build_headers(token=token, tr_id=tr_id)
        if include_hashkey:
            headers["hashkey"] = self._create_hashkey(token, body)

        response = self._request_with_retry(
            "POST",
            path,
            allow_retry=(path != self.ORDER_CASH_PATH),
            headers=headers,
            json=body,
            timeout=20,
        )
        self._raise_for_status(response, path)
        return self._validate_payload(response.json())

    def _create_hashkey(self, token: str, body: Dict[str, str]) -> str:
        response = self._request_with_retry(
            "POST",
            self.HASHKEY_PATH,
            headers=self._build_headers(token=token, tr_id=""),
            json=body,
            timeout=20,
        )
        self._raise_for_status(response, self.HASHKEY_PATH)
        payload = response.json()
        hashkey = payload.get("HASH")
        if not hashkey:
            raise RuntimeError(f"KIS hashkey 발급 실패: {payload}")
        return str(hashkey)

    def _request_with_retry(
        self,
        method: str,
        path: str,
        allow_retry: bool = True,
        **kwargs,
    ) -> requests.Response:
        max_retries = env_int("KIS_MAX_RETRIES", KIS_MAX_RETRIES) if allow_retry else 0
        retry_delay = env_float("KIS_RETRY_DELAY_SECONDS", KIS_RETRY_DELAY_SECONDS)
        retry_statuses = {429, 500, 502, 503, 504}

        for attempt in range(max_retries + 1):
            response = self.session.request(method, f"{self.base_url}{path}", **kwargs)
            if response.status_code not in retry_statuses or attempt >= max_retries:
                return response
            wait_seconds = retry_delay * (attempt + 1)
            logger.warning(
                "KIS %s %s HTTP %s, %.1f초 후 재시도(%d/%d)",
                method,
                path,
                response.status_code,
                wait_seconds,
                attempt + 1,
                max_retries,
            )
            time.sleep(wait_seconds)
        return response

    def _build_headers(self, token: str, tr_id: str) -> Dict[str, str]:
        headers = {
            "content-type": "application/json",
            "authorization": f"Bearer {token}",
            "appkey": self.app_key,
            "appsecret": self.app_secret,
            "custtype": "P",
        }
        if tr_id:
            headers["tr_id"] = tr_id
        return headers

    @staticmethod
    def _validate_payload(payload: Dict[str, object]) -> Dict[str, object]:
        if str(payload.get("rt_cd", "0")) != "0":
            raise RuntimeError(f"KIS API 오류 {payload.get('msg_cd')}: {payload.get('msg1')}")
        return payload

    @staticmethod
    def _raise_for_status(response: requests.Response, path: str) -> None:
        try:
            response.raise_for_status()
        except requests.HTTPError:
            raise RuntimeError(f"KIS HTTP {response.status_code} error: {path}") from None

    def _cash_order_tr_id(self, side: str) -> str:
        if self.trading_env == "real":
            return "TTTC0012U" if side == "buy" else "TTTC0011U"
        return "VTTC0012U" if side == "buy" else "VTTC0011U"

    def _buyable_order_tr_id(self) -> str:
        return "TTTC8908R" if self.trading_env == "real" else "VTTC8908R"

    def _get_access_token(self) -> str:
        cached_token = self._load_cached_token()
        if cached_token:
            return cached_token

        response = self.session.post(
            f"{self.base_url}{self.TOKEN_PATH}",
            headers={"content-type": "application/json"},
            json={
                "grant_type": "client_credentials",
                "appkey": self.app_key,
                "appsecret": self.app_secret,
            },
            timeout=20,
        )
        response.raise_for_status()
        payload = response.json()
        token = payload.get("access_token")
        if not token:
            raise RuntimeError(f"KIS 접근토큰 발급 실패: {payload}")

        expires_at = datetime.now() + timedelta(seconds=int(payload.get("expires_in", 86400)) - 300)
        self._save_cached_token(str(token), expires_at)
        return str(token)

    def _load_cached_token(self) -> Optional[str]:
        if not KIS_TOKEN_CACHE_FILE.exists():
            return None
        try:
            with KIS_TOKEN_CACHE_FILE.open("r", encoding="utf-8") as file:
                data = json.load(file)
            if data.get("base_url") != self.base_url and data.get("base_url"):
                return None
            expires_at = datetime.fromisoformat(str(data.get("expires_at")))
            if datetime.now() >= expires_at:
                return None
            token = data.get("access_token")
            return str(token) if token else None
        except Exception as exc:
            logger.warning("KIS 토큰 캐시 로드 실패: %s", exc)
            return None

    def _save_cached_token(self, token: str, expires_at: datetime) -> None:
        try:
            CACHE_DIR.mkdir(exist_ok=True)
            with KIS_TOKEN_CACHE_FILE.open("w", encoding="utf-8") as file:
                json.dump(
                    {
                        "access_token": token,
                        "expires_at": expires_at.isoformat(timespec="seconds"),
                        "base_url": self.base_url,
                    },
                    file,
                    ensure_ascii=False,
                    indent=2,
                )
        except Exception as exc:
            logger.warning("KIS 토큰 캐시 저장 실패: %s", exc)


class AccumulationAnalyzer:
    NAVER_URL = "https://finance.naver.com/item/frgn.naver"
    USER_AGENT = "Mozilla/5.0"

    def analyze(self, stock_meta: StockMeta) -> Optional[AccumulationSnapshot]:
        if not stock_meta.shares or stock_meta.shares <= 0:
            logger.warning("%s(%s) 상장주식수 데이터가 없어 수급 분석 제외", stock_meta.name, stock_meta.code)
            return None

        try:
            investor_data = self._fetch_investor_data(stock_meta.code)
            data_quality = self._validate_investor_data(investor_data)
            if not data_quality.passed:
                raise ValueError(
                    f"수급 데이터 품질 미달: {data_quality.score:.1f}/100, "
                    f"{'; '.join(data_quality.warnings)}"
                )
            if len(investor_data) < ACCUMULATION_LOOKBACK_DAYS:
                raise ValueError(f"20일 수급 분석에 필요한 데이터 부족: {len(investor_data)}일")

            recent = investor_data.head(ACCUMULATION_LOOKBACK_DAYS).copy()
            combined = recent["foreign_net_buy"] + recent["institutional_net_buy"]
            foreign_amount = recent["foreign_net_buy"] * recent["close"]
            institutional_amount = recent["institutional_net_buy"] * recent["close"]
            combined_amount = foreign_amount + institutional_amount
            combined_net_buy = float(combined.sum())
            foreign_net_buy = float(recent["foreign_net_buy"].sum())
            institutional_net_buy = float(recent["institutional_net_buy"].sum())
            foreign_net_buy_amount = float(foreign_amount.sum())
            institutional_net_buy_amount = float(institutional_amount.sum())
            combined_net_buy_amount = float(combined_amount.sum())
            positive_days = int((combined > 0).sum())
            net_buy_ratio = combined_net_buy / stock_meta.shares
            net_buy_amount_to_market_cap = (
                combined_net_buy_amount / stock_meta.market_cap
                if stock_meta.market_cap and stock_meta.market_cap > 0
                else None
            )
            net_buy_amount_to_trading_value = (
                combined_net_buy_amount / stock_meta.trading_value
                if stock_meta.trading_value and stock_meta.trading_value > 0
                else None
            )

            latest_close = float(recent.iloc[0]["close"])
            oldest_close = float(recent.iloc[-1]["close"])
            if oldest_close <= 0:
                raise ValueError("20일 전 종가가 0 이하입니다.")
            price_change = latest_close / oldest_close - 1

            if combined_net_buy <= 0:
                return None
            if net_buy_ratio < MIN_ACCUMULATION_RATIO:
                return None
            if positive_days < MIN_ACCUMULATION_POSITIVE_DAYS:
                return None
            if (
                net_buy_amount_to_market_cap is not None
                and net_buy_amount_to_market_cap < MIN_ACCUMULATION_AMOUNT_TO_MARKET_CAP
            ):
                return None
            if abs(price_change) > MAX_SIDEWAYS_PRICE_CHANGE:
                return None

            summary = (
                f"최근 {ACCUMULATION_LOOKBACK_DAYS}일 외국인/기관 합산 순매수 "
                f"{combined_net_buy:,.0f}주, 상장주식수 대비 {net_buy_ratio * 100:.2f}%, "
                f"순매수금액 {combined_net_buy_amount / 100_000_000:.1f}억 원, "
                f"시총 대비 {(net_buy_amount_to_market_cap or 0) * 100:.2f}%, "
                f"양수급 {positive_days}/{ACCUMULATION_LOOKBACK_DAYS}일"
            )
            return AccumulationSnapshot(
                days=ACCUMULATION_LOOKBACK_DAYS,
                foreign_net_buy=foreign_net_buy,
                institutional_net_buy=institutional_net_buy,
                combined_net_buy=combined_net_buy,
                net_buy_ratio=net_buy_ratio,
                positive_days=positive_days,
                price_change=price_change,
                summary=summary,
                foreign_net_buy_amount=foreign_net_buy_amount,
                institutional_net_buy_amount=institutional_net_buy_amount,
                combined_net_buy_amount=combined_net_buy_amount,
                net_buy_amount_to_market_cap=net_buy_amount_to_market_cap,
                net_buy_amount_to_trading_value=net_buy_amount_to_trading_value,
                data_quality_score=data_quality.score,
                data_quality_grade=data_quality.grade,
                data_quality_warnings=data_quality.warnings,
            )
        except Exception as exc:
            logger.warning("%s(%s) 수급 분석 실패: %s", stock_meta.name, stock_meta.code, exc)
            return None

    def _fetch_investor_data(self, code: str) -> pd.DataFrame:
        frames: List[pd.DataFrame] = []

        for page in range(1, ACCUMULATION_PAGES + 1):
            response = requests.get(
                self.NAVER_URL,
                params={"code": code, "page": page},
                headers={"User-Agent": self.USER_AGENT},
                timeout=20,
            )
            response.raise_for_status()
            tables = pd.read_html(StringIO(response.text))
            table = self._find_investor_table(tables)
            frames.append(table)
            if sum(len(frame) for frame in frames) >= ACCUMULATION_LOOKBACK_DAYS:
                break
            time.sleep(0.05)

        if not frames:
            raise ValueError("네이버 수급 테이블을 찾지 못했습니다.")

        data = pd.concat(frames, ignore_index=True)
        data = data.drop_duplicates(subset=["date"]).sort_values("date", ascending=False)
        return data

    @staticmethod
    def _validate_investor_data(data: pd.DataFrame) -> DataQualityReport:
        score = 100.0
        checks: List[str] = []
        warnings: List[str] = []

        if data is None or data.empty:
            return DataQualityValidator._report("Naver Finance 수급", 0.0, checks, ["수급 데이터가 비어 있습니다."])

        required = {"date", "close", "institutional_net_buy", "foreign_net_buy"}
        missing = sorted(required - set(data.columns))
        if missing:
            return DataQualityValidator._report(
                "Naver Finance 수급",
                0.0,
                checks,
                [f"수급 필수 컬럼 누락: {', '.join(missing)}"],
            )

        frame = data.copy()
        frame["date"] = pd.to_datetime(frame["date"], errors="coerce")
        frame = frame.dropna(subset=["date", "close", "institutional_net_buy", "foreign_net_buy"])
        if len(frame) < ACCUMULATION_LOOKBACK_DAYS:
            score -= 45.0
            warnings.append(f"수급 유효 데이터 부족: {len(frame)}일")
        else:
            checks.append(f"수급 유효 데이터 {len(frame)}일")

        latest_date = frame["date"].max() if not frame.empty else None
        if latest_date is not None:
            stale_days = (datetime.now().date() - latest_date.date()).days
            max_staleness_days = env_int("MAX_INVESTOR_DATA_STALENESS_DAYS", MAX_INVESTOR_DATA_STALENESS_DAYS)
            if stale_days > max_staleness_days:
                score -= min(40.0, (stale_days - max_staleness_days) * 6.0)
                warnings.append(f"최신 수급 데이터 지연 {stale_days}일")
            else:
                checks.append(f"최신 수급 데이터 {latest_date.strftime('%Y-%m-%d')}")

        close = pd.to_numeric(frame["close"], errors="coerce")
        if close.dropna().empty or float((close <= 0).mean()) > 0:
            score -= 30.0
            warnings.append("수급 테이블 종가 비정상값 포함")

        duplicate_dates = int(frame["date"].duplicated().sum())
        if duplicate_dates:
            score -= min(15.0, duplicate_dates / max(len(frame), 1) * 100)
            warnings.append(f"수급 중복 날짜 {duplicate_dates}건")
        else:
            checks.append("수급 중복 날짜 없음")

        return DataQualityValidator._report("Naver Finance 수급", score, checks, warnings)

    def _find_investor_table(self, tables: List[pd.DataFrame]) -> pd.DataFrame:
        for table in tables:
            normalized = self._normalize_investor_columns(table)
            required = {"date", "close", "institutional_net_buy", "foreign_net_buy"}
            if required.issubset(normalized.columns):
                normalized = normalized.dropna(subset=["date", "close", "institutional_net_buy", "foreign_net_buy"])
                if not normalized.empty:
                    return normalized
        raise ValueError("외국인/기관 순매매 테이블을 찾지 못했습니다.")

    @staticmethod
    def _normalize_investor_columns(table: pd.DataFrame) -> pd.DataFrame:
        table = table.copy()
        flat_columns: List[str] = []
        for column in table.columns:
            if isinstance(column, tuple):
                parts = [str(part) for part in column if str(part) != "nan"]
                if len(parts) >= 2 and parts[0] != parts[-1]:
                    flat_columns.append("_".join(parts))
                else:
                    flat_columns.append(parts[0] if parts else "")
            else:
                flat_columns.append(str(column))

        table.columns = flat_columns
        rename_map: Dict[str, str] = {}
        for column in table.columns:
            if column.startswith("날짜"):
                rename_map[column] = "date"
            elif column.startswith("종가"):
                rename_map[column] = "close"
            elif column.startswith("기관") and "순매매" in column:
                rename_map[column] = "institutional_net_buy"
            elif column.startswith("외국인") and "순매매" in column:
                rename_map[column] = "foreign_net_buy"

        table = table.rename(columns=rename_map)
        keep_columns = [column for column in ["date", "close", "institutional_net_buy", "foreign_net_buy"] if column in table.columns]
        table = table[keep_columns].copy()
        if "date" in table.columns:
            table["date"] = pd.to_datetime(table["date"], format="%Y.%m.%d", errors="coerce")
        for column in ["close", "institutional_net_buy", "foreign_net_buy"]:
            if column in table.columns:
                table[column] = pd.to_numeric(table[column], errors="coerce")
        return table


class TechnicalAnalyzer:
    def __init__(self, kis_provider: Optional[KISDataProvider] = None) -> None:
        self.kis_provider = kis_provider or KISDataProvider()

    @property
    def start_date(self) -> str:
        return (datetime.now() - timedelta(days=LOOKBACK_DAYS)).strftime("%Y-%m-%d")

    @property
    def end_date(self) -> str:
        return datetime.now().strftime("%Y-%m-%d")

    def analyze(
        self,
        stock_meta: StockMeta,
        market_regime: MarketRegime,
        mode: str = "strict",
    ) -> Optional[TechnicalSnapshot]:
        try:
            data, source_quality = self._fetch_price_data(stock_meta.code)
            if data.empty:
                raise ValueError("가격 데이터가 비어 있습니다.")
            if not self._quality_passed_for_mode(source_quality, mode):
                raise ValueError(
                    f"가격 데이터 품질 미달: {source_quality.score:.1f}/100, "
                    f"{'; '.join(source_quality.warnings)}"
                )

            required_columns = {"High", "Low", "Close"}
            missing_columns = required_columns - set(data.columns)
            if missing_columns:
                raise ValueError(f"필수 가격 컬럼 누락: {', '.join(sorted(missing_columns))}")

            columns = ["High", "Low", "Close"]
            if "Volume" in data.columns:
                columns.append("Volume")
            prices = data[columns].dropna().copy()
            if len(prices) < MIN_HISTORY_DAYS:
                raise ValueError(f"분석에 필요한 가격 데이터 부족: {len(prices)}일")

            prices["MA20"] = prices["Close"].rolling(MA_SHORT).mean()
            prices["MA60"] = prices["Close"].rolling(MA_LONG).mean()
            if "Volume" in prices.columns:
                prices["AVG_VOLUME20"] = prices["Volume"].rolling(MA_SHORT).mean()
            else:
                prices["AVG_VOLUME20"] = 0.0
            prices["RSI"] = RSIIndicator(close=prices["Close"], window=RSI_WINDOW).rsi()
            prices["ATR"] = AverageTrueRange(
                high=prices["High"],
                low=prices["Low"],
                close=prices["Close"],
                window=ATR_WINDOW,
            ).average_true_range()
            prices = prices.dropna()
            if len(prices) < 6:
                raise ValueError("이동평균/RSI 계산 후 데이터가 부족합니다.")
            indicator_quality = DataQualityValidator.validate_price_frame(
                prices,
                f"{source_quality.source} 지표계산",
                min_rows=max(6, MIN_HISTORY_DAYS - MA_LONG),
            )
            data_quality = DataQualityValidator.merge_reports(
                source_quality.source,
                [source_quality, indicator_quality],
                weights=[0.75, 0.25],
            )
            if not self._quality_passed_for_mode(data_quality, mode):
                raise ValueError(
                    f"지표 계산 데이터 품질 미달: {data_quality.score:.1f}/100, "
                    f"{'; '.join(data_quality.warnings)}"
                )

            latest = prices.iloc[-1]
            previous = prices.iloc[-2]
            five_days_ago = prices.iloc[-6]

            current_price = float(latest["Close"])
            previous_close = float(previous["Close"])
            ma20 = float(latest["MA20"])
            ma60 = float(latest["MA60"])
            rsi = float(latest["RSI"])
            atr = float(latest["ATR"])
            volume = float(latest.get("Volume", 0.0))
            avg_volume20 = float(latest.get("AVG_VOLUME20", 0.0))
            stop_loss = max(0.0, current_price - (ATR_STOP_MULTIPLIER * atr))
            volatility = annualized_volatility(prices["Close"])
            close = prices["Close"].astype(float)
            return_20d = return_over_period(close, 20)
            return_60d = return_over_period(close, 60)
            return_120d = return_over_period(close, 120)
            max_drawdown_60d = max_drawdown(close.tail(60))
            momentum_120_20d = return_between_periods(close, 120, 20)
            high_window = close.tail(min(len(close), 180))
            high_180d = float(high_window.max()) if not high_window.empty else current_price
            low_180d = float(high_window.min()) if not high_window.empty else current_price
            high_proximity_180d = current_price / high_180d * 100 if high_180d > 0 else 0.0
            distance_to_180d_high_pct = (high_180d / current_price - 1) * 100 if current_price > 0 else 0.0
            target_price = max(high_180d, ma20 + atr * 3.0)
            downside = max(current_price - stop_loss, 1.0)
            risk_reward_ratio = max(0.0, (target_price - current_price) / downside)
            relative_strength_60d = return_60d - market_regime.return_60d
            ma20_rising = ma20 > float(five_days_ago["MA20"])
            ma20_support = ma20 * (1 - MA_SUPPORT_BAND) <= current_price <= ma20 * (1 + MAX_DISTANCE_ABOVE_MA20)
            medium_uptrend = ma20 > ma60
            rsi_entry_zone = MIN_RSI <= rsi <= MAX_RSI
            low_volatility = volatility <= market_regime.volatility * MAX_RELATIVE_VOLATILITY
            relative_strength_ok = relative_strength_60d >= env_float_profile(
                "MIN_RELATIVE_STRENGTH_60D",
                MIN_RELATIVE_STRENGTH_60D,
                {"conservative": 3.0, "institutional": 1.0, "balanced": 0.0, "aggressive": -3.0},
            )
            return_quality_ok = (
                return_20d >= env_float("MIN_RETURN_20D", MIN_RETURN_20D)
                and return_20d <= env_float("MAX_RETURN_20D", MAX_RETURN_20D)
                and return_120d <= env_float("MAX_RETURN_120D", MAX_RETURN_120D)
                and max_drawdown_60d <= env_float("MAX_DRAWDOWN_60D", MAX_DRAWDOWN_60D)
            )
            momentum_durability_ok = (
                momentum_120_20d
                >= env_float_profile(
                    "MIN_INTERMEDIATE_MOMENTUM_120_20D",
                    MIN_INTERMEDIATE_MOMENTUM_120_20D,
                    {"conservative": 0.0, "institutional": -2.0, "balanced": -5.0, "aggressive": -10.0},
                )
                and high_proximity_180d
                >= env_float_profile(
                    "MIN_HIGH_PROXIMITY_180D",
                    MIN_HIGH_PROXIMITY_180D,
                    {"conservative": 72.0, "institutional": 68.0, "balanced": 65.0, "aggressive": 58.0},
                )
                and high_proximity_180d <= env_float("MAX_HIGH_PROXIMITY_180D", MAX_HIGH_PROXIMITY_180D)
                and risk_reward_ratio
                >= env_float_profile(
                    "MIN_RISK_REWARD_RATIO",
                    MIN_RISK_REWARD_RATIO,
                    {"conservative": 1.35, "institutional": 1.15, "balanced": 1.0, "aggressive": 0.8},
                )
            )

            strict_passed = (
                ma20_support
                and ma20_rising
                and medium_uptrend
                and rsi_entry_zone
                and low_volatility
                and relative_strength_ok
                and return_quality_ok
                and momentum_durability_ok
            )
            watchlist_passed = self._watchlist_technical_passed(
                current_price=current_price,
                ma20=ma20,
                ma60=ma60,
                ma20_rising=ma20_rising,
                rsi=rsi,
                volatility=volatility,
                market_regime=market_regime,
                relative_strength_60d=relative_strength_60d,
                return_20d=return_20d,
                return_120d=return_120d,
                max_drawdown_60d=max_drawdown_60d,
                momentum_120_20d=momentum_120_20d,
                high_proximity_180d=high_proximity_180d,
                risk_reward_ratio=risk_reward_ratio,
            )
            radar_passed = self._radar_technical_passed(
                current_price=current_price,
                ma20=ma20,
                ma60=ma60,
                rsi=rsi,
                volatility=volatility,
                market_regime=market_regime,
                relative_strength_60d=relative_strength_60d,
                return_20d=return_20d,
                return_120d=return_120d,
                max_drawdown_60d=max_drawdown_60d,
                momentum_120_20d=momentum_120_20d,
                high_proximity_180d=high_proximity_180d,
                risk_reward_ratio=risk_reward_ratio,
            )

            normalized_mode = mode.strip().lower()
            signal_stage = "strict"
            if normalized_mode == "strict":
                if not strict_passed:
                    return None
            elif normalized_mode == "watchlist":
                if not watchlist_passed:
                    return None
                signal_stage = "watchlist"
            elif normalized_mode == "tiered":
                if strict_passed:
                    signal_stage = "strict"
                elif watchlist_enabled() and watchlist_passed:
                    signal_stage = "watchlist"
                elif radar_enabled() and radar_passed:
                    signal_stage = "radar"
                else:
                    return None
            else:
                raise ValueError(f"알 수 없는 기술분석 모드: {mode}")

            if signal_stage == "watchlist":
                if current_price < ma20:
                    trend_summary = "관찰 후보: 20일선 아래에서 회복 대기"
                elif ma20 <= ma60:
                    trend_summary = "관찰 후보: 20일선 회복, 60일선 전환 확인 필요"
                else:
                    trend_summary = "관찰 후보: RSI 30~65 구간에서 추세 개선 감시"
            elif signal_stage == "radar":
                trend_summary = "레이더 후보: 조건 미성숙, 가격/거래량 회복 여부 추적"
            else:
                crossed_ma20 = float(previous["Close"]) <= float(previous["MA20"]) and current_price > ma20
                if crossed_ma20:
                    trend_summary = "RSI 진입권에서 20일 이동평균선 상향 돌파 중"
                else:
                    trend_summary = "RSI 40~55 구간에서 20일선 지지 확인"

            if signal_stage == "watchlist" and not watchlist_enabled():
                return None
            if signal_stage == "radar" and not radar_enabled():
                return None

            return TechnicalSnapshot(
                current_price=current_price,
                rsi=rsi,
                ma20=ma20,
                ma60=ma60,
                atr=atr,
                stop_loss=stop_loss,
                volatility=volatility,
                market_volatility=market_regime.volatility,
                trend_summary=trend_summary,
                previous_close=previous_close,
                volume=volume,
                avg_volume20=avg_volume20,
                return_20d=return_20d,
                return_60d=return_60d,
                return_120d=return_120d,
                market_return_60d=market_regime.return_60d,
                relative_strength_60d=relative_strength_60d,
                max_drawdown_60d=max_drawdown_60d,
                momentum_120_20d=momentum_120_20d,
                high_180d=high_180d,
                low_180d=low_180d,
                high_proximity_180d=high_proximity_180d,
                distance_to_180d_high_pct=distance_to_180d_high_pct,
                target_price=target_price,
                risk_reward_ratio=risk_reward_ratio,
                price_source=data_quality.source,
                data_quality_score=data_quality.score,
                data_quality_grade=data_quality.grade,
                data_quality_warnings=data_quality.warnings,
                signal_stage=signal_stage,
            )
        except Exception as exc:
            logger.warning("%s(%s) 기술적 분석 실패: %s", stock_meta.name, stock_meta.code, exc)
            return None

    @staticmethod
    def _quality_passed_for_mode(report: DataQualityReport, mode: str) -> bool:
        if not env_bool("STRICT_DATA_VALIDATION", STRICT_DATA_VALIDATION):
            return True
        if report.passed:
            return True
        normalized_mode = mode.strip().lower()
        if normalized_mode in {"watchlist", "tiered"}:
            return report.score >= watchlist_data_quality_min_score()
        return report.score >= data_quality_min_score()

    @staticmethod
    def _watchlist_technical_passed(
        current_price: float,
        ma20: float,
        ma60: float,
        ma20_rising: bool,
        rsi: float,
        volatility: float,
        market_regime: MarketRegime,
        relative_strength_60d: float,
        return_20d: float,
        return_120d: float,
        max_drawdown_60d: float,
        momentum_120_20d: float,
        high_proximity_180d: float,
        risk_reward_ratio: float,
    ) -> bool:
        if ma20 <= 0 or ma60 <= 0:
            return False
        price_near_ma20 = (
            ma20 * (1 - env_float("WATCHLIST_MA_SUPPORT_BAND", WATCHLIST_MA_SUPPORT_BAND))
            <= current_price
            <= ma20 * (1 + env_float("WATCHLIST_MAX_DISTANCE_ABOVE_MA20", WATCHLIST_MAX_DISTANCE_ABOVE_MA20))
        )
        trend_repairing = ma20_rising or ma20 >= ma60 * 0.97
        rsi_watch_zone = (
            env_float("WATCHLIST_MIN_RSI", WATCHLIST_MIN_RSI)
            <= rsi
            <= env_float("WATCHLIST_MAX_RSI", WATCHLIST_MAX_RSI)
        )
        market_volatility = market_regime.volatility or 0.0
        volatility_ok = (
            market_volatility <= 0
            or volatility <= market_volatility * env_float("WATCHLIST_MAX_RELATIVE_VOLATILITY", WATCHLIST_MAX_RELATIVE_VOLATILITY)
        )
        return_quality_ok = (
            return_20d >= env_float("WATCHLIST_MIN_RETURN_20D", WATCHLIST_MIN_RETURN_20D)
            and return_20d <= env_float("WATCHLIST_MAX_RETURN_20D", WATCHLIST_MAX_RETURN_20D)
            and return_120d <= env_float("WATCHLIST_MAX_RETURN_120D", WATCHLIST_MAX_RETURN_120D)
            and max_drawdown_60d <= env_float("WATCHLIST_MAX_DRAWDOWN_60D", WATCHLIST_MAX_DRAWDOWN_60D)
        )
        momentum_ok = (
            relative_strength_60d >= watchlist_relative_strength_minimum()
            and momentum_120_20d
            >= env_float("WATCHLIST_MIN_INTERMEDIATE_MOMENTUM_120_20D", WATCHLIST_MIN_INTERMEDIATE_MOMENTUM_120_20D)
            and high_proximity_180d >= env_float("WATCHLIST_MIN_HIGH_PROXIMITY_180D", WATCHLIST_MIN_HIGH_PROXIMITY_180D)
            and high_proximity_180d <= env_float("MAX_HIGH_PROXIMITY_180D", MAX_HIGH_PROXIMITY_180D)
            and risk_reward_ratio >= env_float("WATCHLIST_MIN_RISK_REWARD_RATIO", WATCHLIST_MIN_RISK_REWARD_RATIO)
        )
        return (
            price_near_ma20
            and trend_repairing
            and rsi_watch_zone
            and volatility_ok
            and return_quality_ok
            and momentum_ok
        )

    @staticmethod
    def _radar_technical_passed(
        current_price: float,
        ma20: float,
        ma60: float,
        rsi: float,
        volatility: float,
        market_regime: MarketRegime,
        relative_strength_60d: float,
        return_20d: float,
        return_120d: float,
        max_drawdown_60d: float,
        momentum_120_20d: float,
        high_proximity_180d: float,
        risk_reward_ratio: float,
    ) -> bool:
        if ma20 <= 0 or ma60 <= 0:
            return False
        price_near_ma20 = (
            ma20 * (1 - env_float("RADAR_MA_SUPPORT_BAND", RADAR_MA_SUPPORT_BAND))
            <= current_price
            <= ma20 * (1 + env_float("RADAR_MAX_DISTANCE_ABOVE_MA20", RADAR_MAX_DISTANCE_ABOVE_MA20))
        )
        rsi_zone = env_float("RADAR_MIN_RSI", RADAR_MIN_RSI) <= rsi <= env_float("RADAR_MAX_RSI", RADAR_MAX_RSI)
        market_volatility = market_regime.volatility or 0.0
        volatility_ok = (
            market_volatility <= 0
            or volatility <= market_volatility * env_float("RADAR_MAX_RELATIVE_VOLATILITY", RADAR_MAX_RELATIVE_VOLATILITY)
        )
        return_quality_ok = (
            return_20d >= env_float("RADAR_MIN_RETURN_20D", RADAR_MIN_RETURN_20D)
            and return_20d <= env_float("RADAR_MAX_RETURN_20D", RADAR_MAX_RETURN_20D)
            and return_120d <= env_float("RADAR_MAX_RETURN_120D", RADAR_MAX_RETURN_120D)
            and max_drawdown_60d <= env_float("RADAR_MAX_DRAWDOWN_60D", RADAR_MAX_DRAWDOWN_60D)
        )
        momentum_ok = (
            relative_strength_60d >= radar_relative_strength_minimum()
            and momentum_120_20d >= env_float("RADAR_MIN_INTERMEDIATE_MOMENTUM_120_20D", RADAR_MIN_INTERMEDIATE_MOMENTUM_120_20D)
            and high_proximity_180d >= env_float("RADAR_MIN_HIGH_PROXIMITY_180D", RADAR_MIN_HIGH_PROXIMITY_180D)
            and risk_reward_ratio >= env_float("RADAR_MIN_RISK_REWARD_RATIO", RADAR_MIN_RISK_REWARD_RATIO)
        )
        return price_near_ma20 and rsi_zone and volatility_ok and return_quality_ok and momentum_ok

    def _fetch_price_data(self, code: str) -> tuple[pd.DataFrame, DataQualityReport]:
        if self.kis_provider.enabled and env_bool("KIS_DAILY_PRICE_ENABLED", KIS_DAILY_PRICE_ENABLED):
            try:
                kis_data = self.kis_provider.fetch_daily_price(code, self.start_date, self.end_date)
                kis_quality = DataQualityValidator.validate_price_frame(kis_data, "KIS 일봉")
                if env_bool("ENABLE_PRICE_CROSSCHECK", ENABLE_PRICE_CROSSCHECK):
                    try:
                        fdr_data = fdr.DataReader(code, self.start_date, self.end_date)
                        fdr_quality = DataQualityValidator.validate_price_frame(fdr_data, "FDR 일봉")
                        cross_quality = DataQualityValidator.compare_price_sources(
                            kis_data,
                            fdr_data,
                            "KIS",
                            "FDR",
                        )
                        combined_quality = DataQualityValidator.merge_reports(
                            "KIS+FDR 가격",
                            [kis_quality, fdr_quality, cross_quality],
                            weights=[0.40, 0.35, 0.25],
                        )
                        if not cross_quality.passed and env_bool("STRICT_DATA_VALIDATION", STRICT_DATA_VALIDATION):
                            combined_quality.passed = False
                            combined_quality.warnings.insert(0, "KIS/FDR 가격 교차검증 실패")
                        if not kis_quality.passed and fdr_quality.passed and cross_quality.passed:
                            logger.debug("%s KIS 품질 미달로 FDR 일봉 데이터 사용", code)
                            return fdr_data, fdr_quality
                        kis_latest = latest_frame_date(kis_data)
                        fdr_latest = latest_frame_date(fdr_data)
                        if fdr_latest and kis_latest and fdr_latest > kis_latest and fdr_quality.passed:
                            combined_quality.warnings.insert(
                                0,
                                f"FDR가 KIS보다 최신입니다: FDR {fdr_latest.strftime('%Y-%m-%d')}, "
                                f"KIS {kis_latest.strftime('%Y-%m-%d')}",
                            )
                            combined_quality.score = round(max(0.0, combined_quality.score - 3.0), 1)
                            combined_quality.grade = quality_grade(combined_quality.score)
                            logger.debug("%s FDR 최신 거래일 우선으로 FDR 일봉 데이터 사용", code)
                            return fdr_data, combined_quality
                        logger.debug("%s KIS/FDR 교차검증 후 KIS 일봉 데이터 사용", code)
                        return kis_data, combined_quality
                    except Exception as cross_exc:
                        kis_quality.warnings.append(f"FDR 교차검증 실패: {cross_exc}")
                        kis_quality.score = round(max(0.0, kis_quality.score - 8.0), 1)
                        kis_quality.grade = quality_grade(kis_quality.score)
                logger.debug("%s KIS 일봉 데이터 사용", code)
                return kis_data, kis_quality
            except Exception as exc:
                logger.warning("%s KIS 일봉 데이터 실패, FDR fallback 사용: %s", code, exc)

        data = fdr.DataReader(code, self.start_date, self.end_date)
        quality = DataQualityValidator.validate_price_frame(data, "FDR 일봉")
        return data, quality


class FactorScorer:
    def score(self, report: DiscoveryReport, market_regime: MarketRegime) -> FactorScore:
        financial = self._financial_score(report.financials)
        accumulation = self._accumulation_score(report.accumulation)
        technical = self._technical_score(report.technicals)
        risk = self._risk_score(report, market_regime)
        total = financial + accumulation + technical + risk
        grade = self._grade(total)
        notes = self._notes(report)
        return FactorScore(
            financial=round(financial, 1),
            accumulation=round(accumulation, 1),
            technical=round(technical, 1),
            risk=round(risk, 1),
            total=round(total, 1),
            grade=grade,
            notes=notes,
        )

    @staticmethod
    def _financial_score(metrics: FinancialMetrics) -> float:
        score = 0.0
        score += clamp((MAX_PBR - metrics.pbr) / MAX_PBR * 7.0, 0.0, 7.0)
        score += clamp((MAX_DEBT_TO_EQUITY - metrics.debt_to_equity) / MAX_DEBT_TO_EQUITY * 6.0, 0.0, 6.0)
        score += clamp((metrics.current_ratio - 100.0) / 200.0 * 4.0, 0.0, 4.0)
        if metrics.roe is not None:
            score += clamp(metrics.roe / 15.0 * 6.0, 0.0, 6.0)
        else:
            score += 3.0
        if metrics.operating_margin is not None:
            score += clamp(metrics.operating_margin / 12.0 * 4.0, 0.0, 4.0)
        else:
            score += 2.0
        if metrics.revenue_growth_yoy is not None:
            score += clamp((metrics.revenue_growth_yoy + 5.0) / 20.0 * 3.0, 0.0, 3.0)
        else:
            score += 1.5
        return clamp(score, 0.0, 30.0)

    @staticmethod
    def _accumulation_score(accumulation: Optional[AccumulationSnapshot]) -> float:
        if accumulation is None:
            return 0.0
        score = 0.0
        score += clamp(accumulation.net_buy_ratio / 0.01 * 7.0, 0.0, 7.0)
        if accumulation.net_buy_amount_to_market_cap is not None:
            score += clamp(accumulation.net_buy_amount_to_market_cap / 0.005 * 7.0, 0.0, 7.0)
        score += clamp(accumulation.positive_days / ACCUMULATION_LOOKBACK_DAYS * 5.0, 0.0, 5.0)
        score += clamp((MAX_SIDEWAYS_PRICE_CHANGE - abs(accumulation.price_change)) / MAX_SIDEWAYS_PRICE_CHANGE * 4.0, 0.0, 4.0)
        if accumulation.combined_net_buy_amount > 0:
            leader = max(abs(accumulation.foreign_net_buy_amount), abs(accumulation.institutional_net_buy_amount))
            balance = leader / max(abs(accumulation.combined_net_buy_amount), 1.0)
            score += 2.0 if balance < 0.85 else 1.0
        return clamp(score, 0.0, 25.0)

    @staticmethod
    def _technical_score(technicals: TechnicalSnapshot) -> float:
        score = 0.0
        score += clamp((15.0 - abs(technicals.rsi - 45.0)) / 15.0 * 4.0, 0.0, 4.0)
        ma_spread = technicals.ma20 / technicals.ma60 - 1 if technicals.ma60 > 0 else 0.0
        score += clamp(ma_spread / 0.10 * 4.0, 0.0, 4.0)
        ma_distance = abs(technicals.current_price / technicals.ma20 - 1) if technicals.ma20 > 0 else 1.0
        score += clamp((MAX_DISTANCE_ABOVE_MA20 - ma_distance) / MAX_DISTANCE_ABOVE_MA20 * 3.0, 0.0, 3.0)
        volume_ratio = technicals.volume / technicals.avg_volume20 if technicals.avg_volume20 > 0 else 1.0
        score += clamp(volume_ratio / 2.0 * 2.5, 0.0, 2.5)
        score += clamp((technicals.relative_strength_60d + 5.0) / 20.0 * 4.0, 0.0, 4.0)
        drawdown_limit = max(1.0, env_float("MAX_DRAWDOWN_60D", MAX_DRAWDOWN_60D))
        score += clamp((drawdown_limit - technicals.max_drawdown_60d) / drawdown_limit * 2.0, 0.0, 2.0)
        score += clamp((technicals.momentum_120_20d + 5.0) / 25.0 * 2.5, 0.0, 2.5)
        score += clamp((technicals.high_proximity_180d - 60.0) / 35.0 * 2.0, 0.0, 2.0)
        score += clamp(technicals.risk_reward_ratio / 2.0 * 2.0, 0.0, 2.0)
        score += 1.0 if "상향 돌파" in technicals.trend_summary else 0.5
        return clamp(score, 0.0, 25.0)

    @staticmethod
    def _risk_score(report: DiscoveryReport, market_regime: MarketRegime) -> float:
        technicals = report.technicals
        score = 0.0
        if market_regime.risk_on:
            score += 3.0
        if market_regime.volatility > 0:
            score += clamp((1.3 - technicals.volatility / market_regime.volatility) / 1.3 * 7.0, 0.0, 7.0)
        risk_pct = (
            (technicals.current_price - technicals.stop_loss) / technicals.current_price
            if technicals.current_price > 0
            else 1.0
        )
        score += clamp((0.12 - risk_pct) / 0.12 * 6.0, 0.0, 6.0)
        if report.stock.trading_value:
            score += clamp(report.stock.trading_value / 5_000_000_000 * 4.0, 0.0, 4.0)
        return clamp(score, 0.0, 20.0)

    @staticmethod
    def _notes(report: DiscoveryReport) -> List[str]:
        notes = []
        if report.financials.quality_notes:
            notes.extend(report.financials.quality_notes[:3])
        if report.accumulation:
            notes.append(f"수급 {report.accumulation.net_buy_amount_to_market_cap or 0:.2%}/시총")
        notes.append(f"60일 상대강도 {report.technicals.relative_strength_60d:+.1f}%p")
        notes.append(f"중기 모멘텀 {report.technicals.momentum_120_20d:+.1f}%")
        notes.append(report.technicals.trend_summary)
        return notes[:5]

    @staticmethod
    def _grade(total: float) -> str:
        if total >= 85:
            return "A+"
        if total >= 75:
            return "A"
        if total >= 65:
            return "B+"
        if total >= factor_score_minimum():
            return "B"
        return "C"


class InvestmentThesisBuilder:
    def build(self, report: DiscoveryReport) -> InvestmentThesis:
        quality = self._quality_score(report.financials)
        value = self._value_score(report.financials)
        momentum = self._momentum_score(report.technicals)
        psychology = self._psychology_score(report)
        asymmetry = self._asymmetry_score(report)
        total = quality + value + momentum + psychology + asymmetry
        strengths = self._strengths(report, quality, value, momentum, psychology, asymmetry)
        concerns = self._concerns(report, quality, value, momentum, psychology, asymmetry)
        return InvestmentThesis(
            quality=round(quality, 1),
            value=round(value, 1),
            momentum=round(momentum, 1),
            psychology=round(psychology, 1),
            asymmetry=round(asymmetry, 1),
            total=round(total, 1),
            label=self._label(total),
            strengths=strengths[:5],
            concerns=concerns[:5],
        )

    @staticmethod
    def _quality_score(metrics: FinancialMetrics) -> float:
        score = 0.0
        score += clamp((MAX_DEBT_TO_EQUITY - metrics.debt_to_equity) / MAX_DEBT_TO_EQUITY * 5.0, 0.0, 5.0)
        score += clamp((metrics.current_ratio - MIN_CURRENT_RATIO) / 200.0 * 4.0, 0.0, 4.0)
        if metrics.roe is not None:
            score += clamp(metrics.roe / 18.0 * 6.0, 0.0, 6.0)
        else:
            score += 2.0
        if metrics.operating_margin is not None:
            score += clamp(metrics.operating_margin / 15.0 * 5.0, 0.0, 5.0)
        else:
            score += 2.0
        if len(metrics.operating_income_years) >= REQUIRED_PROFIT_YEARS:
            positive_years = sum(1 for value in metrics.operating_income_years[:4] if value > 0)
            score += clamp(positive_years / 4.0 * 3.0, 0.0, 3.0)
        if metrics.revenue_growth_yoy is not None:
            score += clamp((metrics.revenue_growth_yoy + 5.0) / 25.0 * 2.0, 0.0, 2.0)
        else:
            score += 1.0
        return clamp(score, 0.0, 25.0)

    @staticmethod
    def _value_score(metrics: FinancialMetrics) -> float:
        score = 0.0
        score += clamp((MAX_PBR - metrics.pbr) / MAX_PBR * 12.0, 0.0, 12.0)
        if metrics.per is not None and metrics.per > 0:
            score += clamp((18.0 - metrics.per) / 18.0 * 5.0, 0.0, 5.0)
        else:
            score += 2.0
        if metrics.roe is not None and metrics.roe >= MIN_ROE:
            score += clamp((metrics.roe - MIN_ROE) / 15.0 * 4.0, 0.0, 4.0)
        if metrics.operating_margin is not None and metrics.operating_margin >= MIN_OPERATING_MARGIN:
            score += clamp((metrics.operating_margin - MIN_OPERATING_MARGIN) / 12.0 * 2.0, 0.0, 2.0)
        if metrics.operating_income_growth_yoy is not None:
            score += clamp((metrics.operating_income_growth_yoy + 20.0) / 50.0 * 2.0, 0.0, 2.0)
        else:
            score += 1.0
        return clamp(score, 0.0, 25.0)

    @staticmethod
    def _momentum_score(technicals: TechnicalSnapshot) -> float:
        score = 0.0
        score += clamp((technicals.relative_strength_60d + 5.0) / 25.0 * 7.0, 0.0, 7.0)
        score += clamp((technicals.momentum_120_20d + 5.0) / 30.0 * 6.0, 0.0, 6.0)
        score += clamp((technicals.high_proximity_180d - 60.0) / 38.0 * 5.0, 0.0, 5.0)
        ma_spread = technicals.ma20 / technicals.ma60 - 1 if technicals.ma60 > 0 else 0.0
        score += clamp(ma_spread / 0.12 * 4.0, 0.0, 4.0)
        volume_ratio = technicals.volume / technicals.avg_volume20 if technicals.avg_volume20 > 0 else 1.0
        score += clamp(volume_ratio / 2.0 * 3.0, 0.0, 3.0)
        return clamp(score, 0.0, 25.0)

    @staticmethod
    def _psychology_score(report: DiscoveryReport) -> float:
        technicals = report.technicals
        score = 0.0
        score += clamp((MAX_RETURN_20D - max(0.0, technicals.return_20d)) / MAX_RETURN_20D * 4.0, 0.0, 4.0)
        score += clamp((MAX_DRAWDOWN_60D - technicals.max_drawdown_60d) / MAX_DRAWDOWN_60D * 3.0, 0.0, 3.0)
        score += clamp((MAX_RSI - technicals.rsi) / (MAX_RSI - MIN_RSI) * 2.0, 0.0, 2.0)
        if report.accumulation is not None:
            score += clamp((MAX_SIDEWAYS_PRICE_CHANGE - abs(report.accumulation.price_change)) / MAX_SIDEWAYS_PRICE_CHANGE * 3.0, 0.0, 3.0)
            score += clamp(report.accumulation.positive_days / ACCUMULATION_LOOKBACK_DAYS * 3.0, 0.0, 3.0)
        else:
            score += 2.0
        return clamp(score, 0.0, 15.0)

    @staticmethod
    def _asymmetry_score(report: DiscoveryReport) -> float:
        technicals = report.technicals
        score = 0.0
        score += clamp(technicals.risk_reward_ratio / 2.5 * 5.0, 0.0, 5.0)
        stop_loss_pct = DecisionPolicy._stop_loss_pct(technicals)
        score += clamp((12.0 - stop_loss_pct) / 12.0 * 3.0, 0.0, 3.0)
        if report.stock.trading_value:
            score += clamp(report.stock.trading_value / 5_000_000_000 * 2.0, 0.0, 2.0)
        return clamp(score, 0.0, 10.0)

    @staticmethod
    def _strengths(
        report: DiscoveryReport,
        quality: float,
        value: float,
        momentum: float,
        psychology: float,
        asymmetry: float,
    ) -> List[str]:
        strengths: List[str] = []
        if quality >= 18:
            strengths.append("품질: 부채/유동성/수익성 조합 우수")
        if value >= 17:
            strengths.append("가치: PBR·이익 대비 할인 매력")
        if momentum >= 17:
            strengths.append("모멘텀: 시장 대비 강한 중기 추세")
        if psychology >= 10:
            strengths.append("심리: 과열보다 매집/휴식 구간에 가까움")
        if asymmetry >= 7:
            strengths.append("손익비: ATR 손절 대비 목표 구간 양호")
        if report.accumulation:
            strengths.append("수급: 외국인/기관 누적 순매수 확인")
        return strengths or ["복합 팩터 통과"]

    @staticmethod
    def _concerns(
        report: DiscoveryReport,
        quality: float,
        value: float,
        momentum: float,
        psychology: float,
        asymmetry: float,
    ) -> List[str]:
        concerns: List[str] = []
        if quality < 15:
            concerns.append("품질 점수 낮음")
        if value < 13:
            concerns.append("가격 매력 제한")
        if momentum < 14:
            concerns.append("중기 모멘텀 약함")
        if psychology < 9:
            concerns.append("단기 과열 또는 심리 리스크")
        if asymmetry < 6:
            concerns.append("목표 대비 손절폭 부담")
        if report.technicals.high_proximity_180d > 100:
            concerns.append("180일 신고가권 돌파 후 변동성 주의")
        return concerns

    @staticmethod
    def _label(total: float) -> str:
        if total >= 82:
            return "복합 알파 우수"
        if total >= 72:
            return "우량 후보"
        if total >= 64:
            return "관심 후보"
        return "보류"


class DecisionPolicy:
    def __init__(self) -> None:
        self.min_factor_score = factor_score_minimum()
        self.min_data_quality = data_quality_min_score()
        self.watchlist_min_factor_score = watchlist_factor_score_minimum()
        self.watchlist_min_data_quality = watchlist_data_quality_min_score()
        self.radar_min_factor_score = radar_factor_score_minimum()
        self.radar_min_data_quality = radar_data_quality_min_score()
        self.strong_buy_score = env_float_profile(
            "SIGNAL_STRONG_BUY_SCORE",
            SIGNAL_STRONG_BUY_SCORE,
            {"conservative": 84.0, "institutional": 78.0, "balanced": 74.0, "aggressive": 70.0},
        )
        self.trade_ready_score = env_float_profile(
            "AUTO_TRADE_MIN_SCORE",
            AUTO_TRADE_MIN_SCORE,
            {"conservative": 85.0, "institutional": 82.0, "balanced": 78.0, "aggressive": 72.0},
        )
        self.auto_min_data_quality = env_float_profile(
            "AUTO_TRADE_MIN_DATA_QUALITY",
            AUTO_TRADE_MIN_DATA_QUALITY,
            {"conservative": 90.0, "institutional": 85.0, "balanced": 82.0, "aggressive": 78.0},
        )
        self.max_stop_loss_pct = env_float_profile(
            "AUTO_TRADE_MAX_STOP_LOSS_PCT",
            AUTO_TRADE_MAX_STOP_LOSS_PCT,
            {"conservative": 6.0, "institutional": 8.0, "balanced": 9.0, "aggressive": 12.0},
        )
        self.min_financial_score = env_float_profile(
            "AUTO_TRADE_MIN_FINANCIAL_SCORE",
            AUTO_TRADE_MIN_FINANCIAL_SCORE,
            {"conservative": 22.0, "institutional": 20.0, "balanced": 18.0, "aggressive": 16.0},
        )
        self.min_accumulation_score = env_float_profile(
            "AUTO_TRADE_MIN_ACCUMULATION_SCORE",
            AUTO_TRADE_MIN_ACCUMULATION_SCORE,
            {"conservative": 15.0, "institutional": 12.0, "balanced": 10.0, "aggressive": 8.0},
        )
        self.min_technical_score = env_float_profile(
            "AUTO_TRADE_MIN_TECHNICAL_SCORE",
            AUTO_TRADE_MIN_TECHNICAL_SCORE,
            {"conservative": 18.0, "institutional": 17.0, "balanced": 15.0, "aggressive": 13.0},
        )
        self.min_risk_score = env_float_profile(
            "AUTO_TRADE_MIN_RISK_SCORE",
            AUTO_TRADE_MIN_RISK_SCORE,
            {"conservative": 15.0, "institutional": 13.0, "balanced": 12.0, "aggressive": 10.0},
        )
        self.min_thesis_score = env_float_profile(
            "MIN_INVESTMENT_THESIS_SCORE",
            MIN_INVESTMENT_THESIS_SCORE,
            {"conservative": 76.0, "institutional": 70.0, "balanced": 66.0, "aggressive": 60.0},
        )
        self.watchlist_min_thesis_score = watchlist_investment_thesis_minimum()
        self.radar_min_thesis_score = radar_investment_thesis_minimum()
        self.min_relative_strength = env_float_profile(
            "MIN_RELATIVE_STRENGTH_60D",
            MIN_RELATIVE_STRENGTH_60D,
            {"conservative": 3.0, "institutional": 1.0, "balanced": 0.0, "aggressive": -3.0},
        )
        self.watchlist_min_relative_strength = watchlist_relative_strength_minimum()
        self.radar_min_relative_strength = radar_relative_strength_minimum()
        self.min_return_20d = env_float("MIN_RETURN_20D", MIN_RETURN_20D)
        self.max_return_20d = env_float("MAX_RETURN_20D", MAX_RETURN_20D)
        self.max_return_120d = env_float("MAX_RETURN_120D", MAX_RETURN_120D)
        self.max_drawdown_60d = env_float("MAX_DRAWDOWN_60D", MAX_DRAWDOWN_60D)
        self.watchlist_min_return_20d = env_float("WATCHLIST_MIN_RETURN_20D", WATCHLIST_MIN_RETURN_20D)
        self.watchlist_max_return_20d = env_float("WATCHLIST_MAX_RETURN_20D", WATCHLIST_MAX_RETURN_20D)
        self.watchlist_max_return_120d = env_float("WATCHLIST_MAX_RETURN_120D", WATCHLIST_MAX_RETURN_120D)
        self.watchlist_max_drawdown_60d = env_float("WATCHLIST_MAX_DRAWDOWN_60D", WATCHLIST_MAX_DRAWDOWN_60D)
        self.radar_min_return_20d = env_float("RADAR_MIN_RETURN_20D", RADAR_MIN_RETURN_20D)
        self.radar_max_return_20d = env_float("RADAR_MAX_RETURN_20D", RADAR_MAX_RETURN_20D)
        self.radar_max_return_120d = env_float("RADAR_MAX_RETURN_120D", RADAR_MAX_RETURN_120D)
        self.radar_max_drawdown_60d = env_float("RADAR_MAX_DRAWDOWN_60D", RADAR_MAX_DRAWDOWN_60D)

    def classify(self, report: DiscoveryReport) -> SignalDecision:
        if report.score is None:
            return SignalDecision(
                tier="보류",
                action="팩터 점수 산출 실패",
                trade_eligible=False,
                vetoes=["팩터 점수 없음"],
            )

        score = report.score
        technicals = report.technicals
        stop_loss_pct = self._stop_loss_pct(technicals)
        is_radar = report.signal_stage == "radar" or technicals.signal_stage == "radar"
        is_watchlist = report.signal_stage == "watchlist" or technicals.signal_stage == "watchlist"
        if is_radar:
            min_data_quality = self.radar_min_data_quality
            min_factor_score = self.radar_min_factor_score
            min_thesis_score = self.radar_min_thesis_score
            min_relative_strength = self.radar_min_relative_strength
            min_return_20d = self.radar_min_return_20d
            max_return_20d = self.radar_max_return_20d
            max_return_120d = self.radar_max_return_120d
            max_drawdown_60d = self.radar_max_drawdown_60d
        elif is_watchlist:
            min_data_quality = self.watchlist_min_data_quality
            min_factor_score = self.watchlist_min_factor_score
            min_thesis_score = self.watchlist_min_thesis_score
            min_relative_strength = self.watchlist_min_relative_strength
            min_return_20d = self.watchlist_min_return_20d
            max_return_20d = self.watchlist_max_return_20d
            max_return_120d = self.watchlist_max_return_120d
            max_drawdown_60d = self.watchlist_max_drawdown_60d
        else:
            min_data_quality = self.min_data_quality
            min_factor_score = self.min_factor_score
            min_thesis_score = self.min_thesis_score
            min_relative_strength = self.min_relative_strength
            min_return_20d = self.min_return_20d
            max_return_20d = self.max_return_20d
            max_return_120d = self.max_return_120d
            max_drawdown_60d = self.max_drawdown_60d
        vetoes: List[str] = []
        if report.data_quality_score < min_data_quality:
            vetoes.append(f"데이터 신뢰도 {report.data_quality_score:.1f} < {min_data_quality:.1f}")
        if score.total < min_factor_score:
            vetoes.append(f"종합점수 {score.total:.1f} < {min_factor_score:.1f}")
        if report.thesis is None:
            vetoes.append("투자 가설 점수 없음")
        elif report.thesis.total < min_thesis_score:
            vetoes.append(f"투자 가설 {report.thesis.total:.1f} < {min_thesis_score:.1f}")
        if technicals.relative_strength_60d < min_relative_strength:
            vetoes.append(f"60일 상대강도 {technicals.relative_strength_60d:+.1f}%p 미달")
        if technicals.return_20d < min_return_20d:
            vetoes.append(f"20일 수익률 {technicals.return_20d:+.1f}% 약세")
        if technicals.return_20d > max_return_20d:
            vetoes.append(f"20일 수익률 {technicals.return_20d:+.1f}% 과열")
        if technicals.return_120d > max_return_120d:
            vetoes.append(f"120일 수익률 {technicals.return_120d:+.1f}% 과열")
        if technicals.max_drawdown_60d > max_drawdown_60d:
            vetoes.append(f"60일 최대낙폭 {technicals.max_drawdown_60d:.1f}% 초과")

        reasons = [
            f"단계 {format_discovery_stage(report.signal_stage)}",
            f"점수 {score.total:.1f}/{score.grade}",
            f"DQ {report.data_quality_score:.1f}",
            f"상대강도 {technicals.relative_strength_60d:+.1f}%p",
            f"손절폭 {stop_loss_pct:.1f}%",
        ]
        if report.thesis is not None:
            reasons.insert(1, f"가설 {report.thesis.total:.1f}/{report.thesis.label}")
        if report.accumulation is not None:
            reasons.append(f"수급 {report.accumulation.net_buy_ratio * 100:.2f}%")

        if vetoes:
            return SignalDecision(
                tier="보류",
                action="매수 제외",
                trade_eligible=False,
                reasons=reasons,
                vetoes=vetoes[:5],
            )

        if is_radar:
            trade_vetoes = self._trade_vetoes(report, stop_loss_pct)
            return SignalDecision(
                tier="레이더 후보",
                action="리서치 전용, 매수 금지",
                trade_eligible=False,
                reasons=reasons,
                vetoes=(["레이더 단계는 자동매매 제외"] + trade_vetoes)[:5],
            )

        if is_watchlist:
            trade_vetoes = self._trade_vetoes(report, stop_loss_pct)
            return SignalDecision(
                tier="관심 후보",
                action="관찰 후보군 편입, 장중 회복 신호 감시",
                trade_eligible=False,
                reasons=reasons,
                vetoes=(["관찰 단계는 자동매매 제외"] + trade_vetoes)[:5],
            )

        trade_vetoes = self._trade_vetoes(report, stop_loss_pct)
        if not trade_vetoes:
            return SignalDecision(
                tier="자동매매 가능",
                action="모의 주문 또는 대기 주문 가능",
                trade_eligible=True,
                reasons=reasons,
            )
        if score.total >= self.strong_buy_score:
            return SignalDecision(
                tier="강력 후보",
                action="알림 우선, 자동매매 보류",
                trade_eligible=False,
                reasons=reasons,
                vetoes=trade_vetoes[:5],
            )
        return SignalDecision(
            tier="관심 후보",
            action="감시 지속",
            trade_eligible=False,
            reasons=reasons,
            vetoes=trade_vetoes[:5],
        )

    def _trade_vetoes(self, report: DiscoveryReport, stop_loss_pct: float) -> List[str]:
        if report.score is None:
            return ["팩터 점수 없음"]
        score = report.score
        vetoes: List[str] = []
        if score.total < self.trade_ready_score:
            vetoes.append(f"자동매매 점수 {score.total:.1f} < {self.trade_ready_score:.1f}")
        if report.data_quality_score < self.auto_min_data_quality:
            vetoes.append(f"자동매매 DQ {report.data_quality_score:.1f} < {self.auto_min_data_quality:.1f}")
        if stop_loss_pct > self.max_stop_loss_pct:
            vetoes.append(f"손절폭 {stop_loss_pct:.1f}% > {self.max_stop_loss_pct:.1f}%")
        if score.financial < self.min_financial_score:
            vetoes.append(f"재무점수 {score.financial:.1f} < {self.min_financial_score:.1f}")
        if score.accumulation < self.min_accumulation_score:
            vetoes.append(f"수급점수 {score.accumulation:.1f} < {self.min_accumulation_score:.1f}")
        if score.technical < self.min_technical_score:
            vetoes.append(f"기술점수 {score.technical:.1f} < {self.min_technical_score:.1f}")
        if score.risk < self.min_risk_score:
            vetoes.append(f"리스크점수 {score.risk:.1f} < {self.min_risk_score:.1f}")
        if report.thesis is None:
            vetoes.append("투자 가설 점수 없음")
        elif report.thesis.total < self.min_thesis_score:
            vetoes.append(f"투자 가설 {report.thesis.total:.1f} < {self.min_thesis_score:.1f}")
        return vetoes

    @staticmethod
    def _stop_loss_pct(technicals: TechnicalSnapshot) -> float:
        if technicals.current_price <= 0 or technicals.stop_loss <= 0:
            return 100.0
        return max(0.0, (technicals.current_price - technicals.stop_loss) / technicals.current_price * 100)


class Notifier:
    MAX_MESSAGE_LENGTH = 3900

    def __init__(self, token: str, chat_id: str) -> None:
        load_dotenv()
        self.token = token
        self.chat_id = chat_id
        self.max_retries = max(1, env_int("TELEGRAM_MAX_RETRIES", TELEGRAM_MAX_RETRIES))
        self.retry_delay_seconds = max(0.1, env_float("TELEGRAM_RETRY_DELAY_SECONDS", TELEGRAM_RETRY_DELAY_SECONDS))
        self.timeout_seconds = max(3.0, env_float("TELEGRAM_TIMEOUT_SECONDS", TELEGRAM_TIMEOUT_SECONDS))

    def send(self, message: str) -> bool:
        if not self.token or not self.chat_id:
            logger.warning("TELEGRAM_TOKEN 또는 CHAT_ID가 비어 있어 텔레그램 전송을 건너뜁니다.")
            logger.info("전송 예정 메시지:\n%s", message)
            return False

        for index, chunk in enumerate(self._split_message(message), start=1):
            if not self._send_chunk(chunk, index):
                return False

        logger.info("텔레그램 메시지 전송 완료")
        return True

    def _send_chunk(self, chunk: str, index: int) -> bool:
        url = f"https://api.telegram.org/bot{self.token}/sendMessage"
        last_status = "N/A"
        for attempt in range(1, self.max_retries + 1):
            try:
                response = requests.post(
                    url,
                    data={
                        "chat_id": self.chat_id,
                        "text": chunk,
                        "disable_web_page_preview": True,
                    },
                    timeout=self.timeout_seconds,
                )
                last_status = response.status_code
                response.raise_for_status()
                return True
            except requests.RequestException as exc:
                response = getattr(exc, "response", None)
                last_status = getattr(response, "status_code", last_status)
                retry_after = self._retry_after_seconds(response)
                if attempt >= self.max_retries:
                    logger.error(
                        "텔레그램 메시지 전송 실패: chunk=%d, HTTP %s, attempts=%d",
                        index,
                        last_status,
                        attempt,
                    )
                    return False
                delay = retry_after or self.retry_delay_seconds * attempt
                logger.warning(
                    "텔레그램 전송 재시도: chunk=%d, HTTP %s, attempt=%d/%d, %.1f초 대기",
                    index,
                    last_status,
                    attempt,
                    self.max_retries,
                    delay,
                )
                time.sleep(delay)
        return False

    @staticmethod
    def _retry_after_seconds(response: Optional[requests.Response]) -> Optional[float]:
        if response is None:
            return None
        retry_after = response.headers.get("Retry-After")
        if not retry_after:
            return None
        try:
            return max(0.1, float(retry_after))
        except ValueError:
            return None

    def _split_message(self, message: str) -> List[str]:
        if len(message) <= self.MAX_MESSAGE_LENGTH:
            return [message]

        chunks: List[str] = []
        current = ""
        for line in message.splitlines():
            candidate = f"{current}\n{line}" if current else line
            if len(candidate) > self.MAX_MESSAGE_LENGTH:
                chunks.append(current)
                current = line
            else:
                current = candidate

        if current:
            chunks.append(current)
        return chunks


class TradingEngine:
    def __init__(self, kis_provider: KISDataProvider, notifier: Notifier) -> None:
        load_dotenv()
        self.kis_provider = kis_provider
        self.notifier = notifier
        self.enabled = env_bool("AUTO_TRADE_ENABLED", AUTO_TRADE_ENABLED)
        self.dry_run = env_bool("AUTO_TRADE_DRY_RUN", AUTO_TRADE_DRY_RUN)
        self.confirm_real_trading = os.getenv(
            "AUTO_TRADE_CONFIRM_REAL_TRADING",
            AUTO_TRADE_CONFIRM_REAL_TRADING,
        ).strip()
        self.run_time = os.getenv("AUTO_TRADE_RUN_TIME_KST", AUTO_TRADE_RUN_TIME_KST)
        self.max_orders_per_run = env_int("AUTO_TRADE_MAX_ORDERS_PER_RUN", AUTO_TRADE_MAX_ORDERS_PER_RUN)
        self.order_budget_krw = env_float("AUTO_TRADE_ORDER_BUDGET_KRW", AUTO_TRADE_ORDER_BUDGET_KRW)
        self.max_order_value_krw = env_float("AUTO_TRADE_MAX_ORDER_VALUE_KRW", AUTO_TRADE_MAX_ORDER_VALUE_KRW)
        self.max_portfolio_exposure_krw = env_float(
            "AUTO_TRADE_MAX_PORTFOLIO_EXPOSURE_KRW",
            AUTO_TRADE_MAX_PORTFOLIO_EXPOSURE_KRW,
        )
        self.cooldown_hours = env_float("AUTO_TRADE_COOLDOWN_HOURS", AUTO_TRADE_COOLDOWN_HOURS)
        self.pending_max_age_hours = env_float(
            "AUTO_TRADE_PENDING_MAX_AGE_HOURS",
            AUTO_TRADE_PENDING_MAX_AGE_HOURS,
        )
        self.order_type = os.getenv("AUTO_TRADE_ORDER_TYPE", AUTO_TRADE_ORDER_TYPE).strip() or "01"
        self.exchange = os.getenv("AUTO_TRADE_EXCHANGE", AUTO_TRADE_EXCHANGE).strip() or "KRX"
        self.use_hashkey = env_bool("AUTO_TRADE_USE_HASHKEY", AUTO_TRADE_USE_HASHKEY)
        self.use_risk_sizing = env_bool("AUTO_TRADE_USE_RISK_SIZING", AUTO_TRADE_USE_RISK_SIZING)
        self.risk_per_trade_krw = env_float("AUTO_TRADE_RISK_PER_TRADE_KRW", AUTO_TRADE_RISK_PER_TRADE_KRW)
        self.min_score = env_float_profile(
            "AUTO_TRADE_MIN_SCORE",
            AUTO_TRADE_MIN_SCORE,
            {"conservative": 85.0, "institutional": 82.0, "balanced": 78.0, "aggressive": 72.0},
        )
        self.min_data_quality = env_float_profile(
            "AUTO_TRADE_MIN_DATA_QUALITY",
            AUTO_TRADE_MIN_DATA_QUALITY,
            {"conservative": 90.0, "institutional": 85.0, "balanced": 82.0, "aggressive": 78.0},
        )
        self.max_stop_loss_pct = env_float_profile(
            "AUTO_TRADE_MAX_STOP_LOSS_PCT",
            AUTO_TRADE_MAX_STOP_LOSS_PCT,
            {"conservative": 6.0, "institutional": 8.0, "balanced": 9.0, "aggressive": 12.0},
        )

    def prepare_buy_plans(self, reports: List[DiscoveryReport], market_regime: MarketRegime) -> List[OrderPlan]:
        if not market_regime.risk_on or not reports:
            return []

        history = self._load_trade_history()
        plans: List[OrderPlan] = []
        planned_value = 0.0

        for report in reports:
            if len(plans) >= max(0, self.max_orders_per_run):
                break
            if self._recently_traded(report.stock.code, history):
                logger.info("%s(%s) 최근 자동매매 이력으로 주문 후보 제외", report.stock.name, report.stock.code)
                continue
            if not self._passes_auto_trade_gate(report):
                continue

            current_price = report.technicals.current_price
            if current_price <= 0:
                continue

            remaining_exposure = max(0.0, self.max_portfolio_exposure_krw - planned_value)
            budget = min(self.order_budget_krw, self.max_order_value_krw, remaining_exposure)
            budget_quantity = int(budget // current_price)
            risk_per_share = max(0.0, current_price - report.technicals.stop_loss)
            risk_quantity = budget_quantity
            if self.use_risk_sizing and risk_per_share > 0 and self.risk_per_trade_krw > 0:
                risk_quantity = int(self.risk_per_trade_krw // risk_per_share)
            quantity = min(budget_quantity, risk_quantity)
            if quantity < 1:
                logger.info("%s(%s) 주문 예산/리스크 한도 부족으로 자동매매 후보 제외", report.stock.name, report.stock.code)
                continue

            estimated_value = quantity * current_price
            estimated_risk = quantity * risk_per_share
            plans.append(
                OrderPlan(
                    side="buy",
                    code=report.stock.code,
                    name=report.stock.name,
                    quantity=quantity,
                    estimated_price=current_price,
                    estimated_value=estimated_value,
                    stop_loss=report.technicals.stop_loss,
                    order_type=self.order_type,
                    exchange=self.exchange,
                    reason=report.reason,
                    created_at=datetime.now().isoformat(timespec="seconds"),
                    risk_per_share=risk_per_share,
                    estimated_risk=estimated_risk,
                )
            )
            planned_value += estimated_value

        return plans

    def _passes_auto_trade_gate(self, report: DiscoveryReport) -> bool:
        score = report.score.total if report.score else 0.0
        if report.signal_stage != "strict" or report.technicals.signal_stage != "strict":
            logger.info(
                "%s(%s) %s 단계이므로 자동매매 제외",
                report.stock.name,
                report.stock.code,
                format_discovery_stage(report.signal_stage),
            )
            return False
        if report.decision and not report.decision.trade_eligible:
            logger.info(
                "%s(%s) 의사결정 등급 %s로 자동매매 보류: %s",
                report.stock.name,
                report.stock.code,
                report.decision.tier,
                "; ".join(report.decision.vetoes[:3]) or report.decision.action,
            )
            return False
        if score < self.min_score:
            logger.info(
                "%s(%s) 자동매매 점수 %.1f 미달(기준 %.1f)",
                report.stock.name,
                report.stock.code,
                score,
                self.min_score,
            )
            return False
        if report.data_quality_score < self.min_data_quality:
            logger.info(
                "%s(%s) 자동매매 데이터 신뢰도 %.1f 미달(기준 %.1f)",
                report.stock.name,
                report.stock.code,
                report.data_quality_score,
                self.min_data_quality,
            )
            return False
        if report.score:
            factor_checks = [
                ("재무", report.score.financial, self.min_financial_score),
                ("수급", report.score.accumulation, self.min_accumulation_score),
                ("기술", report.score.technical, self.min_technical_score),
                ("리스크", report.score.risk, self.min_risk_score),
            ]
            for label, value, minimum in factor_checks:
                if value < minimum:
                    logger.info(
                        "%s(%s) 자동매매 %s점수 %.1f 미달(기준 %.1f)",
                        report.stock.name,
                        report.stock.code,
                        label,
                        value,
                        minimum,
                    )
                    return False
        current_price = report.technicals.current_price
        stop_loss = report.technicals.stop_loss
        if current_price <= 0 or stop_loss <= 0:
            return False
        stop_loss_pct = (current_price - stop_loss) / current_price * 100
        if stop_loss_pct > self.max_stop_loss_pct:
            logger.info(
                "%s(%s) 손절폭 %.1f%% 초과(기준 %.1f%%)",
                report.stock.name,
                report.stock.code,
                stop_loss_pct,
                self.max_stop_loss_pct,
            )
            return False
        return True

    def save_pending_plans(self, plans: List[OrderPlan]) -> None:
        if not self.enabled or not plans:
            return
        try:
            CACHE_DIR.mkdir(exist_ok=True)
            payload = {
                "created_at": datetime.now().isoformat(timespec="seconds"),
                "trading_env": self.kis_provider.trading_env,
                "dry_run": self.dry_run,
                "plans": [asdict(plan) for plan in plans],
            }
            with PENDING_TRADE_FILE.open("w", encoding="utf-8") as file:
                json.dump(payload, file, ensure_ascii=False, indent=2)
            logger.info("자동매매 대기 주문 %d건 저장", len(plans))
        except Exception as exc:
            logger.warning("자동매매 대기 주문 저장 실패: %s", exc)

    def execute_pending_orders(self) -> List[OrderResult]:
        plans = self._load_pending_plans()
        if not plans:
            logger.info("자동매매 대기 주문이 없습니다.")
            return []
        if not self.enabled:
            logger.info("AUTO_TRADE_ENABLED=false 이므로 주문 실행을 건너뜁니다.")
            return []

        permitted, reason = self._orders_permitted()
        if not permitted:
            message = f"🤖 자동매매 실행 차단\n{reason}"
            logger.warning(message)
            self.notifier.send(message)
            return []

        results: List[OrderResult] = []
        history = self._load_trade_history()
        for plan in plans[: max(0, self.max_orders_per_run)]:
            news_block_reason = recent_news_risk_for_plan(plan)
            if news_block_reason:
                results.append(
                    OrderResult(
                        plan=plan,
                        submitted=False,
                        dry_run=self.dry_run,
                        status="NEWS_BLOCK",
                        message=news_block_reason,
                    )
                )
                logger.warning("%s(%s) 뉴스 리스크로 주문 차단: %s", plan.name, plan.code, news_block_reason)
                continue
            result = self._execute_plan(plan)
            results.append(result)
            if result.submitted and not result.dry_run:
                history[plan.code] = datetime.now().isoformat(timespec="seconds")
            time.sleep(REQUEST_DELAY_SECONDS)

        self._save_trade_history(history)
        self._clear_pending_plans()
        if results:
            self.notifier.send(self._build_execution_message(results))
        return results

    def discard_pending_plans(self, reason: str) -> None:
        plans = self._load_pending_plans()
        if not plans:
            return
        self._clear_pending_plans()
        message = f"🤖 자동매매 대기 주문 폐기\n{reason}\n폐기 건수: {len(plans)}"
        logger.warning(message)
        self.notifier.send(message)

    def status_summary(self) -> str:
        if not self.enabled:
            return "자동매매 비활성화(AUTO_TRADE_ENABLED=false)"
        mode = "DRY_RUN" if self.dry_run else "실주문"
        account = mask_account(self.kis_provider.account_no, self.kis_provider.account_product_code)
        return (
            f"{mode}, {self.kis_provider.trading_env}, 계좌 {account}, "
            f"주문시간 {self.run_time}, 1회 최대 {self.max_orders_per_run}건, "
            f"최소점수 {self.min_score:.1f}, 최소DQ {self.min_data_quality:.1f}, "
            f"하위점수 재무/수급/기술/리스크 "
            f"{self.min_financial_score:.0f}/{self.min_accumulation_score:.0f}/"
            f"{self.min_technical_score:.0f}/{self.min_risk_score:.0f}, "
            f"종목당 위험한도 {self.risk_per_trade_krw:,.0f}원"
        )

    def _execute_plan(self, plan: OrderPlan) -> OrderResult:
        if self.dry_run:
            return OrderResult(
                plan=plan,
                submitted=True,
                dry_run=True,
                status="DRY_RUN",
                message="실제 주문은 전송하지 않고 주문 가능성만 기록했습니다.",
            )

        try:
            buyable = self.kis_provider.fetch_buyable_order(plan.code, plan.estimated_price, plan.order_type)
            buyable_cash = to_float(buyable.get("nrcvb_buy_amt"))
            buyable_qty = to_float(buyable.get("nrcvb_buy_qty"))
            if buyable_cash is not None and plan.estimated_value > buyable_cash:
                raise RuntimeError(
                    f"매수가능금액 부족: 필요 {plan.estimated_value:,.0f}원, 가능 {buyable_cash:,.0f}원"
                )
            if buyable_qty is not None and plan.quantity > int(buyable_qty):
                raise RuntimeError(f"매수가능수량 부족: 필요 {plan.quantity}주, 가능 {int(buyable_qty)}주")

            payload = self.kis_provider.place_cash_order(
                side=plan.side,
                code=plan.code,
                quantity=plan.quantity,
                price=plan.estimated_price,
                order_type=plan.order_type,
                exchange=plan.exchange,
                use_hashkey=self.use_hashkey,
            )
            output = payload.get("output") or {}
            order_number = None
            if isinstance(output, dict):
                order_number = str(output.get("ODNO") or "") or None
            return OrderResult(
                plan=plan,
                submitted=True,
                dry_run=False,
                status="SUBMITTED",
                message=str(payload.get("msg1", "주문 접수")),
                order_number=order_number,
            )
        except Exception as exc:
            logger.exception("%s(%s) 자동매매 주문 실패: %s", plan.name, plan.code, exc)
            return OrderResult(
                plan=plan,
                submitted=False,
                dry_run=False,
                status="ERROR",
                message=str(exc),
            )

    def _orders_permitted(self) -> tuple[bool, str]:
        if self.dry_run:
            return True, ""
        if not self.kis_provider.trading_ready:
            return False, "KIS_APP_KEY, KIS_APP_SECRET, KIS_ACCOUNT_NO, KIS_ACCOUNT_PRODUCT_CODE 설정이 필요합니다."
        if self.kis_provider.trading_env == "real" and self.confirm_real_trading != "YES":
            return False, "실전 주문은 AUTO_TRADE_CONFIRM_REAL_TRADING=YES 설정 전까지 차단됩니다."
        return True, ""

    @staticmethod
    def _build_execution_message(results: List[OrderResult]) -> str:
        lines = ["🤖 자동매매 주문 실행 결과"]
        for result in results:
            plan = result.plan
            order_no = f", 주문번호 {result.order_number}" if result.order_number else ""
            lines.extend(
                [
                    "",
                    f"[{plan.name}({plan.code})] {result.status}{order_no}",
                    f"수량 {plan.quantity}주, 예상금액 {plan.estimated_value:,.0f}원",
                    f"손절 기준 {plan.stop_loss:,.0f}원, 예상위험 {plan.estimated_risk:,.0f}원",
                    result.message,
                ]
            )
        return "\n".join(lines)

    def _load_pending_plans(self) -> List[OrderPlan]:
        if not PENDING_TRADE_FILE.exists():
            return []
        try:
            with PENDING_TRADE_FILE.open("r", encoding="utf-8") as file:
                payload = json.load(file)
            created_at_text = payload.get("created_at")
            if created_at_text and self.pending_max_age_hours > 0:
                created_at = datetime.fromisoformat(str(created_at_text))
                if datetime.now() - created_at > timedelta(hours=self.pending_max_age_hours):
                    logger.warning("자동매매 대기 주문이 만료되어 폐기합니다.")
                    self._clear_pending_plans()
                    return []
            plans = payload.get("plans", [])
            return [OrderPlan(**plan) for plan in plans if isinstance(plan, dict)]
        except Exception as exc:
            logger.warning("자동매매 대기 주문 로드 실패: %s", exc)
            return []

    @staticmethod
    def _clear_pending_plans() -> None:
        try:
            if PENDING_TRADE_FILE.exists():
                PENDING_TRADE_FILE.unlink()
        except Exception as exc:
            logger.warning("자동매매 대기 주문 삭제 실패: %s", exc)

    @staticmethod
    def _load_trade_history() -> Dict[str, str]:
        if not TRADE_HISTORY_FILE.exists():
            return {}
        try:
            with TRADE_HISTORY_FILE.open("r", encoding="utf-8") as file:
                data = json.load(file)
            return {str(code): str(timestamp) for code, timestamp in data.items()}
        except Exception as exc:
            logger.warning("자동매매 이력 로드 실패: %s", exc)
            return {}

    @staticmethod
    def _save_trade_history(history: Dict[str, str]) -> None:
        try:
            CACHE_DIR.mkdir(exist_ok=True)
            with TRADE_HISTORY_FILE.open("w", encoding="utf-8") as file:
                json.dump(history, file, ensure_ascii=False, indent=2)
        except Exception as exc:
            logger.warning("자동매매 이력 저장 실패: %s", exc)

    def _recently_traded(self, code: str, history: Dict[str, str]) -> bool:
        traded_at_text = history.get(code)
        if not traded_at_text:
            return False
        try:
            traded_at = datetime.fromisoformat(traded_at_text)
        except ValueError:
            return False
        return datetime.now() - traded_at < timedelta(hours=self.cooldown_hours)


class RealtimeScanner:
    def __init__(self, kis_provider: KISDataProvider, notifier: Notifier) -> None:
        load_dotenv()
        self.kis_provider = kis_provider
        self.notifier = notifier
        self.enabled = env_bool("REALTIME_SCAN_ENABLED", REALTIME_SCAN_ENABLED)
        self.candidate_run_time = os.getenv("REALTIME_CANDIDATE_RUN_TIME_KST", REALTIME_CANDIDATE_RUN_TIME_KST)
        self.scan_start = os.getenv("REALTIME_SCAN_START_KST", REALTIME_SCAN_START_KST)
        self.scan_end = os.getenv("REALTIME_SCAN_END_KST", REALTIME_SCAN_END_KST)
        self.scan_interval_seconds = env_int("REALTIME_SCAN_INTERVAL_SECONDS", REALTIME_SCAN_INTERVAL_SECONDS)
        self.max_watchlist = env_int("REALTIME_MAX_WATCHLIST", REALTIME_MAX_WATCHLIST)
        self.alert_cooldown_hours = env_float("REALTIME_ALERT_COOLDOWN_HOURS", REALTIME_ALERT_COOLDOWN_HOURS)
        self.min_volume_pace = env_float("REALTIME_MIN_VOLUME_PACE", REALTIME_MIN_VOLUME_PACE)
        self.min_intraday_change_pct = env_float(
            "REALTIME_MIN_INTRADAY_CHANGE_PCT",
            REALTIME_MIN_INTRADAY_CHANGE_PCT,
        )
        self.max_intraday_rise_pct = env_float("REALTIME_MAX_INTRADAY_RISE_PCT", REALTIME_MAX_INTRADAY_RISE_PCT)
        self.vi_guard_enabled = env_bool("REALTIME_VI_GUARD_ENABLED", REALTIME_VI_GUARD_ENABLED)
        self.vi_suspect_change_pct = env_float("REALTIME_VI_SUSPECT_CHANGE_PCT", REALTIME_VI_SUSPECT_CHANGE_PCT)
        self.block_margin_rate = env_float("REALTIME_BLOCK_MARGIN_RATE", REALTIME_BLOCK_MARGIN_RATE)
        self.alert_cache = self._load_alert_cache()
        self.last_scan_at: Optional[datetime] = None

    def save_candidate_pool(self, reports: List[DiscoveryReport], regimes: Dict[str, MarketRegime]) -> None:
        if not self.enabled:
            return

        ranked = FinancialHealthBot._rank_reports(reports)[: max(0, self.max_watchlist)]
        candidates = [
            RealtimeCandidate(
                stock=report.stock,
                financials=report.financials,
                technicals=report.technicals,
                accumulation=report.accumulation,
                reason=report.reason,
                created_at=datetime.now().isoformat(timespec="seconds"),
                score=report.score,
                data_quality_score=report.data_quality_score,
                data_quality_grade=report.data_quality_grade,
                data_quality_warnings=report.data_quality_warnings,
                thesis=report.thesis,
                decision=report.decision,
                signal_stage=report.signal_stage,
            )
            for report in ranked
        ]

        try:
            CACHE_DIR.mkdir(exist_ok=True)
            payload = {
                "created_at": datetime.now().isoformat(timespec="seconds"),
                "regimes": {market: asdict(regime) for market, regime in regimes.items()},
                "candidates": [asdict(candidate) for candidate in candidates],
            }
            with REALTIME_CANDIDATE_FILE.open("w", encoding="utf-8") as file:
                json.dump(payload, file, ensure_ascii=False, indent=2)
            logger.info("실시간 감시 후보군 %d개 저장", len(candidates))
        except Exception as exc:
            logger.warning("실시간 감시 후보군 저장 실패: %s", exc)

    def scan_once(self, regimes: Dict[str, MarketRegime], force: bool = False) -> List[RealtimeSignal]:
        if not self.enabled:
            logger.debug("실시간 스캐너 비활성화")
            return []
        now = datetime.now()
        if not force and not is_time_between(now, self.scan_start, self.scan_end):
            logger.debug("실시간 스캔 시간이 아닙니다: %s", now.strftime("%H:%M:%S"))
            return []
        if not force and self.last_scan_at:
            elapsed = (now - self.last_scan_at).total_seconds()
            if elapsed < self.scan_interval_seconds:
                return []

        self.last_scan_at = now
        candidates = self.load_candidate_pool()
        if not candidates:
            logger.info("실시간 감시 후보군이 없습니다.")
            return []

        signals: List[RealtimeSignal] = []
        for candidate in candidates[: max(0, self.max_watchlist)]:
            market_regime = MarketRegimeFilter.select_for_market(candidate.stock.market, regimes)
            if not market_regime.risk_on:
                logger.debug("%s(%s) 시장 Risk-Off로 실시간 감시 제외", candidate.stock.name, candidate.stock.code)
                continue

            signal = self._evaluate_candidate(candidate, market_regime, now)
            if signal and self._send_signal_if_needed(signal):
                signals.append(signal)
            time.sleep(REQUEST_DELAY_SECONDS)

        if signals:
            logger.info("실시간 시그널 %d건 전송", len(signals))
        else:
            logger.info("실시간 시그널 없음")
        return signals

    def load_candidate_pool(self) -> List[RealtimeCandidate]:
        if not REALTIME_CANDIDATE_FILE.exists():
            return []
        try:
            with REALTIME_CANDIDATE_FILE.open("r", encoding="utf-8") as file:
                payload = json.load(file)
            candidates: List[RealtimeCandidate] = []
            for item in payload.get("candidates", []):
                if not isinstance(item, dict):
                    continue
                data_quality_score = float(item.get("data_quality_score", 0.0))
                signal_stage = str(item.get("signal_stage", "strict"))
                required_quality = (
                    radar_data_quality_min_score()
                    if signal_stage == "radar"
                    else watchlist_data_quality_min_score()
                    if signal_stage == "watchlist"
                    else data_quality_min_score()
                )
                if (
                    env_bool("STRICT_DATA_VALIDATION", STRICT_DATA_VALIDATION)
                    and data_quality_score < required_quality
                ):
                    continue
                candidates.append(
                    RealtimeCandidate(
                        stock=StockMeta(**item["stock"]),
                        financials=FinancialMetrics(**item["financials"]),
                        technicals=TechnicalSnapshot(**item["technicals"]),
                        accumulation=(
                            AccumulationSnapshot(**item["accumulation"])
                            if item.get("accumulation")
                            else None
                        ),
                        reason=str(item.get("reason", "")),
                        created_at=str(item.get("created_at", "")),
                        score=(FactorScore(**item["score"]) if item.get("score") else None),
                        data_quality_score=data_quality_score,
                        data_quality_grade=str(item.get("data_quality_grade", "N/A")),
                        data_quality_warnings=list(item.get("data_quality_warnings") or []),
                        thesis=(
                            InvestmentThesis(**item["thesis"])
                            if isinstance(item.get("thesis"), dict)
                            else None
                        ),
                        decision=(
                            SignalDecision(**item["decision"])
                            if isinstance(item.get("decision"), dict)
                            else None
                        ),
                        signal_stage=signal_stage,
                    )
                )
            return candidates
        except Exception as exc:
            logger.warning("실시간 감시 후보군 로드 실패: %s", exc)
            return []

    def build_candidate_message(
        self,
        reports: List[DiscoveryReport],
        regimes: Dict[str, MarketRegime],
        display_limit: Optional[int] = None,
        researched_count: Optional[int] = None,
    ) -> str:
        internal_count = min(len(reports), self.max_watchlist)
        visible_limit = max(1, display_limit or telegram_recommendation_limit())
        visible_count = min(visible_limit, internal_count)
        total_researched = researched_count if researched_count is not None else len(reports)
        lines = [
            "🧭 실시간 감시 후보군 준비 완료",
            f"🗓 {datetime.now().strftime('%Y-%m-%d %H:%M')}",
            f"🔎 전체 리서치 후보 {total_researched}개",
            f"📌 내부 감시 후보 수: {internal_count}개",
            f"🏆 텔레그램 표시: 종합점수 상위 {visible_count}개",
            f"🛡️ KOSPI: {regimes['KOSPI'].summary} / Risk-On={regimes['KOSPI'].risk_on}",
            f"🛡️ KOSDAQ: {regimes['KOSDAQ'].summary} / Risk-On={regimes['KOSDAQ'].risk_on}",
            f"⏱️ 감시 시간: {self.scan_start}~{self.scan_end}, {self.scan_interval_seconds}초 간격",
            "🔢 정렬 기준: 종합점수 높은 순",
        ]
        for report in FinancialHealthBot._rank_reports(reports)[:visible_count]:
            thesis_text = f"가설 {report.thesis.total:.1f}({report.thesis.label})" if report.thesis else "가설 N/A"
            lines.append(
                f"- {report.stock.name}({report.stock.code}) "
                f"{format_discovery_stage(report.signal_stage)}, "
                f"{format_factor_score(report.score)}, PBR {report.financials.pbr:.2f}, "
                f"{thesis_text}, "
                f"{report.decision.tier if report.decision else '판단 N/A'}, "
                f"DQ {report.data_quality_score:.1f}, "
                f"RSI {report.technicals.rsi:.1f}, "
                f"20일선 {report.technicals.ma20:,.0f}원"
            )
        return "\n".join(lines)

    def _evaluate_candidate(
        self,
        candidate: RealtimeCandidate,
        market_regime: MarketRegime,
        now: datetime,
    ) -> Optional[RealtimeSignal]:
        try:
            quote = self.kis_provider.fetch_current_price(candidate.stock.code)
            current_price = quote.get("current_price") or 0.0
            if current_price <= 0:
                return None

            technicals = candidate.technicals
            base_price = technicals.previous_close or technicals.current_price
            change_rate = quote.get("change_rate")
            if change_rate is None and base_price > 0:
                change_rate = (current_price / base_price - 1) * 100
            change_rate = float(change_rate or 0.0)

            block_reason = self._blocking_reason(candidate, quote, current_price, change_rate)
            if block_reason:
                logger.debug("%s(%s) 실시간 차단: %s", candidate.stock.name, candidate.stock.code, block_reason)
                return None

            ma20 = technicals.ma20
            if not (ma20 * (1 - MA_SUPPORT_BAND) <= current_price <= ma20 * (1 + MAX_DISTANCE_ABOVE_MA20)):
                return None
            if current_price < ma20:
                return None

            avg_volume = technicals.avg_volume20 or technicals.volume
            current_volume = quote.get("volume") or 0.0
            volume_ratio = current_volume / avg_volume if avg_volume > 0 else 0.0
            elapsed_ratio = market_elapsed_ratio(now)
            required_ratio = elapsed_ratio * self.min_volume_pace
            if avg_volume > 0 and volume_ratio < required_ratio:
                return None

            volume_pace_ratio = volume_ratio / elapsed_ratio if elapsed_ratio > 0 else 0.0
            summary = (
                f"20일선 상단 회복, 등락률 {change_rate:+.2f}%, "
                f"거래량 페이스 {volume_pace_ratio:.1f}배"
            )
            return RealtimeSignal(
                candidate=candidate,
                current_price=current_price,
                change_rate=change_rate,
                volume_ratio=volume_ratio,
                volume_pace_ratio=volume_pace_ratio,
                market_regime=market_regime,
                summary=summary,
            )
        except Exception as exc:
            logger.warning("%s(%s) 실시간 평가 실패: %s", candidate.stock.name, candidate.stock.code, exc)
            return None

    def _blocking_reason(
        self,
        candidate: RealtimeCandidate,
        quote: Dict[str, object],
        current_price: float,
        change_rate: float,
    ) -> Optional[str]:
        margin_rate = quote.get("margin_rate")
        if margin_rate is not None and float(margin_rate) >= self.block_margin_rate:
            return f"증거금률 {float(margin_rate):.0f}%"

        if change_rate < self.min_intraday_change_pct:
            return f"장중 등락률 {change_rate:+.2f}%"
        if change_rate >= self.max_intraday_rise_pct:
            return f"당일 급등 {change_rate:+.2f}%"

        vi_status = str(quote.get("vi_status") or "").strip()
        if self.vi_guard_enabled and vi_status and vi_status not in {"0", "N", "N/A", "-"}:
            return f"VI 상태 코드 {vi_status}"
        if self.vi_guard_enabled and abs(change_rate) >= self.vi_suspect_change_pct:
            return f"VI 의심 등락률 {change_rate:+.2f}%"

        if current_price <= candidate.technicals.stop_loss:
            return "ATR 손절선 이탈"
        return None

    def _send_signal_if_needed(self, signal: RealtimeSignal) -> bool:
        key = f"{datetime.now().strftime('%Y-%m-%d')}:{signal.candidate.stock.code}"
        cached_at_text = self.alert_cache.get(key)
        if cached_at_text:
            try:
                cached_at = datetime.fromisoformat(cached_at_text)
                if datetime.now() - cached_at < timedelta(hours=self.alert_cooldown_hours):
                    return False
            except ValueError:
                pass

        sent = self.notifier.send(self._build_signal_message(signal))
        if sent:
            self.alert_cache[key] = datetime.now().isoformat(timespec="seconds")
            self._save_alert_cache()
        return sent

    @staticmethod
    def _build_signal_message(signal: RealtimeSignal) -> str:
        candidate = signal.candidate
        technicals = candidate.technicals
        financials = candidate.financials
        return (
            "🚨 장중 실시간 시그널\n"
            f"💎 [{candidate.stock.name}({candidate.stock.code})]\n"
            f"🪜 후보 단계: {format_discovery_stage(candidate.signal_stage)}\n"
            f"🛡️ 시장 국면: {signal.market_regime.summary} / Risk-On\n"
            f"⭐ 종합점수: {format_factor_score(candidate.score)}\n"
            f"🧠 투자 가설: {format_investment_thesis(candidate.thesis)}\n"
            f"🧭 의사결정: {format_signal_decision(candidate.decision)}\n"
            f"🧾 데이터 신뢰도: {format_data_quality(candidate.data_quality_score, candidate.data_quality_grade, candidate.data_quality_warnings)}\n"
            f"💵 현재가: {signal.current_price:,.0f}원 ({signal.change_rate:+.2f}%)\n"
            f"📈 포착 사유: {signal.summary}\n"
            f"📊 재무: 부채비율 {financials.debt_to_equity:.1f}%, "
            f"유동비율 {financials.current_ratio:.1f}%, PBR {financials.pbr:.2f}, "
            f"ROE {format_optional_percent(financials.roe)}\n"
            f"📌 기준: RSI {technicals.rsi:.1f}, 20일선 {technicals.ma20:,.0f}원, "
            f"거래량 페이스 {signal.volume_pace_ratio:.1f}배, "
            f"60일 상대강도 {technicals.relative_strength_60d:+.1f}%p, "
            f"손익비 {technicals.risk_reward_ratio:.2f}\n"
            f"🛡️ 손절선: {technicals.stop_loss:,.0f}원\n"
            f"🏦 수급: {format_accumulation(candidate.accumulation)}\n"
            f"💡 {candidate.reason}"
        )

    @staticmethod
    def _load_alert_cache() -> Dict[str, str]:
        if not REALTIME_ALERT_FILE.exists():
            return {}
        try:
            with REALTIME_ALERT_FILE.open("r", encoding="utf-8") as file:
                data = json.load(file)
            return {str(code): str(timestamp) for code, timestamp in data.items()}
        except Exception as exc:
            logger.warning("실시간 알림 캐시 로드 실패: %s", exc)
            return {}

    def _save_alert_cache(self) -> None:
        try:
            CACHE_DIR.mkdir(exist_ok=True)
            with REALTIME_ALERT_FILE.open("w", encoding="utf-8") as file:
                json.dump(self.alert_cache, file, ensure_ascii=False, indent=2)
        except Exception as exc:
            logger.warning("실시간 알림 캐시 저장 실패: %s", exc)


class NewsPulseMonitor:
    GOOGLE_NEWS_URL = "https://news.google.com/rss/search?q={query}&hl=ko&gl=KR&ceid=KR:ko"

    def __init__(self, notifier: Notifier) -> None:
        load_dotenv()
        self.notifier = notifier
        self.enabled = env_bool("NEWS_ALERT_ENABLED", NEWS_ALERT_ENABLED)
        self.scan_interval_seconds = max(30, env_int("NEWS_SCAN_INTERVAL_SECONDS", NEWS_SCAN_INTERVAL_SECONDS))
        self.lookback_minutes = env_int("NEWS_LOOKBACK_MINUTES", NEWS_LOOKBACK_MINUTES)
        self.cooldown_hours = env_float("NEWS_ALERT_COOLDOWN_HOURS", NEWS_ALERT_COOLDOWN_HOURS)
        self.max_stock_queries = env_int("NEWS_MAX_STOCK_QUERIES", NEWS_MAX_STOCK_QUERIES)
        self.max_items_per_scan = env_int("NEWS_MAX_ITEMS_PER_SCAN", NEWS_MAX_ITEMS_PER_SCAN)
        self.min_impact_score = env_float("NEWS_MIN_IMPACT_SCORE", NEWS_MIN_IMPACT_SCORE)
        self.market_queries = env_list("NEWS_MARKET_QUERIES", NEWS_MARKET_QUERIES)
        self.high_risk_keywords = env_list("NEWS_HIGH_RISK_KEYWORDS", NEWS_HIGH_RISK_KEYWORDS)
        self.negative_keywords = env_list("NEWS_NEGATIVE_KEYWORDS", NEWS_NEGATIVE_KEYWORDS)
        self.positive_keywords = env_list("NEWS_POSITIVE_KEYWORDS", NEWS_POSITIVE_KEYWORDS)
        self.cache = self._load_cache()
        self.last_scan_at: Optional[datetime] = None

    def scan_once(self, force: bool = False) -> List[NewsImpact]:
        if not self.enabled:
            logger.debug("뉴스 속보 감시 비활성화")
            return []
        now = datetime.now()
        if not force and self.last_scan_at:
            elapsed = (now - self.last_scan_at).total_seconds()
            if elapsed < self.scan_interval_seconds:
                return []
        self.last_scan_at = now

        impacts: List[NewsImpact] = []
        for query_meta in self._build_queries():
            try:
                impacts.extend(self._fetch_impacts(query_meta))
            except Exception as exc:
                logger.debug("뉴스 조회 실패(%s): %s", query_meta["query"], exc)
            time.sleep(min(REQUEST_DELAY_SECONDS, 0.25))
            if len(impacts) >= self.max_items_per_scan:
                break

        fresh_impacts = self._dedupe_and_mark(impacts[: self.max_items_per_scan])
        self._save_cache(fresh_impacts)
        if fresh_impacts:
            self.notifier.send(self._build_news_message(fresh_impacts))
            logger.info("뉴스 속보 알림 %d건 전송", len(fresh_impacts))
        else:
            logger.debug("뉴스 속보 신규 영향 없음")
        return fresh_impacts

    def _build_queries(self) -> List[Dict[str, str]]:
        queries = [{"query": query, "code": "", "name": ""} for query in self.market_queries if query.strip()]
        seen_names = set()
        for item in self._load_candidate_items()[: max(0, self.max_stock_queries)]:
            stock = item.get("stock") if isinstance(item, dict) else None
            if not isinstance(stock, dict):
                continue
            name = str(stock.get("name") or stock.get("Name") or "").strip()
            code = str(stock.get("code") or stock.get("Code") or "").strip()
            if not name or name in seen_names:
                continue
            seen_names.add(name)
            queries.append({"query": f"{name} 주식 속보 실적 공시", "code": code, "name": name})
        return queries

    @staticmethod
    def _load_candidate_items() -> List[Dict[str, object]]:
        if not REALTIME_CANDIDATE_FILE.exists():
            return []
        try:
            with REALTIME_CANDIDATE_FILE.open("r", encoding="utf-8") as file:
                payload = json.load(file)
            items = payload.get("candidates", [])
            return items if isinstance(items, list) else []
        except Exception:
            return []

    def _fetch_impacts(self, query_meta: Dict[str, str]) -> List[NewsImpact]:
        query = query_meta["query"]
        url = self.GOOGLE_NEWS_URL.format(query=quote_plus(query))
        response = requests.get(url, timeout=12, headers={"User-Agent": "Mozilla/5.0"})
        response.raise_for_status()
        root = ET.fromstring(response.content)
        impacts: List[NewsImpact] = []
        cutoff = datetime.now() - timedelta(minutes=max(1, self.lookback_minutes))
        for item in root.findall(".//item"):
            title = unescape((item.findtext("title") or "").strip())
            link = (item.findtext("link") or "").strip()
            published_at = parse_news_datetime(item.findtext("pubDate") or "")
            if published_at < cutoff:
                continue
            source = (item.findtext("source") or "").strip()
            sentiment, impact_score, matched_terms = self._score_title(title)
            if impact_score < self.min_impact_score:
                continue
            impacts.append(
                NewsImpact(
                    query=query,
                    title=title,
                    link=link,
                    source=source or "Google News",
                    published_at=published_at.isoformat(timespec="seconds"),
                    sentiment=sentiment,
                    impact_score=round(impact_score, 1),
                    matched_terms=matched_terms,
                    related_code=query_meta.get("code", ""),
                    related_name=query_meta.get("name", ""),
                )
            )
        return impacts

    def _score_title(self, title: str) -> tuple[str, float, List[str]]:
        text = title.lower()
        high_risk = [term for term in self.high_risk_keywords if term.lower() in text]
        negative = [term for term in self.negative_keywords if term.lower() in text]
        positive = [term for term in self.positive_keywords if term.lower() in text]
        score = len(high_risk) * 4.0 + len(negative) * 2.0 + len(positive) * 2.0
        if high_risk:
            sentiment = "risk"
        elif len(negative) > len(positive):
            sentiment = "negative"
        elif positive:
            sentiment = "positive"
        else:
            sentiment = "watch"
        matched_terms = high_risk + negative + positive
        return sentiment, score, matched_terms

    def _dedupe_and_mark(self, impacts: List[NewsImpact]) -> List[NewsImpact]:
        seen = self.cache.setdefault("seen", {})
        fresh: List[NewsImpact] = []
        cutoff = datetime.now() - timedelta(hours=max(0.1, self.cooldown_hours))
        for key, timestamp in list(seen.items()):
            try:
                if datetime.fromisoformat(str(timestamp)) < cutoff:
                    seen.pop(key, None)
            except ValueError:
                seen.pop(key, None)
        for impact in impacts:
            key = news_cache_key(impact.title, impact.link)
            if key in seen:
                continue
            seen[key] = datetime.now().isoformat(timespec="seconds")
            fresh.append(impact)
        return fresh

    def _load_cache(self) -> Dict[str, object]:
        if not NEWS_ALERT_FILE.exists():
            return {"seen": {}, "alerts": []}
        try:
            with NEWS_ALERT_FILE.open("r", encoding="utf-8") as file:
                payload = json.load(file)
            if not isinstance(payload, dict):
                return {"seen": {}, "alerts": []}
            payload.setdefault("seen", {})
            payload.setdefault("alerts", [])
            return payload
        except Exception as exc:
            logger.warning("뉴스 알림 캐시 로드 실패: %s", exc)
            return {"seen": {}, "alerts": []}

    def _save_cache(self, impacts: List[NewsImpact]) -> None:
        try:
            CACHE_DIR.mkdir(exist_ok=True)
            alerts = list(self.cache.get("alerts") or [])
            alerts.extend(asdict(impact) for impact in impacts)
            self.cache["alerts"] = alerts[-300:]
            with NEWS_ALERT_FILE.open("w", encoding="utf-8") as file:
                json.dump(self.cache, file, ensure_ascii=False, indent=2)
        except Exception as exc:
            logger.warning("뉴스 알림 캐시 저장 실패: %s", exc)

    @staticmethod
    def _build_news_message(impacts: List[NewsImpact]) -> str:
        lines = [
            "📰 뉴스 속보 리스크 레이더",
            f"🗓 {datetime.now().strftime('%Y-%m-%d %H:%M')}",
            f"감지 {len(impacts)}건",
        ]
        for impact in impacts:
            icon = {"risk": "🚨", "negative": "⚠️", "positive": "✅"}.get(impact.sentiment, "🧐")
            related = f"{impact.related_name}({impact.related_code})" if impact.related_name else "시장/테마"
            terms = ", ".join(impact.matched_terms[:5]) or "키워드 없음"
            lines.extend(
                [
                    "",
                    f"{icon} {related} / {impact.sentiment.upper()} / 영향 {impact.impact_score:.1f}",
                    f"{impact.title}",
                    f"출처: {impact.source}, 시간: {impact.published_at}",
                    f"감지어: {terms}",
                    impact.link,
                ]
            )
        lines.extend(["", "※ 속보 감지는 RSS 제목 기반 1차 필터입니다. 주문 전 원문과 공시를 확인하세요."])
        return "\n".join(lines)


class FinancialHealthBot:
    def __init__(self) -> None:
        load_dotenv()
        token = TELEGRAM_TOKEN or os.getenv("TELEGRAM_TOKEN", "")
        chat_id = CHAT_ID or os.getenv("TELEGRAM_CHAT_ID", "")
        self.kis_provider = KISDataProvider()
        self.financial_scanner = FinancialScanner()
        self.market_regime_filter = MarketRegimeFilter()
        self.technical_analyzer = TechnicalAnalyzer(self.kis_provider)
        self.accumulation_analyzer = AccumulationAnalyzer()
        self.factor_scorer = FactorScorer()
        self.thesis_builder = InvestmentThesisBuilder()
        self.decision_policy = DecisionPolicy()
        self.notifier = Notifier(token=token, chat_id=chat_id)
        self.trading_engine = TradingEngine(self.kis_provider, self.notifier)
        self.realtime_scanner = RealtimeScanner(self.kis_provider, self.notifier)
        self.news_monitor = NewsPulseMonitor(self.notifier)
        self.alert_cache: Dict[str, str] = self._load_alert_cache()
        self.state_store = OperationStateStore()

    def run_once(self) -> None:
        logger.info("재무 건전성 종목 발굴 작업 시작")
        started_at = self.state_store.start_job(
            "daily_research",
            {"recommendation_limit": telegram_recommendation_limit()},
        )
        try:
            with BotRunLock(SCAN_LOCK_FILE, "daily_research"):
                reports, regimes = self._discover_reports(send_immediate_alerts=False)
            market_regime = regimes["KOSPI"]
            if not any(regime.risk_on for regime in regimes.values()):
                logger.info("Risk-Off 국면이므로 매수 후보 스캔을 중단합니다.")
                self.notifier.send(self._build_risk_off_message(market_regime))
                self.state_store.finish_job(
                    "daily_research",
                    started_at,
                    "risk_off",
                    {"market_regime": market_regime.summary},
                )
                return

            ranked_reports = self._rank_reports(reports)
            research_pool = ranked_reports[:MAX_REPORTS]
            recommendations = self._top_recommendations(ranked_reports)
            research_summary = self._build_research_summary(ranked_reports, research_pool, recommendations)
            self.realtime_scanner.save_candidate_pool(research_pool, regimes)
            order_plans = self.trading_engine.prepare_buy_plans(recommendations, market_regime)
            self.trading_engine.save_pending_plans(order_plans)
            self.notifier.send(
                self._build_message(
                    reports=recommendations,
                    market_regime=market_regime,
                    order_plans=order_plans,
                    trading_status=self.trading_engine.status_summary(),
                    researched_count=len(ranked_reports),
                    research_pool_count=len(research_pool),
                    research_summary=research_summary,
                )
            )
            self._save_alert_cache()
            self.state_store.finish_job("daily_research", started_at, "success", research_summary)
            logger.info(
                "재무 건전성 종목 발굴 작업 완료. 전체 후보: %d개, 전송 추천: %d개",
                len(ranked_reports),
                len(recommendations),
            )
        except BotLockError as exc:
            logger.warning("재무 건전성 종목 발굴 작업 건너뜀: %s", exc)
            self.state_store.finish_job("daily_research", started_at, "skipped", {"reason": str(exc)})
        except Exception as exc:
            logger.exception("재무 건전성 종목 발굴 작업 실패: %s", exc)
            self.state_store.finish_job("daily_research", started_at, "failed", {"error": str(exc)})
            self.notifier.send(f"⚠️ 재무 건전성 스캐너 오류\n{exc}")

    def prepare_realtime_candidates(self) -> None:
        logger.info("실시간 감시 후보군 준비 시작")
        started_at = self.state_store.start_job(
            "candidate_preparation",
            {"watchlist_limit": self.realtime_scanner.max_watchlist},
        )
        try:
            with BotRunLock(SCAN_LOCK_FILE, "candidate_preparation"):
                reports, regimes = self._discover_reports(send_immediate_alerts=False)
            ranked_reports = self._rank_reports(reports)
            watchlist_reports = ranked_reports[: self.realtime_scanner.max_watchlist]
            self.realtime_scanner.save_candidate_pool(watchlist_reports, regimes)
            self.notifier.send(
                self.realtime_scanner.build_candidate_message(
                    watchlist_reports,
                    regimes,
                    display_limit=telegram_recommendation_limit(),
                    researched_count=len(ranked_reports),
                )
            )
            logger.info(
                "실시간 감시 후보군 준비 완료. 전체 후보: %d개, 내부 감시: %d개",
                len(ranked_reports),
                len(watchlist_reports),
            )
            self.state_store.finish_job(
                "candidate_preparation",
                started_at,
                "success",
                self._build_research_summary(
                    ranked_reports,
                    watchlist_reports,
                    self._top_recommendations(ranked_reports),
                ),
            )
        except BotLockError as exc:
            logger.warning("실시간 감시 후보군 준비 건너뜀: %s", exc)
            self.state_store.finish_job("candidate_preparation", started_at, "skipped", {"reason": str(exc)})
        except Exception as exc:
            logger.exception("실시간 감시 후보군 준비 실패: %s", exc)
            self.state_store.finish_job("candidate_preparation", started_at, "failed", {"error": str(exc)})
            self.notifier.send(f"⚠️ 실시간 후보군 준비 오류\n{exc}")

    def run_realtime_once(self, force: bool = False) -> None:
        started_at = self.state_store.start_job("realtime_scan", {"force": force})
        try:
            now = datetime.now()
            if (
                not force
                and (
                    not self.realtime_scanner.enabled
                    or not is_time_between(now, self.realtime_scanner.scan_start, self.realtime_scanner.scan_end)
                )
            ):
                self.state_store.finish_job(
                    "realtime_scan",
                    started_at,
                    "skipped",
                    {"reason": "outside_realtime_window"},
                )
                return
            with BotRunLock(REALTIME_LOCK_FILE, "realtime_scan", stale_minutes=30):
                regimes = self.market_regime_filter.analyze_by_market()
                signals = self.realtime_scanner.scan_once(regimes, force=force)
            self.state_store.finish_job(
                "realtime_scan",
                started_at,
                "success",
                {"signals": len(signals)},
            )
        except BotLockError as exc:
            logger.debug("실시간 스캔 건너뜀: %s", exc)
            self.state_store.finish_job("realtime_scan", started_at, "skipped", {"reason": str(exc)})
        except Exception as exc:
            logger.exception("실시간 스캔 실패: %s", exc)
            self.state_store.finish_job("realtime_scan", started_at, "failed", {"error": str(exc)})
            self.notifier.send(f"⚠️ 실시간 스캔 오류\n{exc}")

    def run_news_once(self, force: bool = False) -> None:
        started_at = self.state_store.start_job("news_scan", {"force": force})
        try:
            with BotRunLock(NEWS_LOCK_FILE, "news_scan", stale_minutes=30):
                impacts = self.news_monitor.scan_once(force=force)
            self.state_store.finish_job("news_scan", started_at, "success", {"impacts": len(impacts)})
        except BotLockError as exc:
            logger.debug("뉴스 속보 감시 건너뜀: %s", exc)
            self.state_store.finish_job("news_scan", started_at, "skipped", {"reason": str(exc)})
        except Exception as exc:
            logger.exception("뉴스 속보 감시 실패: %s", exc)
            self.state_store.finish_job("news_scan", started_at, "failed", {"error": str(exc)})
            self.notifier.send(f"⚠️ 뉴스 속보 감시 오류\n{exc}")

    def run_trading_once(self) -> None:
        logger.info("자동매매 대기 주문 실행 시작")
        started_at = self.state_store.start_job("trading_execution")
        try:
            with BotRunLock(TRADING_LOCK_FILE, "trading_execution", stale_minutes=60):
                market_regime = self.market_regime_filter.analyze()
                if not market_regime.risk_on:
                    self.trading_engine.discard_pending_plans(
                        f"시장 국면이 Risk-Off입니다. {market_regime.summary}"
                    )
                    self.state_store.finish_job(
                        "trading_execution",
                        started_at,
                        "risk_off",
                        {"market_regime": market_regime.summary},
                    )
                    return
                results = self.trading_engine.execute_pending_orders()
            self.state_store.finish_job(
                "trading_execution",
                started_at,
                "success",
                {"orders": len(results)},
            )
        except BotLockError as exc:
            logger.warning("자동매매 실행 건너뜀: %s", exc)
            self.state_store.finish_job("trading_execution", started_at, "skipped", {"reason": str(exc)})
        except Exception as exc:
            logger.exception("자동매매 대기 주문 실행 실패: %s", exc)
            self.state_store.finish_job("trading_execution", started_at, "failed", {"error": str(exc)})
            self.notifier.send(f"⚠️ 자동매매 실행 오류\n{exc}")

    def _discover_reports(self, send_immediate_alerts: bool) -> tuple[List[DiscoveryReport], Dict[str, MarketRegime]]:
        regimes = self.market_regime_filter.analyze_by_market()
        if not any(regime.risk_on for regime in regimes.values()):
            return [], regimes

        universe = self.financial_scanner.fetch_universe()
        stock_map = {stock.code: stock for stock in universe}
        financially_strong = self.financial_scanner.scan(universe)

        reports: List[DiscoveryReport] = []
        min_factor_score = factor_score_minimum()
        watchlist_min_factor = watchlist_factor_score_minimum()
        watchlist_min_thesis = watchlist_investment_thesis_minimum()
        watchlist_min_quality = watchlist_data_quality_min_score()
        radar_min_factor = radar_factor_score_minimum()
        radar_min_thesis = radar_investment_thesis_minimum()
        radar_min_quality = radar_data_quality_min_score()
        strict_validation = env_bool("STRICT_DATA_VALIDATION", STRICT_DATA_VALIDATION)
        technical_mode = "tiered" if watchlist_enabled() or radar_enabled() else "strict"
        for metrics in financially_strong:
            stock_meta = stock_map.get(metrics.code)
            if stock_meta is None:
                continue

            market_regime = self.market_regime_filter.select_for_market(stock_meta.market, regimes)
            if not market_regime.risk_on:
                continue

            technicals = self.technical_analyzer.analyze(stock_meta, market_regime, mode=technical_mode)
            if technicals is None:
                continue
            signal_stage = self._combine_signal_stage(metrics.signal_stage, technicals.signal_stage)
            technicals.signal_stage = signal_stage

            accumulation = self.accumulation_analyzer.analyze(stock_meta)
            if ENABLE_SMART_MONEY_FILTER and accumulation is None:
                if signal_stage == "strict" and watchlist_enabled() and not watchlist_requires_smart_money():
                    signal_stage = "watchlist"
                    technicals.signal_stage = signal_stage
                elif signal_stage in {"watchlist", "radar"} and not watchlist_requires_smart_money():
                    pass
                elif signal_stage == "strict" and radar_enabled():
                    signal_stage = "radar"
                    technicals.signal_stage = signal_stage
                else:
                    continue

            report = DiscoveryReport(
                stock=stock_meta,
                financials=metrics,
                technicals=technicals,
                accumulation=accumulation,
                reason=self._build_reason(metrics, technicals),
                signal_stage=signal_stage,
            )
            data_quality = combine_report_data_quality(report)
            report.data_quality_score = data_quality.score
            report.data_quality_grade = data_quality.grade
            report.data_quality_warnings = data_quality.warnings
            strict_quality_min = data_quality_min_score()
            if (
                signal_stage == "strict"
                and watchlist_enabled()
                and strict_validation
                and data_quality.score < strict_quality_min
                and data_quality.score >= watchlist_min_quality
            ):
                signal_stage = "watchlist"
                report.signal_stage = signal_stage
                report.technicals.signal_stage = signal_stage
            if (
                signal_stage in {"strict", "watchlist"}
                and radar_enabled()
                and strict_validation
                and data_quality.score < (watchlist_min_quality if signal_stage == "watchlist" else strict_quality_min)
                and data_quality.score >= radar_min_quality
            ):
                signal_stage = "radar"
                report.signal_stage = signal_stage
                report.technicals.signal_stage = signal_stage
            if signal_stage == "radar":
                required_quality = radar_min_quality
            elif signal_stage == "watchlist":
                required_quality = watchlist_min_quality
            else:
                required_quality = strict_quality_min
            if strict_validation and data_quality.score < required_quality:
                logger.debug(
                    "%s(%s) %s 데이터 품질 %.1f 미달(기준 %.1f): %s",
                    report.stock.name,
                    report.stock.code,
                    format_discovery_stage(signal_stage),
                    data_quality.score,
                    required_quality,
                    "; ".join(data_quality.warnings),
                )
                continue
            report.score = self.factor_scorer.score(report, market_regime)
            if (
                signal_stage == "strict"
                and watchlist_enabled()
                and report.score.total < min_factor_score
                and report.score.total >= watchlist_min_factor
            ):
                signal_stage = "watchlist"
                report.signal_stage = signal_stage
                report.technicals.signal_stage = signal_stage
            if (
                signal_stage in {"strict", "watchlist"}
                and radar_enabled()
                and report.score.total < (watchlist_min_factor if signal_stage == "watchlist" else min_factor_score)
                and report.score.total >= radar_min_factor
            ):
                signal_stage = "radar"
                report.signal_stage = signal_stage
                report.technicals.signal_stage = signal_stage
            if signal_stage == "radar":
                required_factor_score = radar_min_factor
            elif signal_stage == "watchlist":
                required_factor_score = watchlist_min_factor
            else:
                required_factor_score = min_factor_score
            if report.score.total < required_factor_score:
                logger.debug(
                    "%s(%s) %s 팩터 점수 %.1f 미달(기준 %.1f)",
                    report.stock.name,
                    report.stock.code,
                    format_discovery_stage(signal_stage),
                    report.score.total,
                    required_factor_score,
                )
                continue
            report.thesis = self.thesis_builder.build(report)
            strict_thesis_min = investment_thesis_minimum()
            if (
                signal_stage == "strict"
                and watchlist_enabled()
                and report.thesis.total < strict_thesis_min
                and report.thesis.total >= watchlist_min_thesis
            ):
                signal_stage = "watchlist"
                report.signal_stage = signal_stage
                report.technicals.signal_stage = signal_stage
            if (
                signal_stage in {"strict", "watchlist"}
                and radar_enabled()
                and report.thesis.total < (watchlist_min_thesis if signal_stage == "watchlist" else strict_thesis_min)
                and report.thesis.total >= radar_min_thesis
            ):
                signal_stage = "radar"
                report.signal_stage = signal_stage
                report.technicals.signal_stage = signal_stage
            if signal_stage == "radar":
                required_thesis_score = radar_min_thesis
            elif signal_stage == "watchlist":
                required_thesis_score = watchlist_min_thesis
            else:
                required_thesis_score = strict_thesis_min
            if (
                env_bool("ENABLE_INVESTMENT_THESIS_FILTER", ENABLE_INVESTMENT_THESIS_FILTER)
                and report.thesis.total < required_thesis_score
            ):
                logger.debug(
                    "%s(%s) %s 투자 가설 %.1f 미달(기준 %.1f)",
                    report.stock.name,
                    report.stock.code,
                    format_discovery_stage(signal_stage),
                    report.thesis.total,
                    required_thesis_score,
                )
                continue
            report.decision = self.decision_policy.classify(report)
            if report.decision.tier == "보류":
                logger.debug(
                    "%s(%s) 의사결정 보류: %s",
                    report.stock.name,
                    report.stock.code,
                    "; ".join(report.decision.vetoes),
                )
                continue
            reports.append(report)
            if send_immediate_alerts:
                self._send_immediate_alert_if_needed(report, market_regime)

        return reports, regimes

    @staticmethod
    def _combine_signal_stage(*stages: str) -> str:
        priority = {"radar": 2, "watchlist": 1, "strict": 0}
        clean_stages = [stage for stage in stages if stage in priority]
        if not clean_stages:
            return "strict"
        return max(clean_stages, key=lambda stage: priority[stage])

    def _send_immediate_alert_if_needed(self, report: DiscoveryReport, market_regime: MarketRegime) -> None:
        if report.signal_stage == "radar":
            logger.debug(
                "%s(%s) 레이더 후보는 최종 리포트에만 포함",
                report.stock.name,
                report.stock.code,
            )
            return

        cache_key = report.stock.code
        cached_at_text = self.alert_cache.get(cache_key)

        if cached_at_text:
            try:
                cached_at = datetime.fromisoformat(cached_at_text)
                if datetime.now() - cached_at < timedelta(hours=IMMEDIATE_ALERT_COOLDOWN_HOURS):
                    logger.info("%s(%s) 즉시 알림 중복 방지", report.stock.name, report.stock.code)
                    return
            except ValueError:
                pass

        if self.notifier.send(self._build_immediate_alert_message(report, market_regime)):
            self.alert_cache[cache_key] = datetime.now().isoformat(timespec="seconds")
            self._save_alert_cache()

    @staticmethod
    def _build_immediate_alert_message(report: DiscoveryReport, market_regime: MarketRegime) -> str:
        financials = report.financials
        technicals = report.technicals
        return (
            "🚨 종목 발굴 즉시 알림\n"
            f"🛡️ 시장 국면: {market_regime.summary} / Risk-On\n\n"
            f"💎 [{report.stock.name}({report.stock.code})]\n"
            f"🪜 후보 단계: {format_discovery_stage(report.signal_stage)}\n"
            f"⭐ 종합점수: {format_factor_score(report.score)}\n"
            f"🧠 투자 가설: {format_investment_thesis(report.thesis)}\n"
            f"🧭 의사결정: {format_signal_decision(report.decision)}\n"
            f"🧾 데이터 신뢰도: {format_data_quality(report.data_quality_score, report.data_quality_grade, report.data_quality_warnings)}\n"
            f"💰 시가총액: {format_market_cap(financials.market_cap)}\n"
            f"💧 당일 거래대금: {format_market_cap(report.stock.trading_value)}\n"
            f"📊 재무: 부채비율 {financials.debt_to_equity:.1f}%, "
            f"유동비율 {financials.current_ratio:.1f}%, PBR {financials.pbr:.2f}, "
            f"ROE {format_optional_percent(financials.roe)}\n"
            f"📈 타점: {technicals.trend_summary} "
            f"(현재가 {technicals.current_price:,.0f}원, RSI {technicals.rsi:.1f})\n"
            f"🚀 상대강도: 60일 {technicals.relative_strength_60d:+.1f}%p, "
            f"20일 수익률 {technicals.return_20d:+.1f}%, "
            f"120~20일 모멘텀 {technicals.momentum_120_20d:+.1f}%\n"
            f"🛡️ 손절선: {technicals.stop_loss:,.0f}원 "
            f"(ATR {technicals.atr:,.0f}원 기준)\n"
            f"🏦 수급: {format_accumulation(report.accumulation)}\n"
            f"💡 이유: {report.reason}"
        )

    @staticmethod
    def _load_alert_cache() -> Dict[str, str]:
        if not ALERT_CACHE_FILE.exists():
            return {}
        try:
            with ALERT_CACHE_FILE.open("r", encoding="utf-8") as file:
                data = json.load(file)
            return {str(code): str(timestamp) for code, timestamp in data.items()}
        except Exception as exc:
            logger.warning("알림 캐시 로드 실패: %s", exc)
            return {}

    def _save_alert_cache(self) -> None:
        try:
            CACHE_DIR.mkdir(exist_ok=True)
            with ALERT_CACHE_FILE.open("w", encoding="utf-8") as file:
                json.dump(self.alert_cache, file, ensure_ascii=False, indent=2)
        except Exception as exc:
            logger.warning("알림 캐시 저장 실패: %s", exc)

    @staticmethod
    def _rank_reports(reports: List[DiscoveryReport]) -> List[DiscoveryReport]:
        return sorted(
            reports,
            key=lambda report: (
                -(report.score.total if report.score else 0.0),
                -(1 if report.decision and report.decision.trade_eligible else 0),
                decision_rank(report.decision),
                -(report.thesis.total if report.thesis else 0.0),
                -report.data_quality_score,
                -((report.accumulation.net_buy_amount_to_market_cap if report.accumulation and report.accumulation.net_buy_amount_to_market_cap else 0.0)),
                -((report.accumulation.net_buy_ratio if report.accumulation else 0.0)),
                report.financials.debt_to_equity,
                report.technicals.volatility,
            ),
        )

    @staticmethod
    def _top_recommendations(reports: List[DiscoveryReport]) -> List[DiscoveryReport]:
        return FinancialHealthBot._rank_reports(reports)[:telegram_recommendation_limit()]

    @staticmethod
    def _build_research_summary(
        ranked_reports: List[DiscoveryReport],
        research_pool: List[DiscoveryReport],
        recommendations: List[DiscoveryReport],
    ) -> Dict[str, object]:
        stage_counts = {"strict": 0, "watchlist": 0, "radar": 0}
        decision_counts: Dict[str, int] = {}
        scores = [report.score.total for report in ranked_reports if report.score is not None]
        for report in ranked_reports:
            stage = report.signal_stage if report.signal_stage in stage_counts else "strict"
            stage_counts[stage] += 1
            tier = report.decision.tier if report.decision else "N/A"
            decision_counts[tier] = decision_counts.get(tier, 0) + 1
        cutoff_score = recommendations[-1].score.total if recommendations and recommendations[-1].score else None
        return {
            "total_candidates": len(ranked_reports),
            "research_pool_count": len(research_pool),
            "recommendation_count": len(recommendations),
            "recommendation_limit": telegram_recommendation_limit(),
            "stage_counts": stage_counts,
            "decision_counts": decision_counts,
            "highest_score": round(max(scores), 1) if scores else None,
            "lowest_score": round(min(scores), 1) if scores else None,
            "cutoff_score": round(cutoff_score, 1) if cutoff_score is not None else None,
            "top_recommendations": [
                FinancialHealthBot._report_summary(report, rank)
                for rank, report in enumerate(recommendations, start=1)
            ],
        }

    @staticmethod
    def _report_summary(report: DiscoveryReport, rank: int) -> Dict[str, object]:
        return {
            "rank": rank,
            "code": report.stock.code,
            "name": report.stock.name,
            "stage": report.signal_stage,
            "stage_label": format_discovery_stage(report.signal_stage),
            "decision": report.decision.tier if report.decision else "N/A",
            "score": round(report.score.total, 1) if report.score else None,
            "thesis": round(report.thesis.total, 1) if report.thesis else None,
            "data_quality": round(report.data_quality_score, 1),
            "rsi": round(report.technicals.rsi, 1),
            "relative_strength_60d": round(report.technicals.relative_strength_60d, 1),
            "pbr": round(report.financials.pbr, 2),
        }

    @staticmethod
    def _build_reason(metrics: FinancialMetrics, technicals: TechnicalSnapshot) -> str:
        margin_text = "영업이익률 확인 가능"
        if metrics.operating_margin is not None:
            margin_text = f"영업이익률 {metrics.operating_margin:.1f}%"
        return (
            f"부채비율 {metrics.debt_to_equity:.1f}%와 유동비율 {metrics.current_ratio:.1f}%로 재무 안정성이 높고, "
            f"PBR {metrics.pbr:.2f}로 자산가치 대비 저평가 구간입니다. "
            f"{margin_text}, 120~20일 중기 모멘텀 {technicals.momentum_120_20d:+.1f}%와 "
            f"180일 고점 근접도 {technicals.high_proximity_180d:.1f}%로 추세 지속성을 확인했고, "
            f"목표/손절 손익비는 {technicals.risk_reward_ratio:.2f}입니다."
        )

    @staticmethod
    def _build_message(
        reports: List[DiscoveryReport],
        market_regime: MarketRegime,
        order_plans: Optional[List[OrderPlan]] = None,
        trading_status: str = "",
        researched_count: Optional[int] = None,
        research_pool_count: Optional[int] = None,
        research_summary: Optional[Dict[str, object]] = None,
    ) -> str:
        today = datetime.now().strftime("%Y-%m-%d")
        total_researched = researched_count if researched_count is not None else len(reports)
        recommendation_limit = telegram_recommendation_limit()
        if not reports:
            return (
                f"📊 재무 건전성 알짜 기업 스캐너\n"
                f"🗓 {today}\n\n"
                f"🛡️ 시장 국면: {market_regime.summary} / Risk-On\n\n"
                f"🔎 전체 리서치 후보 {total_researched}개\n"
                "오늘은 텔레그램으로 보낼 상위 추천 종목이 없습니다."
            )

        lines = [
            "📊 재무 건전성 알짜 기업 스캐너",
            f"🗓 {today}",
            f"🛡️ 시장 국면: {market_regime.summary} / Risk-On",
            f"🔎 전체 리서치 후보 {total_researched}개",
            f"🏆 텔레그램 추천: 종합점수 상위 {len(reports)}개 / 표시 한도 {recommendation_limit}개",
            "🔢 정렬 기준: 종합점수 높은 순",
        ]
        summary_lines = format_research_summary(research_summary)
        if summary_lines:
            lines.extend(summary_lines)
        if research_pool_count is not None and research_pool_count > len(reports):
            lines.append(f"📁 내부 감시/캐시 보관: 상위 {research_pool_count}개")

        for rank, report in enumerate(reports, start=1):
            financials = report.financials
            technicals = report.technicals
            accumulation = report.accumulation
            lines.extend(
                [
                    "",
                    f"🏆 TOP {rank} [{report.stock.name}({report.stock.code})] 발굴 리포트",
                    f"🪜 후보 단계: {format_discovery_stage(report.signal_stage)}",
                    f"⭐ 종합점수: {format_factor_score(report.score)}",
                    f"🧠 투자 가설: {format_investment_thesis(report.thesis)}",
                    f"🧭 의사결정: {format_signal_decision(report.decision)}",
                    f"🧾 데이터 신뢰도: {format_data_quality(report.data_quality_score, report.data_quality_grade, report.data_quality_warnings)}",
                    f"💰 시가총액: {format_market_cap(financials.market_cap)}",
                    f"💧 당일 거래대금: {format_market_cap(report.stock.trading_value)}",
                    (
                        "📊 재무 핵심 지표: "
                        f"부채비율 {financials.debt_to_equity:.1f}%, "
                        f"유동비율 {financials.current_ratio:.1f}%, "
                        f"PBR {financials.pbr:.2f}, "
                        f"PER {format_optional_number(financials.per)}, "
                        f"ROE {format_optional_percent(financials.roe)}, "
                        f"영업이익률 {format_optional_percent(financials.operating_margin)}"
                    ),
                    (
                        "🧪 가치함정 점검: "
                        f"매출 YoY {format_optional_percent(financials.revenue_growth_yoy)}, "
                        f"영업이익 YoY {format_optional_percent(financials.operating_income_growth_yoy)}, "
                        f"소스 {financials.financial_source}"
                    ),
                    (
                        "📈 기술적 상황: "
                        f"{technicals.trend_summary} "
                        f"(현재가 {technicals.current_price:,.0f}원, "
                        f"RSI {technicals.rsi:.1f}, "
                        f"20일선 {technicals.ma20:,.0f}원, "
                        f"60일 상대강도 {technicals.relative_strength_60d:+.1f}%p)"
                    ),
                    (
                        "🚀 모멘텀 품질: "
                        f"20일 {technicals.return_20d:+.1f}%, "
                        f"60일 {technicals.return_60d:+.1f}%, "
                        f"120일 {technicals.return_120d:+.1f}%, "
                        f"60일 최대낙폭 {technicals.max_drawdown_60d:.1f}%"
                    ),
                    (
                        "🧭 중기 구조: "
                        f"120~20일 모멘텀 {technicals.momentum_120_20d:+.1f}%, "
                        f"180일 고점 근접도 {technicals.high_proximity_180d:.1f}%, "
                        f"목표/손절 손익비 {technicals.risk_reward_ratio:.2f}"
                    ),
                    (
                        "🛡️ 리스크 관리: "
                        f"ATR {technicals.atr:,.0f}원 기준 손절선 "
                        f"{technicals.stop_loss:,.0f}원"
                    ),
                    (
                        "📉 변동성: "
                        f"종목 {technicals.volatility * 100:.1f}% / "
                        f"시장 {technicals.market_volatility * 100:.1f}%"
                    ),
                    f"🏦 수급 매집: {format_accumulation(accumulation)}",
                    f"💡 추천 이유: {report.reason}",
                ]
            )

        if order_plans:
            lines.extend(
                [
                    "",
                    "🤖 자동매매 주문 계획",
                    f"상태: {trading_status or 'N/A'}",
                ]
            )
            for plan in order_plans:
                lines.append(format_order_plan(plan))
        elif trading_status:
            lines.extend(["", f"🤖 자동매매 상태: {trading_status}"])

        lines.extend(
            [
                "",
                "※ 본 메시지는 자동화된 재무/기술 필터링 결과이며 투자 수익을 보장하지 않습니다.",
            ]
        )
        return "\n".join(lines)

    @staticmethod
    def _build_risk_off_message(market_regime: MarketRegime) -> str:
        today = datetime.now().strftime("%Y-%m-%d")
        return (
            "🛡️ Risk-Off 경고\n"
            f"🗓 {today}\n\n"
            f"{market_regime.summary}\n"
            "코스피가 200일 이동평균선 아래에 있어 신규 매수 알림을 비활성화합니다.\n"
            "현금 비중 확대와 보유 종목 리스크 점검이 우선입니다."
        )


def latest_frame_date(frame: pd.DataFrame) -> Optional[pd.Timestamp]:
    if frame is None or frame.empty:
        return None
    index = frame.index
    if not isinstance(index, pd.DatetimeIndex):
        index = pd.to_datetime(index, errors="coerce")
    latest = index.max()
    if pd.isna(latest):
        return None
    return latest


def combine_report_data_quality(report: DiscoveryReport) -> DataQualityReport:
    financial_quality = DataQualityValidator._report(
        report.financials.financial_source,
        report.financials.data_quality_score,
        [],
        report.financials.data_quality_warnings,
    )
    technical_quality = DataQualityValidator._report(
        report.technicals.price_source or "가격",
        report.technicals.data_quality_score,
        [],
        report.technicals.data_quality_warnings,
    )
    reports = [financial_quality, technical_quality]
    weights = [0.40, 0.45]
    if report.accumulation is not None:
        reports.append(
            DataQualityValidator._report(
                "수급",
                report.accumulation.data_quality_score,
                [],
                report.accumulation.data_quality_warnings,
            )
        )
        weights.append(0.15)
    return DataQualityValidator.merge_reports("통합 데이터", reports, weights=weights)


def quality_grade(score: float) -> str:
    if score >= 95:
        return "A+"
    if score >= 90:
        return "A"
    if score >= 80:
        return "B"
    if score >= 70:
        return "C"
    if score >= 60:
        return "D"
    return "F"


def format_market_cap(value: Optional[float]) -> str:
    if value is None:
        return "N/A"
    return f"{value / 100_000_000:,.0f}억 원"


def format_optional_percent(value: Optional[float]) -> str:
    if value is None:
        return "N/A"
    return f"{value:.1f}%"


def format_optional_number(value: Optional[float]) -> str:
    if value is None:
        return "N/A"
    return f"{value:.1f}"


def format_factor_score(score: Optional[FactorScore]) -> str:
    if score is None:
        return "N/A"
    return (
        f"{score.total:.1f}/100({score.grade}) "
        f"[재무 {score.financial:.1f}, 수급 {score.accumulation:.1f}, "
        f"기술 {score.technical:.1f}, 리스크 {score.risk:.1f}]"
    )


def format_investment_thesis(thesis: Optional[InvestmentThesis]) -> str:
    if thesis is None:
        return "N/A"
    text = (
        f"{thesis.total:.1f}/100({thesis.label}) "
        f"[품질 {thesis.quality:.1f}, 가치 {thesis.value:.1f}, 모멘텀 {thesis.momentum:.1f}, "
        f"심리 {thesis.psychology:.1f}, 손익비 {thesis.asymmetry:.1f}]"
    )
    if thesis.strengths:
        text += " / 강점: " + " · ".join(thesis.strengths[:2])
    if thesis.concerns:
        text += " / 주의: " + " · ".join(thesis.concerns[:2])
    return text


def format_research_summary(summary: Optional[Dict[str, object]]) -> List[str]:
    if not summary:
        return []
    stage_counts = summary.get("stage_counts")
    score_text = "점수 범위 N/A"
    highest_score = summary.get("highest_score")
    cutoff_score = summary.get("cutoff_score")
    lowest_score = summary.get("lowest_score")
    if highest_score is not None and cutoff_score is not None and lowest_score is not None:
        score_text = f"최고 {highest_score}, 추천 컷 {cutoff_score}, 전체 최저 {lowest_score}"

    lines = [f"📊 점수 범위: {score_text}"]
    if isinstance(stage_counts, dict):
        lines.append(
            "🧮 후보 분포: "
            f"정규 {int(stage_counts.get('strict', 0))} / "
            f"관찰 {int(stage_counts.get('watchlist', 0))} / "
            f"레이더 {int(stage_counts.get('radar', 0))}"
        )
    decision_counts = summary.get("decision_counts")
    if isinstance(decision_counts, dict) and decision_counts:
        ordered = sorted(decision_counts.items(), key=lambda item: str(item[0]))
        lines.append("🧭 판단 분포: " + " / ".join(f"{key} {value}" for key, value in ordered[:5]))
    return lines


def decision_rank(decision: Optional[SignalDecision]) -> int:
    if decision is None:
        return 9
    order = {
        "자동매매 가능": 0,
        "강력 후보": 1,
        "관심 후보": 2,
        "레이더 후보": 3,
        "보류": 8,
    }
    return order.get(decision.tier, 5)


def format_signal_decision(decision: Optional[SignalDecision]) -> str:
    if decision is None:
        return "N/A"
    text = f"{decision.tier} / {decision.action}"
    if decision.reasons:
        text += " / 근거: " + " · ".join(decision.reasons[:4])
    if decision.vetoes:
        text += " / 보류: " + " · ".join(decision.vetoes[:3])
    return text


def format_discovery_stage(stage: str) -> str:
    if stage == "radar":
        return "레이더 후보"
    if stage == "watchlist":
        return "관찰 후보"
    if stage == "strict":
        return "정규 후보"
    return stage or "정규 후보"


def format_data_quality(score: float, grade: str, warnings: Optional[List[str]] = None) -> str:
    if score <= 0:
        return "N/A"
    warning_text = ""
    if warnings:
        warning_text = " / 주의: " + "; ".join(warnings[:2])
    return f"{score:.1f}/100({grade}){warning_text}"


def format_accumulation(value: Optional[AccumulationSnapshot]) -> str:
    if value is None:
        return "N/A"
    return (
        f"{value.days}일 외국인/기관 합산 {value.combined_net_buy:,.0f}주 순매수, "
        f"상장주식수 대비 {value.net_buy_ratio * 100:.2f}%, "
        f"순매수금액 {value.combined_net_buy_amount / 100_000_000:.1f}억 원, "
        f"시총 대비 {(value.net_buy_amount_to_market_cap or 0) * 100:.2f}%, "
        f"주가 변화 {value.price_change * 100:+.1f}%"
    )


def format_order_plan(plan: OrderPlan) -> str:
    order_type = "시장가" if plan.order_type == "01" else "지정가"
    return (
        f"- [{plan.name}({plan.code})] {order_type} {plan.quantity}주, "
        f"예상 {plan.estimated_value:,.0f}원, "
        f"예상위험 {plan.estimated_risk:,.0f}원, 손절 {plan.stop_loss:,.0f}원"
    )


def clamp(value: float, minimum: float, maximum: float) -> float:
    return max(minimum, min(maximum, value))


def env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


def env_int(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None or value.strip() == "":
        return default
    try:
        return int(float(value.replace(",", "")))
    except ValueError:
        logger.warning("%s=%s 값을 정수로 해석할 수 없어 기본값 %s 사용", name, value, default)
        return default


def env_float(name: str, default: float) -> float:
    value = os.getenv(name)
    if value is None or value.strip() == "":
        return float(default)
    try:
        return float(value.replace(",", ""))
    except ValueError:
        logger.warning("%s=%s 값을 숫자로 해석할 수 없어 기본값 %s 사용", name, value, default)
        return float(default)


def env_list(name: str, default: List[str]) -> List[str]:
    value = os.getenv(name)
    if value is None or value.strip() == "":
        return list(default)
    separators = ["|", "\n", ";"]
    parts = [value]
    for separator in separators:
        if separator in value:
            parts = value.split(separator)
            break
    return [part.strip() for part in parts if part.strip()]


def active_strategy_profile() -> str:
    profile = os.getenv("STRATEGY_PROFILE", STRATEGY_PROFILE).strip().lower()
    if profile not in {"conservative", "institutional", "balanced", "aggressive"}:
        logger.warning("알 수 없는 STRATEGY_PROFILE=%s, institutional 사용", profile)
        return "institutional"
    return profile


def env_float_profile(name: str, default: float, profile_defaults: Dict[str, float]) -> float:
    if os.getenv(name) is not None:
        return env_float(name, default)
    return float(profile_defaults.get(active_strategy_profile(), default))


def factor_score_minimum() -> float:
    return env_float_profile(
        "MIN_FACTOR_SCORE",
        MIN_FACTOR_SCORE,
        {"conservative": 80.0, "institutional": 72.0, "balanced": 68.0, "aggressive": 64.0},
    )


def watchlist_enabled() -> bool:
    return env_bool("WATCHLIST_ENABLED", WATCHLIST_ENABLED)


def watchlist_requires_smart_money() -> bool:
    return env_bool("WATCHLIST_REQUIRE_SMART_MONEY", WATCHLIST_REQUIRE_SMART_MONEY)


def watchlist_factor_score_minimum() -> float:
    return env_float_profile(
        "WATCHLIST_MIN_FACTOR_SCORE",
        WATCHLIST_MIN_FACTOR_SCORE,
        {"conservative": 64.0, "institutional": 58.0, "balanced": 56.0, "aggressive": 52.0},
    )


def watchlist_investment_thesis_minimum() -> float:
    return env_float_profile(
        "WATCHLIST_MIN_INVESTMENT_THESIS_SCORE",
        WATCHLIST_MIN_INVESTMENT_THESIS_SCORE,
        {"conservative": 60.0, "institutional": 55.0, "balanced": 53.0, "aggressive": 50.0},
    )


def watchlist_data_quality_min_score() -> float:
    return env_float_profile(
        "WATCHLIST_MIN_DATA_QUALITY_SCORE",
        WATCHLIST_MIN_DATA_QUALITY_SCORE,
        {"conservative": 75.0, "institutional": 68.0, "balanced": 65.0, "aggressive": 60.0},
    )


def watchlist_relative_strength_minimum() -> float:
    return env_float_profile(
        "WATCHLIST_MIN_RELATIVE_STRENGTH_60D",
        WATCHLIST_MIN_RELATIVE_STRENGTH_60D,
        {"conservative": -2.0, "institutional": -5.0, "balanced": -6.0, "aggressive": -8.0},
    )


def radar_enabled() -> bool:
    return env_bool("RADAR_ENABLED", RADAR_ENABLED)


def radar_factor_score_minimum() -> float:
    return env_float_profile(
        "RADAR_MIN_FACTOR_SCORE",
        RADAR_MIN_FACTOR_SCORE,
        {"conservative": 45.0, "institutional": 35.0, "balanced": 32.0, "aggressive": 28.0},
    )


def radar_investment_thesis_minimum() -> float:
    return env_float_profile(
        "RADAR_MIN_INVESTMENT_THESIS_SCORE",
        RADAR_MIN_INVESTMENT_THESIS_SCORE,
        {"conservative": 45.0, "institutional": 35.0, "balanced": 32.0, "aggressive": 28.0},
    )


def radar_data_quality_min_score() -> float:
    return env_float_profile(
        "RADAR_MIN_DATA_QUALITY_SCORE",
        RADAR_MIN_DATA_QUALITY_SCORE,
        {"conservative": 60.0, "institutional": 50.0, "balanced": 45.0, "aggressive": 40.0},
    )


def radar_relative_strength_minimum() -> float:
    return env_float_profile(
        "RADAR_MIN_RELATIVE_STRENGTH_60D",
        RADAR_MIN_RELATIVE_STRENGTH_60D,
        {"conservative": -12.0, "institutional": -20.0, "balanced": -25.0, "aggressive": -30.0},
    )


def investment_thesis_minimum() -> float:
    return env_float_profile(
        "MIN_INVESTMENT_THESIS_SCORE",
        MIN_INVESTMENT_THESIS_SCORE,
        {"conservative": 76.0, "institutional": 70.0, "balanced": 66.0, "aggressive": 60.0},
    )


def data_quality_min_score() -> float:
    return env_float_profile(
        "MIN_DATA_QUALITY_SCORE",
        MIN_DATA_QUALITY_SCORE,
        {"conservative": 90.0, "institutional": 80.0, "balanced": 75.0, "aggressive": 70.0},
    )


def telegram_recommendation_limit() -> int:
    return max(1, env_int("TELEGRAM_RECOMMENDATION_LIMIT", TELEGRAM_RECOMMENDATION_LIMIT))


def parse_hhmm(value: str) -> tuple[int, int]:
    hour_text, minute_text = value.strip().split(":", 1)
    return int(hour_text), int(minute_text)


def is_time_between(now: datetime, start_hhmm: str, end_hhmm: str) -> bool:
    start_hour, start_minute = parse_hhmm(start_hhmm)
    end_hour, end_minute = parse_hhmm(end_hhmm)
    start = now.replace(hour=start_hour, minute=start_minute, second=0, microsecond=0)
    end = now.replace(hour=end_hour, minute=end_minute, second=0, microsecond=0)
    return start <= now <= end


def market_elapsed_ratio(now: datetime) -> float:
    start_hour, start_minute = parse_hhmm("09:00")
    end_hour, end_minute = parse_hhmm("15:30")
    start = now.replace(hour=start_hour, minute=start_minute, second=0, microsecond=0)
    end = now.replace(hour=end_hour, minute=end_minute, second=0, microsecond=0)
    if now <= start:
        return 0.01
    if now >= end:
        return 1.0
    return max(0.01, min(1.0, (now - start).total_seconds() / (end - start).total_seconds()))


def normalize_trading_env(value: str) -> str:
    normalized = (value or "").strip().lower()
    if normalized in {"real", "prod", "production", "live"}:
        return "real"
    return "demo"


def normalize_kis_account(account_no: str, account_product_code: str) -> tuple[str, str]:
    digits = "".join(ch for ch in str(account_no) if ch.isdigit())
    product_digits = "".join(ch for ch in str(account_product_code) if ch.isdigit())
    if len(digits) == 10 and not product_digits:
        return digits[:8], digits[8:]
    if len(digits) == 10 and product_digits == "01":
        return digits[:8], digits[8:]
    return digits[:8] if len(digits) >= 8 else digits, (product_digits or "01")[:2]


def mask_account(account_no: str, product_code: str) -> str:
    if not account_no:
        return "미설정"
    visible = account_no[-2:] if len(account_no) >= 2 else account_no
    return f"******{visible}-{product_code or '**'}"


def date_chunks(start_date: str, end_date: str, chunk_days: int) -> List[tuple[str, str]]:
    start = datetime.strptime(start_date, "%Y-%m-%d")
    end = datetime.strptime(end_date, "%Y-%m-%d")
    chunks: List[tuple[str, str]] = []
    current = start
    while current <= end:
        chunk_end = min(current + timedelta(days=max(1, chunk_days)), end)
        chunks.append((current.strftime("%Y-%m-%d"), chunk_end.strftime("%Y-%m-%d")))
        current = chunk_end + timedelta(days=1)
    return chunks


def compact_date(value: str) -> str:
    return value.replace("-", "")


def to_float(value: object) -> Optional[float]:
    try:
        if value is None or pd.isna(value):
            return None
        text = str(value).replace(",", "").strip()
        if not text:
            return None
        return float(text)
    except (TypeError, ValueError):
        return None


def annualized_volatility(close: pd.Series) -> float:
    returns = close.astype(float).pct_change().dropna()
    if returns.empty:
        return 0.0
    return float(returns.tail(120).std() * (252 ** 0.5))


def return_over_period(close: pd.Series, days: int) -> float:
    values = close.dropna().astype(float)
    if len(values) <= days:
        return 0.0
    previous = float(values.iloc[-days - 1])
    current = float(values.iloc[-1])
    if previous <= 0:
        return 0.0
    return (current / previous - 1) * 100


def return_between_periods(close: pd.Series, start_days_ago: int, end_days_ago: int) -> float:
    values = close.dropna().astype(float)
    if start_days_ago <= end_days_ago or len(values) <= start_days_ago:
        return 0.0
    start_value = float(values.iloc[-start_days_ago - 1])
    end_value = float(values.iloc[-end_days_ago - 1])
    if start_value <= 0:
        return 0.0
    return (end_value / start_value - 1) * 100


def max_drawdown(close: pd.Series) -> float:
    values = close.dropna().astype(float)
    if values.empty:
        return 0.0
    running_max = values.cummax()
    drawdown = values / running_max - 1
    return abs(float(drawdown.min() * 100))


def parse_news_datetime(value: str) -> datetime:
    try:
        parsed = parsedate_to_datetime(value)
        if parsed.tzinfo is not None:
            return parsed.astimezone().replace(tzinfo=None)
        return parsed
    except Exception:
        return datetime.now()


def news_cache_key(title: str, link: str) -> str:
    raw = f"{title}|{link}".encode("utf-8", errors="ignore")
    return hashlib.sha256(raw).hexdigest()[:20]


def recent_news_risk_for_plan(plan: OrderPlan) -> str:
    if not env_bool("NEWS_BLOCK_AUTO_TRADE_ON_RISK", NEWS_BLOCK_AUTO_TRADE_ON_RISK):
        return ""
    if not NEWS_ALERT_FILE.exists():
        return ""
    try:
        with NEWS_ALERT_FILE.open("r", encoding="utf-8") as file:
            payload = json.load(file)
        alerts = payload.get("alerts", []) if isinstance(payload, dict) else []
        cutoff = datetime.now() - timedelta(hours=max(0.1, env_float("NEWS_TRADE_BLOCK_LOOKBACK_HOURS", NEWS_TRADE_BLOCK_LOOKBACK_HOURS)))
        min_score = env_float("NEWS_TRADE_BLOCK_MIN_SCORE", NEWS_TRADE_BLOCK_MIN_SCORE)
        for item in reversed(alerts):
            if not isinstance(item, dict):
                continue
            sentiment = str(item.get("sentiment", ""))
            if sentiment not in {"risk", "negative"}:
                continue
            impact_score = to_float(item.get("impact_score")) or 0.0
            if impact_score < min_score:
                continue
            published_at = datetime.fromisoformat(str(item.get("published_at")))
            if published_at < cutoff:
                continue
            title = str(item.get("title", ""))
            related_code = str(item.get("related_code", ""))
            related_name = str(item.get("related_name", ""))
            if related_code == plan.code or plan.name in title or (related_name and related_name == plan.name):
                return f"최근 뉴스 리스크 감지: {title[:120]} (영향 {impact_score:.1f})"
    except Exception as exc:
        logger.warning("뉴스 리스크 주문 차단 확인 실패: %s", exc)
    return ""


def run_scheduled_job(bot: FinancialHealthBot) -> None:
    bot.run_once()


def run_candidate_job(bot: FinancialHealthBot) -> None:
    bot.prepare_realtime_candidates()


def run_realtime_job(bot: FinancialHealthBot) -> None:
    bot.run_realtime_once()


def run_news_job(bot: FinancialHealthBot) -> None:
    bot.run_news_once()


def run_trading_job(bot: FinancialHealthBot) -> None:
    bot.run_trading_once()


def main() -> None:
    try:
        scheduler_stale_minutes = env_float("SCHEDULER_LOCK_STALE_MINUTES", SCHEDULER_LOCK_STALE_MINUTES)
        with BotRunLock(SCHEDULER_LOCK_FILE, "scheduler", stale_minutes=scheduler_stale_minutes):
            bot = FinancialHealthBot()
            logger.info("재무 건전성 중심 종목 발굴 봇 시작")
            logger.info("매일 한국 시간 기준 %s에 분석을 실행합니다.", RUN_TIME_KST)
            logger.info(
                "실시간 감시는 %s 후보 준비 후 %s~%s, %d초 간격으로 실행합니다.",
                bot.realtime_scanner.candidate_run_time,
                bot.realtime_scanner.scan_start,
                bot.realtime_scanner.scan_end,
                bot.realtime_scanner.scan_interval_seconds,
            )
            logger.info("자동매매 대기 주문은 매일 한국 시간 기준 %s에 실행합니다.", bot.trading_engine.run_time)
            logger.info(
                "뉴스 속보 감시는 %s, %d초 간격으로 실행합니다.",
                "활성화" if bot.news_monitor.enabled else "비활성화",
                bot.news_monitor.scan_interval_seconds,
            )

            schedule.every().day.at(RUN_TIME_KST).do(run_scheduled_job, bot)
            schedule.every().day.at(bot.realtime_scanner.candidate_run_time).do(run_candidate_job, bot)
            schedule.every(bot.realtime_scanner.scan_interval_seconds).seconds.do(run_realtime_job, bot)
            schedule.every(bot.news_monitor.scan_interval_seconds).seconds.do(run_news_job, bot)
            schedule.every().day.at(bot.trading_engine.run_time).do(run_trading_job, bot)
            bot.state_store.heartbeat({"status": "scheduler_started"})
            run_scheduled_job(bot)
            run_news_job(bot)

            while True:
                try:
                    schedule.run_pending()
                    bot.state_store.heartbeat(
                        {
                            "status": "scheduler_running",
                            "next_jobs": [str(job) for job in schedule.jobs[:8]],
                        }
                    )
                    time.sleep(30)
                except KeyboardInterrupt:
                    logger.info("사용자 요청으로 봇을 종료합니다.")
                    bot.state_store.heartbeat({"status": "scheduler_stopped"})
                    break
                except Exception as exc:
                    logger.exception("스케줄 루프 오류: %s", exc)
                    bot.state_store.heartbeat({"status": "scheduler_error", "error": str(exc)})
                    time.sleep(60)
    except BotLockError as exc:
        logger.error("봇이 이미 실행 중입니다: %s", exc)
        raise SystemExit(2)


if __name__ == "__main__":
    main()
