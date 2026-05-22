import logging
import time
from datetime import datetime, timedelta
from html import escape
from typing import Dict, List, Optional

import pandas as pd
import requests
import schedule
from pykrx import stock
from ta.trend import MACD
from ta.momentum import RSIIndicator


# Telegram settings: put your own values here.
TELEGRAM_TOKEN = ""
CHAT_ID = ""

# Bot settings
RUN_TIME_KST = "16:00"
LOOKBACK_DAYS = 220
RSI_WINDOW = 14
MA_WINDOW = 20
RSI_BUY_THRESHOLD = 30
MA_PROXIMITY_RATE = 0.03
FUNDAMENTAL_FILTER_ENABLED = True
MAX_PER = 40
MAX_PBR = 5

STOCKS: Dict[str, str] = {
    "005930": "삼성전자",
    "000660": "SK하이닉스",
    "035420": "NAVER",
    "035720": "카카오",
    "051910": "LG화학",
    "005380": "현대차",
    "068270": "셀트리온",
    "247540": "에코프로비엠",
}

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)


def send_telegram_message(message: str) -> bool:
    """Send a message to Telegram. Returns False instead of raising."""
    if not TELEGRAM_TOKEN or not CHAT_ID:
        logging.warning("TELEGRAM_TOKEN 또는 CHAT_ID가 비어 있어 텔레그램 전송을 건너뜁니다.")
        logging.info("전송 예정 메시지:\n%s", message)
        return False

    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {
        "chat_id": CHAT_ID,
        "text": message,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }

    try:
        response = requests.post(url, data=payload, timeout=15)
        response.raise_for_status()
        logging.info("텔레그램 메시지 전송 완료")
        return True
    except requests.RequestException as exc:
        logging.exception("텔레그램 메시지 전송 실패: %s", exc)
        return False


def get_date_range() -> tuple[str, str]:
    end_date = datetime.now()
    start_date = end_date - timedelta(days=LOOKBACK_DAYS)
    return start_date.strftime("%Y%m%d"), end_date.strftime("%Y%m%d")


def normalize_ohlcv_columns(data: pd.DataFrame) -> pd.DataFrame:
    column_map = {
        "시가": "Open",
        "고가": "High",
        "저가": "Low",
        "종가": "Close",
        "거래량": "Volume",
    }
    data = data.rename(columns=column_map)
    required_columns = ["Open", "High", "Low", "Close", "Volume"]
    missing_columns = set(required_columns) - set(data.columns)
    if missing_columns:
        raise ValueError(f"필수 OHLCV 컬럼 누락: {', '.join(sorted(missing_columns))}")
    return data[required_columns].sort_index()


def fetch_stock_data(ticker: str) -> Optional[pd.DataFrame]:
    """Fetch recent KRX daily OHLCV data through pykrx."""
    try:
        start_date, end_date = get_date_range()
        data = stock.get_market_ohlcv_by_date(start_date, end_date, ticker)

        if data.empty:
            raise ValueError(f"{ticker} OHLCV 데이터가 비어 있습니다.")

        data = normalize_ohlcv_columns(data)
        data = data.dropna(subset=["Open", "High", "Low", "Close", "Volume"]).copy()
        if len(data) < MA_WINDOW + RSI_WINDOW:
            raise ValueError(f"{ticker} 분석에 필요한 데이터가 부족합니다. 현재 {len(data)}일")

        return data
    except Exception as exc:
        logging.exception("%s 데이터 수집 실패: %s", ticker, exc)
        send_telegram_message(f"⚠️ <b>{ticker} 데이터 수집 오류</b>\n{exc}")
        return None


def fetch_fundamental_data(ticker: str) -> Dict[str, Optional[float]]:
    """Fetch latest PER/PBR/EPS/BPS/DPS data through pykrx."""
    try:
        start_date, end_date = get_date_range()
        data = stock.get_market_fundamental_by_date(start_date, end_date, ticker)

        if data.empty:
            raise ValueError(f"{ticker} 기본적 분석 데이터가 비어 있습니다.")

        latest = data.dropna(how="all").iloc[-1]

        bps = to_optional_float(latest.get("BPS"))
        eps = to_optional_float(latest.get("EPS"))
        roe = None
        if bps and eps is not None:
            roe = eps / bps * 100

        return {
            "per": to_optional_float(latest.get("PER")),
            "pbr": to_optional_float(latest.get("PBR")),
            "eps": eps,
            "bps": bps,
            "dps": to_optional_float(latest.get("DPS")),
            "roe": roe,
        }
    except Exception as exc:
        logging.exception("%s 기본적 분석 데이터 수집 실패: %s", ticker, exc)
        return {
            "per": None,
            "pbr": None,
            "eps": None,
            "bps": None,
            "dps": None,
            "roe": None,
        }


def to_optional_float(value: object) -> Optional[float]:
    try:
        if pd.isna(value):
            return None
        number = float(value)
        return number if number != 0 else None
    except (TypeError, ValueError):
        return None


def passes_fundamental_filter(fundamental: Dict[str, Optional[float]]) -> bool:
    if not FUNDAMENTAL_FILTER_ENABLED:
        return True

    per = fundamental.get("per")
    pbr = fundamental.get("pbr")
    roe = fundamental.get("roe")

    if per is None or per <= 0 or per > MAX_PER:
        return False
    if pbr is None or pbr <= 0 or pbr > MAX_PBR:
        return False
    if roe is not None and roe <= 0:
        return False

    return True


