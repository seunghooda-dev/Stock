import json
import logging
import os
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from io import StringIO
from pathlib import Path
from typing import Dict, List, Optional

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

# Scanner settings
RUN_TIME_KST = "16:00"
LOOKBACK_DAYS = 220
MIN_HISTORY_DAYS = 80
MAX_REPORTS = 20
REQUEST_DELAY_SECONDS = 0.15
FUNDAMENTAL_CACHE_DAYS = 7
FAILURE_CACHE_DAYS = 3
IMMEDIATE_ALERTS_ENABLED = True
IMMEDIATE_ALERT_COOLDOWN_HOURS = 20

# Liquidity guardrails
MIN_MARKET_CAP = 50_000_000_000
MIN_DAILY_TRADING_VALUE = 500_000_000

# Market regime filter
MARKET_INDEX_CODE = "KS11"
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

# Financial filters
MAX_DEBT_TO_EQUITY = 100.0
MIN_CURRENT_RATIO = 150.0
MAX_PBR = 1.5
REQUIRED_PROFIT_YEARS = 3

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

MARKETS = {"KOSPI", "KOSDAQ"}
EXCLUDE_NAME_KEYWORDS = ["스팩", "ETF", "ETN", "리츠"]
CACHE_DIR = Path("cache")
FUNDAMENTAL_CACHE_FILE = CACHE_DIR / "fundamentals.json"
ALERT_CACHE_FILE = CACHE_DIR / "alerts.json"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("financial-health-scanner")


@dataclass
class StockMeta:
    code: str
    name: str
    market: str
    market_cap: Optional[float]
    shares: Optional[float]
    trading_value: Optional[float]


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


@dataclass
class MarketRegime:
    index_code: str
    current: float
    ma200: float
    volatility: float
    risk_on: bool
    summary: str


@dataclass
class DiscoveryReport:
    stock: StockMeta
    financials: FinancialMetrics
    technicals: TechnicalSnapshot
    accumulation: Optional[AccumulationSnapshot]
    reason: str


