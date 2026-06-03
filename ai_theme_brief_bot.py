import argparse
import json
import logging
import os
import re
import sys
import time
import xml.etree.ElementTree as ET
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta
from email.utils import parsedate_to_datetime
from html import unescape
from pathlib import Path
from typing import Dict, List, Optional
from urllib.parse import quote_plus

import pandas as pd
import requests
import schedule
import yfinance as yf
from dotenv import load_dotenv


TELEGRAM_TOKEN = ""
TELEGRAM_CHAT_ID = ""
AI_THEME_BRIEF_RUN_TIME_KST = "08:00"
AI_THEME_BRIEF_NEWS_LOOKBACK_HOURS = 36
AI_THEME_BRIEF_MAX_NEWS_PER_SYMBOL = 1
AI_THEME_BRIEF_MAX_TOTAL_NEWS = 12
AI_THEME_BRIEF_REQUEST_DELAY_SECONDS = 0.2
AI_THEME_BRIEF_PRICE_PERIOD = "1mo"
AI_THEME_BRIEF_NEWS_SOURCES = "yahoo,google"
AI_THEME_BRIEF_TRANSLATE_NEWS = True
AI_THEME_BRIEF_TRANSLATION_PROVIDER = "mymemory"
AI_THEME_BRIEF_TRANSLATION_TIMEOUT_SECONDS = 8.0
AI_THEME_BRIEF_NEWS_SUMMARY_MAX_CHARS = 220
AI_THEME_BRIEF_CACHE_FILE = Path("cache") / "ai_theme_brief_latest.json"
AI_THEME_BRIEF_LOG_FILE = Path("logs") / "ai_theme_brief.log"


logger = logging.getLogger("ai-theme-brief")


@dataclass(frozen=True)
class ThemeStock:
    symbol: str
    name_ko: str
    name_en: str
    theme: str
    role: str
    news_query: str


@dataclass
class PriceSnapshot:
    symbol: str
    name_ko: str
    theme: str
    role: str
    price: Optional[float] = None
    currency: str = ""
    change_1d_pct: Optional[float] = None
    change_5d_pct: Optional[float] = None
    change_20d_pct: Optional[float] = None
    volume: Optional[float] = None
    status: str = "ok"
    error: str = ""


@dataclass
class NewsItem:
    symbol: str
    name_ko: str
    theme: str
    title: str
    source: str
    published_at: str
    link: str
    sentiment: str
    impact_score: float
    matched_terms: List[str] = field(default_factory=list)
    provider: str = ""
    original_title: str = ""
    original_description: str = ""
    summary_ko: str = ""


