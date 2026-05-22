# Financial Health Stock Scanner

KOSPI/KOSDAQ 전종목 중 재무 건전성이 좋고 자산가치 대비 저평가된 종목을 1차로 추린 뒤, 시장 국면, 저변동성, 외국인/기관 수급, 기술적 진입 타점을 함께 통과한 후보만 텔레그램으로 전송하는 스캐너 봇입니다.

## 데이터 소스

- `FinanceDataReader`: KRX 종목 목록, 시가총액, 국내 주가 데이터
- `yfinance`: 재무제표, 대차대조표, 손익계산서
- `Naver Finance`: 최근 외국인/기관 순매매 데이터

## 설치

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

## 텔레그램 설정

`stock_telegram_bot.py` 상단의 값을 직접 입력하거나 `.env` 파일을 사용하세요.

```python
TELEGRAM_TOKEN = "텔레그램 봇 토큰"
CHAT_ID = "텔레그램 채팅 ID"
```

`.env` 방식:

```powershell
Copy-Item .env.example .env
notepad .env
```

```text
TELEGRAM_TOKEN=텔레그램 봇 토큰
TELEGRAM_CHAT_ID=텔레그램 채팅 ID
```

## 실행

```powershell
.\.venv\Scripts\python.exe stock_telegram_bot.py
```

실행 직후 1회 스캔하고, 이후 매일 한국 시간 기준 오후 4시에 자동 실행됩니다.

## 재무 필터

아래 조건을 모두 만족해야 1차 후보가 됩니다.

- 부채비율 100% 미만
- 유동비율 150% 이상
- 영업이익 3년 연속 흑자
- PBR 1.5 미만

## 시장 국면 필터

코스피 지수가 200일 이동평균선 아래에 있으면 Risk-Off로 판단하고 신규 매수 후보 스캔을 중단합니다.

## 기술적 필터

재무 필터를 통과한 종목에만 적용합니다.

- 현재가가 20일 이동평균선 지지권 안에 있음
- 20일 이동평균선이 상승 중
- 20일 이동평균선이 60일 이동평균선 위
- RSI(14)가 40~55 진입 구간
- 최근 120거래일 변동성이 시장 변동성의 110% 이하

## 수급 매집 필터

기술적 필터를 통과한 종목에만 적용합니다.

- 최근 20거래일 외국인/기관 합산 순매수
- 합산 순매수량이 상장주식수 대비 0.1% 이상
- 최근 20거래일 중 10일 이상 양수급
- 20거래일 주가 변화율이 ±5% 이내

## 구조

- `FinancialScanner`: 전종목 유니버스 구성, yfinance 재무제표 수집, 재무 필터링
- `MarketRegimeFilter`: 코스피 200일 이동평균선 기반 Risk-On/Risk-Off 판단
- `TechnicalAnalyzer`: RSI, 20일/60일 이동평균선, 저변동성 기반 기술적 분석
- `AccumulationAnalyzer`: 네이버 금융 외국인/기관 순매매 기반 수급 매집 분석
- `Notifier`: 텔레그램 리포트 전송
- `FinancialHealthBot`: 전체 실행 흐름과 스케줄 관리

## 참고

전종목 재무제표 조회는 시간이 걸릴 수 있습니다. 재무 데이터는 `cache/fundamentals.json`에 7일간 캐시되어 다음 실행부터 속도가 빨라집니다.
