# Stock Telegram Bot

국내 주요 종목의 최근 일별 OHLCV와 기본지표를 수집하고 RSI, MACD, 20일 이동평균선 기준으로 매수 후보를 골라 텔레그램으로 전송하는 Python 봇입니다.

## 설치

```powershell
pip install -r requirements.txt
```

## 설정

텔레그램 토큰과 채팅 ID는 코드에 직접 넣지 말고 환경변수로 설정하세요.

```powershell
$env:TELEGRAM_TOKEN = "텔레그램 봇 토큰"
$env:TELEGRAM_CHAT_ID = "텔레그램 채팅 ID"
```

## 실행

```powershell
python stock_telegram_bot.py
```

프로그램은 시작 직후 한 번 분석을 실행하고, 이후 매일 한국 시간 기준 오후 4시에 다시 실행됩니다.

## 추천 기준

- RSI 14일 기준 30 이하
- 현재가가 20일 이동평균선에 3% 이내로 근접했거나 20일 이동평균선을 돌파하려는 경우
- PER/PBR/ROE 기본 필터를 통과한 경우
- MACD 회복 신호가 있으면 추천 이유에 함께 표시

## 대상 종목

- `005930` 삼성전자
- `000660` SK하이닉스
- `035420` NAVER
- `035720` 카카오
- `051910` LG화학
- `005380` 현대차
- `068270` 셀트리온
- `247540` 에코프로비엠

## 데이터 출처

- 일별 OHLCV: `pykrx.stock.get_market_ohlcv_by_date`
- PER/PBR/EPS/BPS/DPS: `pykrx.stock.get_market_fundamental_by_date`
- ROE: `EPS / BPS * 100`으로 계산