AI_THEME_STOCKS: List[ThemeStock] = [
    ThemeStock("NVDA", "엔비디아", "NVIDIA", "AI 생태계 앵커", "GPU/네트워킹/로보틱스 플랫폼 기준점", "NVIDIA AI data center Blackwell robotics"),
    ThemeStock("MRVL", "마벨 테크놀로지", "Marvell Technology", "인프라 & 네트워킹", "광통신, 네트워킹 칩, 맞춤형 ASIC", "Marvell AI data center custom silicon optical networking"),
    ThemeStock("CRWV", "코어위브", "CoreWeave", "인프라 & 네트워킹", "AI GPU 특화 클라우드", "CoreWeave AI cloud GPU Nvidia"),
    ThemeStock("NOW", "서비스나우", "ServiceNow", "엔터프라이즈 AI", "기업 워크플로우 AI 에이전트/NIM 파트너", "ServiceNow Nvidia NIM AI agents enterprise workflow"),
    ThemeStock("CRM", "세일즈포스", "Salesforce", "엔터프라이즈 AI", "CRM AI 에이전트", "Salesforce AI agent enterprise software"),
    ThemeStock("SAP", "SAP", "SAP", "엔터프라이즈 AI", "ERP AI 에이전트", "SAP AI agent enterprise ERP Nvidia"),
    ThemeStock("PLTR", "팔란티어", "Palantir", "엔터프라이즈 AI", "정부/국방/대기업 AI 분석 플랫폼", "Palantir AI platform government defense enterprise"),
    ThemeStock("MSFT", "마이크로소프트", "Microsoft", "로컬 AI PC", "Windows Copilot+ PC/RTX AI 생태계", "Microsoft Windows Copilot PC Nvidia RTX AI"),
    ThemeStock("2454.TW", "미디어텍", "MediaTek", "로컬 AI PC", "AI PC/차량용 인포테인먼트 칩 협력", "MediaTek Nvidia AI PC automotive chip"),
    ThemeStock("005380.KS", "현대차", "Hyundai Motor", "물리적 AI/로보틱스", "Boston Dynamics 모회사 노출", "Hyundai Boston Dynamics robotics Nvidia Isaac"),
    ThemeStock("SIE.DE", "지멘스", "Siemens", "물리적 AI/로보틱스", "디지털 트윈/공장 시뮬레이션", "Siemens Nvidia digital twin industrial AI"),
    ThemeStock("2317.TW", "폭스콘", "Hon Hai/Foxconn", "AI 서버 ODM", "AI 서버/랙 제조", "Foxconn Nvidia Blackwell AI server rack"),
    ThemeStock("2382.TW", "콴타", "Quanta Computer", "AI 서버 ODM", "AI 서버 제조", "Quanta Nvidia AI server Blackwell"),
    ThemeStock("3231.TW", "위스트론", "Wistron", "AI 서버 ODM", "AI 서버 제조", "Wistron Nvidia AI server"),
    ThemeStock("2356.TW", "인벤텍", "Inventec", "AI 서버 ODM", "AI 서버 제조", "Inventec Nvidia AI server"),
    ThemeStock("4938.TW", "페가트론", "Pegatron", "AI 서버 ODM", "AI 서버/전자 제조", "Pegatron Nvidia AI server"),
    ThemeStock("SMCI", "슈퍼마이크로", "Super Micro Computer", "서버/하드웨어", "AI 서버 시스템", "Super Micro Nvidia Blackwell AI server"),
    ThemeStock("2357.TW", "에이수스", "ASUS", "서버/하드웨어", "서버/메인보드/AI PC", "ASUS Nvidia AI server RTX AI PC"),
    ThemeStock("2376.TW", "기가바이트", "Gigabyte", "서버/하드웨어", "서버/메인보드", "Gigabyte Nvidia AI server motherboard"),
]


PRIVATE_OR_INDIRECT = [
    "Figure AI: 비상장, 직접 매수 가능한 상장 티커 없음",
    "Agility Robotics: 비상장, 직접 매수 가능한 상장 티커 없음",
    "Boston Dynamics: 비상장, 현대차(005380.KS)를 간접 노출로 추적",
]


STOCK_NEWS_ALIASES: Dict[str, List[str]] = {
    "NVDA": ["nvidia", "nvda"],
    "MRVL": ["marvell", "marvell technology", "mrvl"],
    "CRWV": ["coreweave", "crwv"],
    "NOW": ["servicenow", "service now"],
    "CRM": ["salesforce", "crm"],
    "SAP": ["sap"],
    "PLTR": ["palantir", "pltr"],
    "MSFT": ["microsoft", "msft", "windows", "copilot"],
    "2454.TW": ["mediatek", "media tek"],
    "005380.KS": ["hyundai", "hyundai motor", "boston dynamics"],
    "SIE.DE": ["siemens"],
    "2317.TW": ["foxconn", "hon hai"],
    "2382.TW": ["quanta", "quanta computer"],
    "3231.TW": ["wistron"],
    "2356.TW": ["inventec"],
    "4938.TW": ["pegatron"],
    "SMCI": ["supermicro", "super micro", "smci"],
    "2357.TW": ["asus", "asustek"],
    "2376.TW": ["gigabyte", "gigabyte technology"],
}


