import logging
import time
from datetime import datetime
from typing import Dict, List, Optional

import pandas as pd
import requests
import schedule
import yfinance as yf
from ta.momentum import RSIIndicator


# Telegram settings: put your own values here.
TELEGRAM_TOKEN = ""
CHAT_ID = ""

# Bot settings
RUN_TIME_KST = "16:00"
DATA_PERIOD = "6mo"
DATA_INTERVAL = "1d"
RSI_WINDOW = 14
MA_WINDOW = 20
RSI_BUY_THRESHOLD = 30
MA_PROXIMITY_RATE = 0.03

STOCKS: Dict[str, str] = {
    "8035.T": "도쿄일렉트론",
    "6857.T": "어드반테스트",
    "7203.T": "토요타",
    "6758.T": "소니",
    "9984.T": "소프트뱅크",
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


def fetch_stock_data(ticker: str) -> Optional[pd.DataFrame]:
    """Fetch recent daily price data from Yahoo Finance."""
    try:
        data = yf.download(
            tickers=ticker,
            period=DATA_PERIOD,
            interval=DATA_INTERVAL,
            progress=False,
            auto_adjust=False,
            threads=False,
        )

        if data.empty:
            raise ValueError(f"{ticker} 데이터가 비어 있습니다.")

        if isinstance(data.columns, pd.MultiIndex):
            data.columns = data.columns.get_level_values(0)

        required_columns = {"Close"}
        missing_columns = required_columns - set(data.columns)
        if missing_columns:
            raise ValueError(f"{ticker} 필수 컬럼 누락: {', '.join(sorted(missing_columns))}")

        data = data.dropna(subset=["Close"]).copy()
        if len(data) < MA_WINDOW + RSI_WINDOW:
            raise ValueError(f"{ticker} 분석에 필요한 데이터가 부족합니다. 현재 {len(data)}일")

        return data
    except Exception as exc:
        logging.exception("%s 데이터 수집 실패: %s", ticker, exc)
        send_telegram_message(f"⚠️ <b>{ticker} 데이터 수집 오류</b>\n{exc}")
        return None


def analyze_stock(ticker: str, name: str, data: pd.DataFrame) -> Optional[Dict[str, object]]:
    """Analyze one stock and return a buy candidate dict when conditions match."""
    try:
        close = data["Close"].astype(float)
        data["RSI"] = RSIIndicator(close=close, window=RSI_WINDOW).rsi()
        data["MA20"] = close.rolling(window=MA_WINDOW).mean()

        latest = data.dropna(subset=["RSI", "MA20"]).iloc[-1]
        previous = data.dropna(subset=["RSI", "MA20"]).iloc[-2]

        current_price = float(latest["Close"])
        previous_price = float(previous["Close"])
        rsi = float(latest["RSI"])
        ma20 = float(latest["MA20"])
        previous_ma20 = float(previous["MA20"])

        near_ma20 = abs(current_price - ma20) / ma20 <= MA_PROXIMITY_RATE
        breaking_ma20 = previous_price < previous_ma20 and current_price >= ma20
        oversold = rsi <= RSI_BUY_THRESHOLD

        if not (oversold and (near_ma20 or breaking_ma20)):
            return None

        reason_parts: List[str] = [f"RSI {rsi:.1f}로 과매도 구간 진입"]
        if breaking_ma20:
            reason_parts.append("20일 이동평균선 돌파 시도")
        elif current_price >= ma20:
            reason_parts.append("20일 이동평균선 지지 확인")
        else:
            reason_parts.append("20일 이동평균선 근접")

        return {
            "ticker": ticker,
            "name": name,
            "current_price": current_price,
            "rsi": rsi,
            "ma20": ma20,
            "reason": " 및 ".join(reason_parts),
        }
    except Exception as exc:
        logging.exception("%s 분석 실패: %s", ticker, exc)
        send_telegram_message(f"⚠️ <b>{name}({ticker}) 분석 오류</b>\n{exc}")
        return None


def build_recommendation_message(recommendations: List[Dict[str, object]]) -> str:
    today = datetime.now().strftime("%Y-%m-%d")

    if not recommendations:
        return (
            f"📊 <b>일본 주요 종목 매수 추천 리포트</b>\n"
            f"🗓 {today}\n\n"
            "오늘은 조건에 부합하는 추천 종목이 없습니다."
        )

    lines = [
        "📊 <b>일본 주요 종목 매수 추천 리포트</b>",
        f"🗓 {today}",
        "",
        "✅ <b>매수 추천 후보</b>",
    ]

    for item in recommendations:
        lines.extend(
            [
                "",
                f"🚀 <b>{item['name']} ({item['ticker']})</b>",
                f"💴 현재가: {item['current_price']:,.0f} JPY",
                f"📉 RSI: {item['rsi']:.1f}",
                f"📈 20일 MA: {item['ma20']:,.0f} JPY",
                f"🧠 추천 이유: {item['reason']}",
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