class FinancialScanner:
    def __init__(self) -> None:
        self.cache: Dict[str, Dict[str, object]] = self._load_cache()

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
            market_cap = self._safe_float(getattr(row, "Marcap", None))
            shares = self._safe_float(getattr(row, "Stocks", None))
            trading_value = self._safe_float(getattr(row, "Amount", None))

            if not self._is_common_stock(name):
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
                )
            )

        logger.info("재무 스캔 대상 종목 수: %d개", len(stocks))
        return stocks

    def scan(self, stocks: List[StockMeta]) -> List[FinancialMetrics]:
        passed: List[FinancialMetrics] = []

        for index, stock_meta in enumerate(stocks, start=1):
            if index % 100 == 0:
                logger.info("재무 필터 진행률: %d/%d", index, len(stocks))
                self._save_cache()

            metrics = self.fetch_financial_metrics(stock_meta)
            if metrics is None:
                continue

            if self._passes_financial_filters(metrics):
                passed.append(metrics)

            time.sleep(REQUEST_DELAY_SECONDS)

        logger.info("재무 필터 통과 종목 수: %d개", len(passed))
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

            pbr = market_cap / equity
            operating_income_years = self._get_recent_operating_income(financials, REQUIRED_PROFIT_YEARS)
            revenue = self._get_latest_financial_value(financials, ["Total Revenue", "Operating Revenue"])
            operating_margin = None
            if revenue and revenue > 0:
                operating_margin = operating_income_years[0] / revenue * 100

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
            )
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
        return True

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
                if len(values) >= count:
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
    def _safe_float(value: object) -> Optional[float]:
        try:
            if value is None or pd.isna(value):
                return None
            return float(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _is_common_stock(name: str) -> bool:
        if any(keyword in name for keyword in EXCLUDE_NAME_KEYWORDS):
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

    def analyze(self) -> MarketRegime:
        logger.info("Market Regime Filter: KOSPI 200일선 확인 시작")
        data = fdr.DataReader(MARKET_INDEX_CODE, self.start_date, self.end_date)
        if data.empty or "Close" not in data.columns:
            raise RuntimeError("코스피 지수 데이터를 수집하지 못했습니다.")

        close = data["Close"].dropna().astype(float)
        if len(close) < MARKET_REGIME_MA:
            raise RuntimeError("코스피 200일 이동평균 계산에 필요한 데이터가 부족합니다.")

        current = float(close.iloc[-1])
        ma200 = float(close.rolling(MARKET_REGIME_MA).mean().iloc[-1])
        volatility = annualized_volatility(close)
        risk_on = current >= ma200
        summary = (
            f"KOSPI {current:,.2f}, 200일선 {ma200:,.2f}, "
            f"시장 변동성 {volatility * 100:.1f}%"
        )
        logger.info("%s, Risk-On=%s", summary, risk_on)
        return MarketRegime(
            index_code=MARKET_INDEX_CODE,
            current=current,
            ma200=ma200,
            volatility=volatility,
            risk_on=risk_on,
            summary=summary,
        )


class AccumulationAnalyzer:
    NAVER_URL = "https://finance.naver.com/item/frgn.naver"
    USER_AGENT = "Mozilla/5.0"

    def analyze(self, stock_meta: StockMeta) -> Optional[AccumulationSnapshot]:
        if not stock_meta.shares or stock_meta.shares <= 0:
            logger.warning("%s(%s) 상장주식수 데이터가 없어 수급 분석 제외", stock_meta.name, stock_meta.code)
            return None

        try:
            investor_data = self._fetch_investor_data(stock_meta.code)
            if len(investor_data) < ACCUMULATION_LOOKBACK_DAYS:
                raise ValueError(f"20일 수급 분석에 필요한 데이터 부족: {len(investor_data)}일")

            recent = investor_data.head(ACCUMULATION_LOOKBACK_DAYS).copy()
            combined = recent["foreign_net_buy"] + recent["institutional_net_buy"]
            combined_net_buy = float(combined.sum())
            foreign_net_buy = float(recent["foreign_net_buy"].sum())
            institutional_net_buy = float(recent["institutional_net_buy"].sum())
            positive_days = int((combined > 0).sum())
            net_buy_ratio = combined_net_buy / stock_meta.shares

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
            if abs(price_change) > MAX_SIDEWAYS_PRICE_CHANGE:
                return None

            summary = (
                f"최근 {ACCUMULATION_LOOKBACK_DAYS}일 외국인/기관 합산 순매수 "
                f"{combined_net_buy:,.0f}주, 상장주식수 대비 {net_buy_ratio * 100:.2f}%, "
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
    @property
    def start_date(self) -> str:
        return (datetime.now() - timedelta(days=LOOKBACK_DAYS)).strftime("%Y-%m-%d")

    @property
    def end_date(self) -> str:
        return datetime.now().strftime("%Y-%m-%d")

    def analyze(self, stock_meta: StockMeta, market_regime: MarketRegime) -> Optional[TechnicalSnapshot]:
        try:
            data = fdr.DataReader(stock_meta.code, self.start_date, self.end_date)
            if data.empty:
                raise ValueError("가격 데이터가 비어 있습니다.")

            required_columns = {"High", "Low", "Close"}
            missing_columns = required_columns - set(data.columns)
            if missing_columns:
                raise ValueError(f"필수 가격 컬럼 누락: {', '.join(sorted(missing_columns))}")

            prices = data[["High", "Low", "Close"]].dropna().copy()
            if len(prices) < MIN_HISTORY_DAYS:
                raise ValueError(f"분석에 필요한 가격 데이터 부족: {len(prices)}일")

            prices["MA20"] = prices["Close"].rolling(MA_SHORT).mean()
            prices["MA60"] = prices["Close"].rolling(MA_LONG).mean()
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

            latest = prices.iloc[-1]
            previous = prices.iloc[-2]
            five_days_ago = prices.iloc[-6]

            current_price = float(latest["Close"])
            ma20 = float(latest["MA20"])
            ma60 = float(latest["MA60"])
            rsi = float(latest["RSI"])
            atr = float(latest["ATR"])
            stop_loss = max(0.0, current_price - (ATR_STOP_MULTIPLIER * atr))
            volatility = annualized_volatility(prices["Close"])
            ma20_rising = ma20 > float(five_days_ago["MA20"])
            ma20_support = ma20 * (1 - MA_SUPPORT_BAND) <= current_price <= ma20 * (1 + MAX_DISTANCE_ABOVE_MA20)
            medium_uptrend = ma20 > ma60
            rsi_entry_zone = MIN_RSI <= rsi <= MAX_RSI
            low_volatility = volatility <= market_regime.volatility * MAX_RELATIVE_VOLATILITY

            if not (ma20_support and ma20_rising and medium_uptrend and rsi_entry_zone and low_volatility):
                return None

            crossed_ma20 = float(previous["Close"]) <= float(previous["MA20"]) and current_price > ma20
            if crossed_ma20:
                trend_summary = "RSI 진입권에서 20일 이동평균선 상향 돌파 중"
            else:
                trend_summary = "RSI 40~55 구간에서 20일선 지지 확인"

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
            )
        except Exception as exc:
            logger.warning("%s(%s) 기술적 분석 실패: %s", stock_meta.name, stock_meta.code, exc)
            return None


class Notifier:
    MAX_MESSAGE_LENGTH = 3900

    def __init__(self, token: str, chat_id: str) -> None:
        self.token = token
        self.chat_id = chat_id

    def send(self, message: str) -> bool:
        if not self.token or not self.chat_id:
            logger.warning("TELEGRAM_TOKEN 또는 CHAT_ID가 비어 있어 텔레그램 전송을 건너뜁니다.")
            logger.info("전송 예정 메시지:\n%s", message)
            return False

        try:
            for chunk in self._split_message(message):
                response = requests.post(
                    f"https://api.telegram.org/bot{self.token}/sendMessage",
                    data={
                        "chat_id": self.chat_id,
                        "text": chunk,
                        "disable_web_page_preview": True,
                    },
                    timeout=20,
                )
                response.raise_for_status()
        except requests.RequestException as exc:
            logger.exception("텔레그램 메시지 전송 실패: %s", exc)
            return False

        logger.info("텔레그램 메시지 전송 완료")
        return True

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


class FinancialHealthBot:
    def __init__(self) -> None:
        load_dotenv()
        token = TELEGRAM_TOKEN or os.getenv("TELEGRAM_TOKEN", "")
        chat_id = CHAT_ID or os.getenv("TELEGRAM_CHAT_ID", "")
        self.financial_scanner = FinancialScanner()
        self.market_regime_filter = MarketRegimeFilter()
        self.technical_analyzer = TechnicalAnalyzer()
        self.accumulation_analyzer = AccumulationAnalyzer()
        self.notifier = Notifier(token=token, chat_id=chat_id)
        self.alert_cache: Dict[str, str] = self._load_alert_cache()

    def run_once(self) -> None:
        logger.info("재무 건전성 종목 발굴 작업 시작")
        try:
            market_regime = self.market_regime_filter.analyze()
            if not market_regime.risk_on:
                logger.info("Risk-Off 국면이므로 매수 후보 스캔을 중단합니다.")
                self.notifier.send(self._build_risk_off_message(market_regime))
                return

            universe = self.financial_scanner.fetch_universe()
            stock_map = {stock.code: stock for stock in universe}
            financially_strong = self.financial_scanner.scan(universe)

            reports: List[DiscoveryReport] = []
            for metrics in financially_strong:
                stock_meta = stock_map.get(metrics.code)
                if stock_meta is None:
                    continue

                technicals = self.technical_analyzer.analyze(stock_meta, market_regime)
                if technicals is None:
                    continue

                accumulation = self.accumulation_analyzer.analyze(stock_meta)
                if ENABLE_SMART_MONEY_FILTER and accumulation is None:
                    continue

                reports.append(
                    DiscoveryReport(
                        stock=stock_meta,
                        financials=metrics,
                        technicals=technicals,
                        accumulation=accumulation,
                        reason=self._build_reason(metrics, technicals),
                    )
                )
                latest_report = reports[-1]
                if IMMEDIATE_ALERTS_ENABLED:
                    self._send_immediate_alert_if_needed(latest_report, market_regime)

            reports = self._rank_reports(reports)[:MAX_REPORTS]
            self.notifier.send(self._build_message(reports, market_regime))
            self._save_alert_cache()
            logger.info("재무 건전성 종목 발굴 작업 완료. 최종 후보: %d개", len(reports))
        except Exception as exc:
            logger.exception("재무 건전성 종목 발굴 작업 실패: %s", exc)
            self.notifier.send(f"⚠️ 재무 건전성 스캐너 오류\n{exc}")

    def _send_immediate_alert_if_needed(self, report: DiscoveryReport, market_regime: MarketRegime) -> None:
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
            f"💰 시가총액: {format_market_cap(financials.market_cap)}\n"
            f"💧 당일 거래대금: {format_market_cap(report.stock.trading_value)}\n"
            f"📊 재무: 부채비율 {financials.debt_to_equity:.1f}%, "
            f"유동비율 {financials.current_ratio:.1f}%, PBR {financials.pbr:.2f}\n"
            f"📈 타점: {technicals.trend_summary} "
            f"(현재가 {technicals.current_price:,.0f}원, RSI {technicals.rsi:.1f})\n"
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
                report.financials.pbr,
                -((report.accumulation.net_buy_ratio if report.accumulation else 0.0)),
                report.technicals.volatility,
                report.financials.debt_to_equity,
                -report.technicals.rsi,
            ),
        )

    @staticmethod
    def _build_reason(metrics: FinancialMetrics, technicals: TechnicalSnapshot) -> str:
        margin_text = "영업이익률 확인 가능"
        if metrics.operating_margin is not None:
            margin_text = f"영업이익률 {metrics.operating_margin:.1f}%"
        return (
            f"부채비율 {metrics.debt_to_equity:.1f}%와 유동비율 {metrics.current_ratio:.1f}%로 재무 안정성이 높고, "
            f"PBR {metrics.pbr:.2f}로 자산가치 대비 저평가 구간입니다. "
            f"{margin_text}, 시장보다 낮은 변동성과 {technicals.trend_summary}입니다."
        )

    @staticmethod
    def _build_message(reports: List[DiscoveryReport], market_regime: MarketRegime) -> str:
        today = datetime.now().strftime("%Y-%m-%d")
        if not reports:
            return (
                f"📊 재무 건전성 알짜 기업 스캐너\n"
                f"🗓 {today}\n\n"
                f"🛡️ 시장 국면: {market_regime.summary} / Risk-On\n\n"
                "오늘은 재무, 저변동성, 수급, 기술적 타점 조건을 모두 만족한 종목이 없습니다."
            )

        lines = [
            "📊 재무 건전성 알짜 기업 스캐너",
            f"🗓 {today}",
            f"🛡️ 시장 국면: {market_regime.summary} / Risk-On",
            f"✅ 최종 발굴 종목 {len(reports)}개",
        ]

        for report in reports:
            financials = report.financials
            technicals = report.technicals
            accumulation = report.accumulation
            lines.extend(
                [
                    "",
                    f"💎 [{report.stock.name}({report.stock.code})] 발굴 리포트",
                    f"💰 시가총액: {format_market_cap(financials.market_cap)}",
                    f"💧 당일 거래대금: {format_market_cap(report.stock.trading_value)}",
                    (
                        "📊 재무 핵심 지표: "
                        f"부채비율 {financials.debt_to_equity:.1f}%, "
                        f"유동비율 {financials.current_ratio:.1f}%, "
                        f"PBR {financials.pbr:.2f}, "
                        f"영업이익률 {format_optional_percent(financials.operating_margin)}"
                    ),
                    (
                        "📈 기술적 상황: "
                        f"{technicals.trend_summary} "
                        f"(현재가 {technicals.current_price:,.0f}원, "
                        f"RSI {technicals.rsi:.1f}, "
                        f"20일선 {technicals.ma20:,.0f}원)"
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


def format_market_cap(value: Optional[float]) -> str:
    if value is None:
        return "N/A"
    return f"{value / 100_000_000:,.0f}억 원"


def format_optional_percent(value: Optional[float]) -> str:
    if value is None:
        return "N/A"
    return f"{value:.1f}%"


def format_accumulation(value: Optional[AccumulationSnapshot]) -> str:
    if value is None:
        return "N/A"
    return (
        f"{value.days}일 외국인/기관 합산 {value.combined_net_buy:,.0f}주 순매수, "
        f"상장주식수 대비 {value.net_buy_ratio * 100:.2f}%, "
        f"주가 변화 {value.price_change * 100:+.1f}%"
    )


def annualized_volatility(close: pd.Series) -> float:
    returns = close.astype(float).pct_change().dropna()
    if returns.empty:
        return 0.0
    return float(returns.tail(120).std() * (252 ** 0.5))


def run_scheduled_job(bot: FinancialHealthBot) -> None:
    bot.run_once()


def main() -> None:
    bot = FinancialHealthBot()
    logger.info("재무 건전성 중심 종목 발굴 봇 시작")
    logger.info("매일 한국 시간 기준 %s에 분석을 실행합니다.", RUN_TIME_KST)

    schedule.every().day.at(RUN_TIME_KST).do(run_scheduled_job, bot)
    run_scheduled_job(bot)

    while True:
        try:
            schedule.run_pending()
            time.sleep(30)
        except KeyboardInterrupt:
            logger.info("사용자 요청으로 봇을 종료합니다.")
            break
        except Exception as exc:
            logger.exception("스케줄 루프 오류: %s", exc)
            time.sleep(60)


if __name__ == "__main__":
    main()