POSITIVE_TERMS = [
    "수주",
    "공급",
    "계약",
    "협력",
    "파트너십",
    "투자",
    "실적",
    "매출",
    "가이던스 상향",
    "AI server",
    "Blackwell",
    "data center",
    "GPU",
    "AI agent",
    "robotics",
    "digital twin",
]

RISK_TERMS = [
    "급락",
    "하락",
    "downgrade",
    "lawsuit",
    "소송",
    "규제",
    "조사",
    "제재",
    "delay",
    "지연",
    "margin",
    "debt",
    "capex",
    "적자",
    "실적 부진",
]


def main() -> None:
    configure_logging()
    configure_console_encoding()
    load_dotenv()
    args = parse_args()
    bot = AIThemeBriefBot(dry_run=args.dry_run)
    if args.once:
        bot.run_once()
        return

    logger.info("AI 테마 브리프 봇 시작. 매일 %s KST 전송", bot.run_time)
    schedule.every().day.at(bot.run_time).do(bot.run_once)
    if args.run_on_start:
        bot.run_once()
    while True:
        try:
            schedule.run_pending()
            time.sleep(30)
        except KeyboardInterrupt:
            logger.info("사용자 요청으로 종료")
            break
        except Exception as exc:
            logger.exception("스케줄 루프 오류: %s", exc)
            time.sleep(60)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Daily Telegram brief for NVIDIA AI ecosystem stocks")
    parser.add_argument("--once", action="store_true", help="한 번만 실행합니다.")
    parser.add_argument("--dry-run", action="store_true", help="텔레그램 전송 없이 콘솔에만 출력합니다.")
    parser.add_argument("--run-on-start", action="store_true", help="스케줄 대기 전 즉시 1회 실행합니다.")
    return parser.parse_args()


