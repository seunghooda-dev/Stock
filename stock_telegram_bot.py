import json
import logging
import os
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional

import FinanceDataReader as fdr
import pandas as pd
import requests
import schedule
import yfinance as yf
from dotenv import load_dotenv
from ta.momentum import RSIIndicator


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

# Financial filters
MAX_DEBT_TO_EQUITY = 100.0
MIN_CURRENT_RATIO = 150.0
MAX_PBR = 1.5
REQUIRED_PROFIT_YEARS = 3

# Technical filters
RSI_WINDOW = 14
MA_SHORT = 20
MA_LONG = 60
MIN_RSI = 50.0
MAX_RSI = 75.0

MARKETS = {"KOSPI", "KOSDAQ"}
EXCLUDE_NAME_KEYWORDS = ["스팩", "ETF", "ETN", "리츠"]
CACHE_DIR = Path("cache")
FUNDAMENTAL_CACHE_FILE = CACHE_DIR / "fundamentals.json"

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
    trend_summary: str


@dataclass
class DiscoveryReport:
    stock: StockMeta
    financials: FinancialMetrics
    technicals: TechnicalSnapshot
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

            if not self._is_common_stock(name):
                continue

            stocks.append(StockMeta(code=code, name=name, market=market, market_cap=market_cap))

        logger.info("재무 스캔 대상 종목 수: %d개", len(stocks))
        return stocks

    def scan(self, stocks: List[StockMeta]) -> List[FinancialMetrics]:
        passed: List[FinancialMetrics] = []

        for index, stock_meta in enumerate(stocks, start=1):
            if index % 100 == 0:
                logger.info("재무 필터 진행률: %d/%d", index, len(stocks))

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


class TechnicalAnalyzer:
    @property
    def start_date(self) -> str:
        return (datetime.now() - timedelta(days=LOOKBACK_DAYS)).strftime("%Y-%m-%d")

    @property
    def end_date(self) -> str:
        return datetime.now().strftime("%Y-%m-%d")

    def analyze(self, stock_meta: StockMeta) -> Optional[TechnicalSnapshot]:
        try:
            data = fdr.DataReader(stock_meta.code, self.start_date, self.end_date)
            if data.empty:
                raise ValueError("가격 데이터가 비어 있습니다.")

            required_columns = {"Close"}
            missing_columns = required_columns - set(data.columns)
            if missing_columns:
                raise ValueError(f"필수 가격 컬럼 누락: {', '.join(sorted(missing_columns))}")

            prices = data[["Close"]].dropna().copy()
            if len(prices) < MIN_HISTORY_DAYS:
                raise ValueError(f"분석에 필요한 가격 데이터 부족: {len(prices)}일")

            prices["MA20"] = prices["Close"].rolling(MA_SHORT).mean()
            prices["MA60"] = prices["Close"].rolling(MA_LONG).mean()
            prices["RSI"] = RSIIndicator(close=prices["Close"], window=RSI_WINDOW).rsi()
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
            ma20_rising = ma20 > float(five_days_ago["MA20"])
            above_ma20 = current_price > ma20
            medium_uptrend = ma20 > ma60
            rsi_healthy = MIN_RSI <= rsi <= MAX_RSI

            if not (above_ma20 and ma20_rising and medium_uptrend and rsi_healthy):
                return None

            crossed_ma20 = float(previous["Close"]) <= float(previous["MA20"]) and current_price > ma20
            if crossed_ma20:
                trend_summary = "20일 이동평균선 상향 돌파 중"
            else:
                trend_summary = "20일선 위에서 60일선 대비 상승 추세 유지"

            return TechnicalSnapshot(
                current_price=current_price,
                rsi=rsi,
                ma20=ma20,
                ma60=ma60,
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

    def send(self, message: str) -> None:
        if not self.token or not self.chat_id:
            logger.warning("TELEGRAM_TOKEN 또는 CHAT_ID가 비어 있어 텔레그램 전송을 건너뜁니다.")
            logger.info("전송 예정 메시지:\n%s", message)
            return

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

        logger.info("텔레그램 메시지 전송 완료")

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
        self.technical_analyzer = TechnicalAnalyzer()
        self.notifier = Notifier(token=token, chat_id=chat_id)

    def run_once(self) -> None:
        logger.info("재무 건전성 종목 발굴 작업 시작")
        try:
            universe = self.financial_scanner.fetch_universe()
            stock_map = {stock.code: stock for stock in universe}
            financially_strong = self.financial_scanner.scan(universe)

            reports: List[DiscoveryReport] = []
            for metrics in financially_strong:
                stock_meta = stock_map.get(metrics.code)
                if stock_meta is None:
                    continue

                technicals = self.technical_analyzer.analyze(stock_meta)
                if technicals is None:
                    continue

                reports.append(
                    DiscoveryReport(
                        stock=stock_meta,
                        financials=metrics,
                        technicals=technicals,
                        reason=self._build_reason(metrics, technicals),
                    )
                )

            reports = self._rank_reports(reports)[:MAX_REPORTS]
            self.notifier.send(self._build_message(reports))
            logger.info("재무 건전성 종목 발굴 작업 완료. 최종 후보: %d개", len(reports))
        except Exception as exc:
            logger.exception("재무 건전성 종목 발굴 작업 실패: %s", exc)
            self.notifier.send(f"⚠️ 재무 건전성 스캐너 오류\n{exc}")

    @staticmethod
    def _rank_reports(reports: List[DiscoveryReport]) -> List[DiscoveryReport]:
        return sorted(
            reports,
            key=lambda report: (
                report.financials.pbr,
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
            f"{margin_text}, {technicals.trend_summary}입니다."
        )

    @staticmethod
    def _build_message(reports: List[DiscoveryReport]) -> str:
        today = datetime.now().strftime("%Y-%m-%d")
        if not reports:
            return (
                f"📊 재무 건전성 알짜 기업 스캐너\n"
                f"🗓 {today}\n\n"
                "오늘은 재무 필터와 기술적 추세 조건을 모두 만족한 종목이 없습니다."
            )

        lines = [
            "📊 재무 건전성 알짜 기업 스캐너",
            f"🗓 {today}",
            f"✅ 최종 발굴 종목 {len(reports)}개",
        ]

        for report in reports:
            financials = report.financials
            technicals = report.technicals
            lines.extend(
                [
                    "",
                    f"💎 [{report.stock.name}({report.stock.code})] 발굴 리포트",
                    f"💰 시가총액: {format_market_cap(financials.market_cap)}",
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


def format_market_cap(value: Optional[float]) -> str:
    if value is None:
        return "N/A"
    return f"{value / 100_000_000:,.0f}억 원"


def format_optional_percent(value: Optional[float]) -> str:
    if value is None:
        return "N/A"
    return f"{value:.1f}%"


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