def analyze_stock(ticker: str, name: str, data: pd.DataFrame) -> Optional[Dict[str, object]]:
    """Analyze one stock and return a buy candidate dict when conditions match."""
    try:
        close = data["Close"].astype(float)
        data["RSI"] = RSIIndicator(close=close, window=RSI_WINDOW).rsi()
        data["MA20"] = close.rolling(window=MA_WINDOW).mean()
        macd = MACD(close=close)
        data["MACD"] = macd.macd()
        data["MACD_SIGNAL"] = macd.macd_signal()

        latest = data.dropna(subset=["RSI", "MA20", "MACD", "MACD_SIGNAL"]).iloc[-1]
        previous = data.dropna(subset=["RSI", "MA20", "MACD", "MACD_SIGNAL"]).iloc[-2]

        current_price = float(latest["Close"])
        previous_price = float(previous["Close"])
        rsi = float(latest["RSI"])
        ma20 = float(latest["MA20"])
        previous_ma20 = float(previous["MA20"])
        volume = int(latest["Volume"])
        macd_value = float(latest["MACD"])
        macd_signal = float(latest["MACD_SIGNAL"])

        near_ma20 = abs(current_price - ma20) / ma20 <= MA_PROXIMITY_RATE
        breaking_ma20 = previous_price < previous_ma20 and current_price >= ma20
        oversold = rsi <= RSI_BUY_THRESHOLD

        if not (oversold and (near_ma20 or breaking_ma20)):
            return None

        fundamental = fetch_fundamental_data(ticker)
        if not passes_fundamental_filter(fundamental):
            return None

        reason_parts: List[str] = [f"RSI {rsi:.1f}로 과매도 구간 진입"]
        if breaking_ma20:
            reason_parts.append("20일 이동평균선 돌파 시도")
        elif current_price >= ma20:
            reason_parts.append("20일 이동평균선 지지 확인")
        else:
            reason_parts.append("20일 이동평균선 근접")
        if macd_value >= macd_signal:
            reason_parts.append("MACD 회복 신호")

        return {
            "ticker": ticker,
            "name": name,
            "current_price": current_price,
            "volume": volume,
            "rsi": rsi,
            "ma20": ma20,
            "macd": macd_value,
            "macd_signal": macd_signal,
            "fundamental": fundamental,
            "reason": " 및 ".join(reason_parts),
        }
    except Exception as exc:
        logging.exception("%s 분석 실패: %s", ticker, exc)
        send_telegram_message(f"⚠️ <b>{name}({ticker}) 분석 오류</b>\n{exc}")
        return None


def format_metric(value: Optional[float], suffix: str = "", digits: int = 2) -> str:
    if value is None:
        return "N/A"
    return f"{value:,.{digits}f}{suffix}"


def build_recommendation_message(recommendations: List[Dict[str, object]]) -> str:
    today = datetime.now().strftime("%Y-%m-%d")

    if not recommendations:
        return (
            f"📊 <b>국내 주요 종목 매수 추천 리포트</b>\n"
            f"🗓 {today}\n\n"
            "오늘은 조건에 부합하는 추천 종목이 없습니다."
        )

    lines = [
        "📊 <b>국내 주요 종목 매수 추천 리포트</b>",
        f"🗓 {today}",
        "",
        "✅ <b>매수 추천 후보</b>",
    ]

    for item in recommendations:
        fundamental = item["fundamental"]
        lines.extend(
            [
                "",
                f"🚀 <b>{escape(str(item['name']))} ({item['ticker']})</b>",
                f"💰 현재가: {item['current_price']:,.0f} KRW",
                f"📦 거래량: {item['volume']:,}주",
                f"📉 RSI: {item['rsi']:.1f}",
                f"📈 20일 MA: {item['ma20']:,.0f} KRW",
                f"📊 MACD: {item['macd']:.2f} / Signal {item['macd_signal']:.2f}",
                (
                    "🏢 기본지표: "
                    f"PER {format_metric(fundamental.get('per'), digits=2)}, "
                    f"PBR {format_metric(fundamental.get('pbr'), digits=2)}, "
                    f"ROE {format_metric(fundamental.get('roe'), '%', digits=2)}"
                ),
                f"🧠 추천 이유: {escape(str(item['reason']))}",
            ]
        )

    lines.extend(
        [
            "",
            "※ 이 메시지는 기술적 지표 기반 자동 분석이며 투자 수익을 보장하지 않습니다.",
        ]
    )
    return "\n".join(lines)


def run_analysis() -> None:
    logging.info("주식 분석 작업 시작")
    recommendations: List[Dict[str, object]] = []

    try:
        for ticker, name in STOCKS.items():
            logging.info("%s(%s) 데이터 수집 및 분석 중", name, ticker)
            data = fetch_stock_data(ticker)
            if data is None:
                continue

            recommendation = analyze_stock(ticker, name, data)
            if recommendation:
                recommendations.append(recommendation)

        message = build_recommendation_message(recommendations)
        send_telegram_message(message)
        logging.info("주식 분석 작업 완료. 추천 종목 수: %d", len(recommendations))
    except Exception as exc:
        logging.exception("전체 분석 작업 실패: %s", exc)
        send_telegram_message(f"⚠️ <b>주식 추천 봇 오류</b>\n{exc}")


def main() -> None:
    logging.info("주식 추천 텔레그램 봇 시작")
    logging.info("매일 한국 시간 기준 %s에 분석을 실행합니다.", RUN_TIME_KST)

    schedule.every().day.at(RUN_TIME_KST).do(run_analysis)

    # Start once immediately so you can verify Telegram and data collection quickly.
    run_analysis()

    while True:
        try:
            schedule.run_pending()
            time.sleep(30)
        except KeyboardInterrupt:
            logging.info("사용자 요청으로 봇을 종료합니다.")
            break
        except Exception as exc:
            logging.exception("스케줄 루프 오류: %s", exc)
            send_telegram_message(f"⚠️ <b>스케줄 루프 오류</b>\n{exc}")
            time.sleep(60)


if __name__ == "__main__":
    main()