def configure_logging() -> None:
    Path("logs").mkdir(exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


def configure_console_encoding() -> None:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass


class AIThemeBriefBot:
    GOOGLE_NEWS_URL = "https://news.google.com/rss/search?q={query}&hl=ko&gl=KR&ceid=KR:ko"
    YAHOO_FINANCE_RSS_URL = "https://feeds.finance.yahoo.com/rss/2.0/headline?s={symbol}&region=US&lang=en-US"

    def __init__(self, dry_run: bool = False) -> None:
        self.dry_run = dry_run
        self.run_time = os.getenv("AI_THEME_BRIEF_RUN_TIME_KST", AI_THEME_BRIEF_RUN_TIME_KST)
        self.news_lookback_hours = env_int("AI_THEME_BRIEF_NEWS_LOOKBACK_HOURS", AI_THEME_BRIEF_NEWS_LOOKBACK_HOURS)
        self.max_news_per_symbol = env_int("AI_THEME_BRIEF_MAX_NEWS_PER_SYMBOL", AI_THEME_BRIEF_MAX_NEWS_PER_SYMBOL)
        self.max_total_news = env_int("AI_THEME_BRIEF_MAX_TOTAL_NEWS", AI_THEME_BRIEF_MAX_TOTAL_NEWS)
        self.request_delay = env_float("AI_THEME_BRIEF_REQUEST_DELAY_SECONDS", AI_THEME_BRIEF_REQUEST_DELAY_SECONDS)
        self.price_period = os.getenv("AI_THEME_BRIEF_PRICE_PERIOD", AI_THEME_BRIEF_PRICE_PERIOD)
        self.news_sources = env_list("AI_THEME_BRIEF_NEWS_SOURCES", AI_THEME_BRIEF_NEWS_SOURCES)
        self.translate_news = env_bool("AI_THEME_BRIEF_TRANSLATE_NEWS", AI_THEME_BRIEF_TRANSLATE_NEWS)
        self.translation_provider = os.getenv(
            "AI_THEME_BRIEF_TRANSLATION_PROVIDER",
            AI_THEME_BRIEF_TRANSLATION_PROVIDER,
        ).strip().lower()
        self.translation_timeout = env_float(
            "AI_THEME_BRIEF_TRANSLATION_TIMEOUT_SECONDS",
            AI_THEME_BRIEF_TRANSLATION_TIMEOUT_SECONDS,
        )
        self.news_summary_max_chars = env_int(
            "AI_THEME_BRIEF_NEWS_SUMMARY_MAX_CHARS",
            AI_THEME_BRIEF_NEWS_SUMMARY_MAX_CHARS,
        )
        self.telegram = TelegramClient(
            token=TELEGRAM_TOKEN or os.getenv("TELEGRAM_TOKEN", ""),
            chat_id=TELEGRAM_CHAT_ID or os.getenv("TELEGRAM_CHAT_ID", ""),
        )

    def run_once(self) -> None:
        logger.info("AI 테마 브리프 생성 시작")
        prices = [self.fetch_price(stock) for stock in AI_THEME_STOCKS]
        news: List[NewsItem] = []
        for stock in AI_THEME_STOCKS:
            news.extend(self.fetch_news(stock)[: self.max_news_per_symbol])
            time.sleep(self.request_delay)
            if len(news) >= self.max_total_news:
                break
        news = sorted(news, key=lambda item: (item.impact_score, item.published_at), reverse=True)[: self.max_total_news]
        payload = {
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "run_time": self.run_time,
            "prices": [asdict(item) for item in prices],
            "news": [asdict(item) for item in news],
            "private_or_indirect": PRIVATE_OR_INDIRECT,
        }
        write_json(AI_THEME_BRIEF_CACHE_FILE, payload)
        message = self.build_message(prices, news)
        if self.dry_run:
            print(message)
        else:
            self.telegram.send(message)
        logger.info("AI 테마 브리프 생성 완료. 가격 %d개, 뉴스 %d개", len(prices), len(news))

    def fetch_price(self, stock: ThemeStock) -> PriceSnapshot:
        snapshot = PriceSnapshot(symbol=stock.symbol, name_ko=stock.name_ko, theme=stock.theme, role=stock.role)
        try:
            ticker = yf.Ticker(stock.symbol)
            frame = ticker.history(period=self.price_period, auto_adjust=False)
            if frame is None or frame.empty or "Close" not in frame.columns:
                snapshot.status = "missing_price"
                snapshot.error = "가격 데이터 없음"
                return snapshot
            close = frame["Close"].dropna().astype(float)
            if close.empty:
                snapshot.status = "missing_price"
                snapshot.error = "종가 데이터 없음"
                return snapshot
            snapshot.price = round(float(close.iloc[-1]), 2)
            snapshot.currency = infer_currency(stock.symbol)
            snapshot.change_1d_pct = pct_change(close, 1)
            snapshot.change_5d_pct = pct_change(close, 5)
            snapshot.change_20d_pct = pct_change(close, 20)
            if "Volume" in frame.columns and not frame["Volume"].dropna().empty:
                snapshot.volume = float(frame["Volume"].dropna().iloc[-1])
        except Exception as exc:
            snapshot.status = "error"
            snapshot.error = str(exc)[:160]
            logger.warning("%s(%s) 가격 조회 실패: %s", stock.name_ko, stock.symbol, exc)
        return snapshot

    def fetch_news(self, stock: ThemeStock) -> List[NewsItem]:
        items: List[NewsItem] = []
        if "yahoo" in self.news_sources:
            items.extend(self.fetch_yahoo_news(stock))
            time.sleep(self.request_delay)
        if "google" in self.news_sources:
            items.extend(self.fetch_google_news(stock))
        deduped = dedupe_news_items(items)
        return sorted(deduped, key=lambda item: (item.impact_score, item.published_at), reverse=True)

    def fetch_yahoo_news(self, stock: ThemeStock) -> List[NewsItem]:
        url = self.YAHOO_FINANCE_RSS_URL.format(symbol=quote_plus(stock.symbol))
        cutoff = datetime.now() - timedelta(hours=max(1, self.news_lookback_hours))
        candidates: List[dict] = []
        try:
            response = requests.get(url, timeout=12, headers={"User-Agent": "Mozilla/5.0"})
            response.raise_for_status()
            root = ET.fromstring(response.content)
            for item in root.findall(".//item"):
                title = normalize_news_title(item.findtext("title") or "")
                description = clean_html_text(item.findtext("description") or "")
                link = (item.findtext("link") or "").strip()
                published_at = parse_news_datetime(item.findtext("pubDate") or "")
                if published_at < cutoff or not title:
                    continue
                if not is_relevant_news(stock, title, description):
                    continue
                source = (item.findtext("source") or "Yahoo Finance").strip()
                _, impact_score, _ = score_news_title(f"{title} {description}")
                candidates.append(
                    {
                        "title": title,
                        "description": description,
                        "source": source,
                        "published_at": published_at,
                        "link": link,
                        "provider": "Yahoo Finance",
                        "impact_score": impact_score,
                    }
                )
        except Exception as exc:
            logger.debug("%s(%s) Yahoo Finance 뉴스 조회 실패: %s", stock.name_ko, stock.symbol, exc)
        return self.build_top_news_items(stock, candidates)

    def fetch_google_news(self, stock: ThemeStock) -> List[NewsItem]:
        query = f"{stock.news_query} stock OR shares"
        url = self.GOOGLE_NEWS_URL.format(query=quote_plus(query))
        cutoff = datetime.now() - timedelta(hours=max(1, self.news_lookback_hours))
        candidates: List[dict] = []
        try:
            response = requests.get(url, timeout=12, headers={"User-Agent": "Mozilla/5.0"})
            response.raise_for_status()
            root = ET.fromstring(response.content)
            for item in root.findall(".//item"):
                source = (item.findtext("source") or "Google News").strip()
                title = normalize_news_title(item.findtext("title") or "", source)
                description = clean_html_text(item.findtext("description") or "")
                link = (item.findtext("link") or "").strip()
                published_at = parse_news_datetime(item.findtext("pubDate") or "")
                if published_at < cutoff or not title:
                    continue
                if not is_relevant_news(stock, title, description):
                    continue
                _, impact_score, _ = score_news_title(f"{title} {description}")
                candidates.append(
                    {
                        "title": title,
                        "description": description,
                        "source": source,
                        "published_at": published_at,
                        "link": link,
                        "provider": "Google News",
                        "impact_score": impact_score,
                    }
                )
        except Exception as exc:
            logger.debug("%s(%s) Google News 뉴스 조회 실패: %s", stock.name_ko, stock.symbol, exc)
        return self.build_top_news_items(stock, candidates)

    def build_top_news_items(self, stock: ThemeStock, candidates: List[dict]) -> List[NewsItem]:
        limit = max(1, self.max_news_per_symbol)
        ranked = sorted(candidates, key=lambda item: (item["impact_score"], item["published_at"]), reverse=True)
        return [
            self.build_news_item(
                stock=stock,
                title=str(candidate["title"]),
                description=str(candidate["description"]),
                source=str(candidate["source"]),
                published_at=candidate["published_at"],
                link=str(candidate["link"]),
                provider=str(candidate["provider"]),
            )
            for candidate in ranked[:limit]
        ]

    def build_news_item(
        self,
        stock: ThemeStock,
        title: str,
        description: str,
        source: str,
        published_at: datetime,
        link: str,
        provider: str,
    ) -> NewsItem:
        scoring_text = f"{title} {description}"
        sentiment, impact_score, matched_terms = score_news_title(scoring_text)
        summary = summarize_news_to_korean(
            stock=stock,
            title=title,
            description=description,
            sentiment=sentiment,
            matched_terms=matched_terms,
            translate_enabled=self.translate_news,
            provider=self.translation_provider,
            timeout=self.translation_timeout,
            max_chars=self.news_summary_max_chars,
        )
        return NewsItem(
            symbol=stock.symbol,
            name_ko=stock.name_ko,
            theme=stock.theme,
            title=summary,
            source=source or provider,
            published_at=published_at.isoformat(timespec="seconds"),
            link=link,
            sentiment=sentiment,
            impact_score=impact_score,
            matched_terms=matched_terms,
            provider=provider,
            original_title=title,
            original_description=description,
            summary_ko=summary,
        )

    def build_message(self, prices: List[PriceSnapshot], news: List[NewsItem]) -> str:
        generated = datetime.now().strftime("%Y-%m-%d %H:%M")
        lines = [
            "🧠 AI 밸류체인 주식 브리프",
            f"🗓 {generated} KST",
            "범위: 사용자가 지정한 NVIDIA AI 인프라/소프트웨어/디바이스/로보틱스/서버 관련 상장주",
            "",
            "📌 가격 변화 상위",
        ]
        movable = [item for item in prices if item.change_1d_pct is not None]
        movers = sorted(movable, key=lambda item: abs(item.change_1d_pct or 0), reverse=True)[:8]
        if not movers:
            lines.append("- 가격 데이터 없음")
        for item in movers:
            lines.append(
                f"- {item.name_ko}({item.symbol}) {format_price(item.price, item.currency)} "
                f"1D {format_pct(item.change_1d_pct)}, 5D {format_pct(item.change_5d_pct)}, "
                f"20D {format_pct(item.change_20d_pct)} / {item.theme}"
            )

        lines.extend(["", "🧩 테마별 관찰"])
        for theme, items in group_by_theme(prices).items():
            compact = ", ".join(
                f"{item.name_ko} {format_pct(item.change_1d_pct)}"
                for item in items
                if item.status == "ok"
            )
            if compact:
                lines.append(f"- {theme}: {compact}")

        lines.extend(["", "📰 관련 뉴스"])
        if not news:
            lines.append("- 최근 감지 뉴스 없음")
        for item in news[: self.max_total_news]:
            terms = ", ".join(item.matched_terms[:3]) or "키워드 없음"
            summary = item.summary_ko or item.title
            lines.append(
                f"- [{item.name_ko}({item.symbol})/{item.sentiment.upper()}/{item.provider or item.source}] "
                f"{summary} ({item.source}, {item.published_at}, {terms})"
            )

        lines.extend(["", "🚫 직접 상장 티커 없음"])
        lines.extend(f"- {item}" for item in PRIVATE_OR_INDIRECT)
        lines.extend(["", "※ 자동 요약입니다. 매수/매도 추천이 아니라 지정 테마 관찰 리포트입니다."])
        return "\n".join(lines)


class TelegramClient:
    def __init__(self, token: str, chat_id: str) -> None:
        self.token = token
        self.chat_id = chat_id

    def send(self, message: str) -> bool:
        if not self.token or not self.chat_id:
            logger.warning("텔레그램 토큰/채팅 ID가 없어 전송 생략")
            print(message)
            return False
        ok = True
        for chunk in split_message(message, 3900):
            response = requests.post(
                f"https://api.telegram.org/bot{self.token}/sendMessage",
                data={"chat_id": self.chat_id, "text": chunk, "disable_web_page_preview": True},
                timeout=20,
            )
            if not response.ok:
                ok = False
                logger.error("텔레그램 전송 실패: HTTP %s %s", response.status_code, response.text[:200])
        if ok:
            logger.info("텔레그램 전송 완료")
        return ok


def group_by_theme(prices: List[PriceSnapshot]) -> Dict[str, List[PriceSnapshot]]:
    grouped: Dict[str, List[PriceSnapshot]] = {}
    for item in prices:
        grouped.setdefault(item.theme, []).append(item)
    return grouped


def pct_change(close: pd.Series, periods: int) -> Optional[float]:
    if len(close) <= periods:
        return None
    previous = float(close.iloc[-periods - 1])
    current = float(close.iloc[-1])
    if previous <= 0:
        return None
    return round((current / previous - 1) * 100, 2)


def format_pct(value: Optional[float]) -> str:
    if value is None:
        return "N/A"
    return f"{value:+.2f}%"


def format_price(value: Optional[float], currency: str) -> str:
    if value is None:
        return "N/A"
    return f"{value:,.2f}{currency}"


def infer_currency(symbol: str) -> str:
    if symbol.endswith(".TW"):
        return " TWD"
    if symbol.endswith(".KS"):
        return " KRW"
    if symbol.endswith(".DE"):
        return " EUR"
    return " USD"


def score_news_title(title: str) -> tuple[str, float, List[str]]:
    lower = title.lower()
    positive = [term for term in POSITIVE_TERMS if term.lower() in lower]
    risk = [term for term in RISK_TERMS if term.lower() in lower]
    score = len(positive) * 2.0 + len(risk) * 2.5
    if risk and len(risk) >= len(positive):
        sentiment = "risk"
    elif positive:
        sentiment = "positive"
    else:
        sentiment = "watch"
        score = 1.0
    return sentiment, round(score, 1), risk + positive


def summarize_news_to_korean(
    stock: ThemeStock,
    title: str,
    description: str,
    sentiment: str,
    matched_terms: List[str],
    translate_enabled: bool,
    provider: str,
    timeout: float,
    max_chars: int,
) -> str:
    source_text = title
    if len(source_text) < 70 and description:
        source_text = f"{source_text} - {compact_text(description, 160)}"
    source_text = compact_text(source_text, 360)
    translated = translate_text_to_korean(
        source_text,
        enabled=translate_enabled,
        provider=provider,
        timeout=timeout,
    )
    if not translated:
        translated = fallback_news_summary(title, sentiment, matched_terms)
    sentiment_label = {"positive": "긍정", "risk": "리스크", "watch": "관찰"}.get(sentiment, "관찰")
    terms = ", ".join(matched_terms[:3])
    suffix = f" / 핵심 키워드: {terms}" if terms else ""
    return compact_text(f"{stock.name_ko} 관련 {sentiment_label} 뉴스: {translated}{suffix}", max_chars)


def translate_text_to_korean(text: str, enabled: bool, provider: str, timeout: float) -> str:
    text = compact_text(clean_html_text(text), 440)
    if not text:
        return ""
    if contains_korean(text):
        return text
    if not enabled:
        return ""
    if provider == "mymemory":
        translated = translate_with_mymemory(text, timeout)
        if translated:
            return translated
    return ""


def translate_with_mymemory(text: str, timeout: float) -> str:
    text = compact_text(text, 440)
    try:
        response = requests.get(
            "https://api.mymemory.translated.net/get",
            params={"q": text, "langpair": "en|ko"},
            timeout=max(2.0, timeout),
            headers={"User-Agent": "Mozilla/5.0"},
        )
        response.raise_for_status()
        payload = response.json()
        translated = clean_html_text(str(payload.get("responseData", {}).get("translatedText", "")))
        lowered = translated.lower()
        invalid_markers = ("query length limit exceeded", "invalid", "too many requests", "translation failed")
        if translated and translated.lower() != text.lower() and not any(marker in lowered for marker in invalid_markers):
            return translated
    except Exception as exc:
        logger.debug("뉴스 번역 실패: %s", exc)
    return ""


def fallback_news_summary(text: str, sentiment: str, matched_terms: List[str]) -> str:
    clean = compact_text(clean_html_text(text), 180)
    replacements = {
        "earnings": "실적",
        "revenue": "매출",
        "guidance": "가이던스",
        "outlook": "전망",
        "analyst": "애널리스트",
        "upgrade": "투자의견 상향",
        "downgrade": "투자의견 하향",
        "partnership": "파트너십",
        "contract": "계약",
        "order": "수주",
        "data center": "데이터센터",
        "ai server": "AI 서버",
        "blackwell": "Blackwell",
        "gpu": "GPU",
        "robotics": "로보틱스",
        "lawsuit": "소송",
        "regulation": "규제",
        "delay": "지연",
        "margin": "마진",
    }
    lowered = clean.lower()
    detected = [ko for en, ko in replacements.items() if en in lowered]
    detected.extend(matched_terms[:3])
    detected = list(dict.fromkeys(detected))
    label = {"positive": "호재 가능성", "risk": "리스크 가능성", "watch": "관찰 필요"}.get(sentiment, "관찰 필요")
    keyword_text = f" 감지 키워드: {', '.join(detected[:5])}." if detected else ""
    return f"{label}.{keyword_text} 원문 핵심: {clean}"


def normalize_news_title(value: str, source: str = "") -> str:
    title = clean_html_text(value)
    if source:
        for separator in (" - ", " | "):
            suffix = f"{separator}{source}"
            if title.endswith(suffix):
                title = title[: -len(suffix)].strip()
    return title


def clean_html_text(value: str) -> str:
    text = unescape(value or "")
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def contains_korean(value: str) -> bool:
    return bool(re.search(r"[가-힣]", value or ""))


def compact_text(value: str, max_chars: int) -> str:
    text = re.sub(r"\s+", " ", (value or "")).strip()
    if max_chars <= 0 or len(text) <= max_chars:
        return text
    return text[: max(0, max_chars - 3)].rstrip() + "..."


def dedupe_news_items(items: List[NewsItem]) -> List[NewsItem]:
    deduped: Dict[str, NewsItem] = {}
    for item in items:
        key_source = item.original_title or item.title or item.link
        key = re.sub(r"[^a-z0-9가-힣]+", "", key_source.lower())
        if not key:
            key = item.link
        existing = deduped.get(key)
        if existing is None or item.impact_score > existing.impact_score:
            deduped[key] = item
    return list(deduped.values())


def is_relevant_news(stock: ThemeStock, title: str, description: str) -> bool:
    text = f"{title} {description}".lower()
    aliases = STOCK_NEWS_ALIASES.get(stock.symbol, [])
    for alias in aliases:
        alias = alias.lower().strip()
        if not alias:
            continue
        pattern = rf"(?<![a-z0-9]){re.escape(alias)}(?![a-z0-9])"
        if re.search(pattern, text):
            return True
    return False


def parse_news_datetime(value: str) -> datetime:
    try:
        parsed = parsedate_to_datetime(value)
        if parsed.tzinfo is not None:
            return parsed.astimezone().replace(tzinfo=None)
        return parsed
    except Exception:
        return datetime.now()


def split_message(message: str, max_length: int) -> List[str]:
    if len(message) <= max_length:
        return [message]
    chunks: List[str] = []
    current = ""
    for line in message.splitlines():
        candidate = f"{current}\n{line}" if current else line
        if len(candidate) > max_length:
            if current:
                chunks.append(current)
            current = line
        else:
            current = candidate
    if current:
        chunks.append(current)
    return chunks


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(exist_ok=True)
    temp_path = path.with_name(path.name + ".tmp")
    with temp_path.open("w", encoding="utf-8") as file:
        json.dump(payload, file, ensure_ascii=False, indent=2)
    temp_path.replace(path)


def env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        return default


def env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except ValueError:
        return default


def env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


def env_list(name: str, default: str) -> List[str]:
    value = os.getenv(name, default)
    return [item.strip().lower() for item in value.split(",") if item.strip()]


if __name__ == "__main__":
    main()
