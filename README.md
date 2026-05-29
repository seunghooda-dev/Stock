# Financial Health Stock Scanner

KOSPI/KOSDAQ 전종목 중 재무 건전성이 좋고 자산가치 대비 저평가된 종목을 1차로 추린 뒤, 시장 국면, 저변동성, 외국인/기관 수급, 기술적 진입 타점을 함께 통과한 후보만 텔레그램으로 전송하는 스캐너 봇입니다.

## 데이터 소스

- `FinanceDataReader`: KRX 종목 목록, 시가총액, 국내 주가 데이터
- `KIS Open API`: 한국투자증권 국내주식 일봉/현재가 데이터
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

## 한국투자증권 API 설정

KIS Developers에서 API 신청 후 발급받은 `APP_KEY`, `APP_SECRET`을 `.env`에 넣으면 개별 종목 일봉 데이터는 한국투자증권 API를 우선 사용합니다. 키가 없거나 호출이 실패하면 기존 `FinanceDataReader`로 자동 fallback됩니다.

```text
KIS_APP_KEY=한국투자증권 APP KEY
KIS_APP_SECRET=한국투자증권 APP SECRET
KIS_BASE_URL=https://openapi.koreainvestment.com:9443
KIS_TRADING_ENV=real
KIS_ACCOUNT_NO=계좌번호 앞 8자리
KIS_ACCOUNT_PRODUCT_CODE=01
```

모의투자 환경을 쓸 때는 아래처럼 바꾸면 됩니다.

```text
KIS_TRADING_ENV=demo
KIS_BASE_URL=https://openapivts.koreainvestment.com:29443
```

연결 확인:

```powershell
.\.venv\Scripts\python.exe test_kis_connection.py
```

## 민감정보 관리

실제 토큰, 앱키, 앱시크릿, 계좌번호는 `.env`에만 저장하세요. `.env`, `.env.*`, `cache/`, `logs/`, KIS 설정 파일은 Git에 올라가지 않도록 차단되어 있습니다.

`.env.example`에는 예시값만 남기고 실제 값은 절대 넣지 않습니다. 키가 채팅이나 로그에 노출되었다면 KIS Developers 또는 Telegram BotFather에서 재발급하는 것을 권장합니다.

## 자동매매 설계

스캐너는 오후 4시에 종목을 발굴한 뒤, 매수 주문 계획을 `cache/pending_trades.json`에 저장할 수 있습니다. 실제 주문 실행은 다음 거래일 오전 9시 5분 스케줄에서 처리합니다. 기본값은 안전을 위해 자동매매 비활성화와 모의 실행입니다.

```text
AUTO_TRADE_ENABLED=false
AUTO_TRADE_DRY_RUN=true
AUTO_TRADE_RUN_TIME_KST=09:05
AUTO_TRADE_MAX_ORDERS_PER_RUN=2
AUTO_TRADE_ORDER_TYPE=00
AUTO_TRADE_ORDER_BUDGET_KRW=300000
AUTO_TRADE_MAX_ORDER_VALUE_KRW=500000
AUTO_TRADE_MAX_PORTFOLIO_EXPOSURE_KRW=1000000
AUTO_TRADE_PENDING_MAX_AGE_HOURS=20
```

실제 주문을 보내려면 아래 값을 모두 의도적으로 바꿔야 합니다.

```text
AUTO_TRADE_ENABLED=true
AUTO_TRADE_DRY_RUN=false
KIS_TRADING_ENV=real
KIS_BASE_URL=https://openapi.koreainvestment.com:9443
AUTO_TRADE_CONFIRM_REAL_TRADING=YES
```

모의투자 주문을 먼저 검증하려면 `KIS_TRADING_ENV=demo`, 모의투자용 `APP_KEY/APP_SECRET`, 모의투자 계좌번호, 모의투자 도메인을 사용하세요.

`AUTO_TRADE_ORDER_TYPE=00`은 지정가, `01`은 시장가입니다. 기본값은 시가 급등 시 과도한 체결가를 피하기 위해 지정가입니다.

## 실행

```powershell
.\.venv\Scripts\python.exe stock_telegram_bot.py
```

실행 직후 1회 스캔하고, 이후 매일 한국 시간 기준 오후 4시에 자동 실행됩니다.

바탕화면에서 실행하려면 `Stock Bot 실행.bat`을 더블클릭하세요. 종료가 필요하면 `Stock Bot 종료.bat`을 더블클릭하면 실행 중인 봇 프로세스를 정리합니다.

## 즉시 알림

스캔 중 최종 조건을 통과한 종목이 발견되면 전체 스캔이 끝나기 전이라도 텔레그램으로 즉시 알림을 보냅니다.

- 같은 종목은 20시간 동안 중복 알림을 보내지 않습니다.
- 중복 알림 기록은 `cache/alerts.json`에 저장됩니다.
- 스캔 종료 후에는 최종 요약 리포트도 한 번 더 전송됩니다.

## 장중 실시간 알림

장중에는 전종목을 반복 분석하지 않고, 아침에 만든 후보군만 KIS 현재가 API로 감시합니다. 기본 흐름은 `08:40 후보군 준비 -> 09:20~14:50 실시간 감시 -> 16:00 장마감 리포트`입니다.

```text
REALTIME_SCAN_ENABLED=true
REALTIME_CANDIDATE_RUN_TIME_KST=08:40
REALTIME_SCAN_START_KST=09:20
REALTIME_SCAN_END_KST=14:50
REALTIME_SCAN_INTERVAL_SECONDS=180
REALTIME_MAX_WATCHLIST=50
```

국내장 특화 방어 로직도 함께 적용합니다.

- KOSPI 종목은 KOSPI 200일선, KOSDAQ 종목은 KOSDAQ150 추종 지표 200일선으로 Risk-On을 분리합니다.
- 관리종목, 투자주의환기종목, SPAC은 후보군에서 제외합니다.
- 당일 상승률 15% 이상 종목은 신규 진입 알림을 차단합니다.
- VI 의심 등락률 또는 KIS 현재가 응답의 VI 상태 코드가 있으면 알림을 차단합니다.
- 증거금률 100%로 확인되는 종목은 실시간 알림에서 제외합니다.
- 장중 거래량이 시간 경과 대비 20일 평균 거래량보다 충분히 빠르지 않으면 알림을 보내지 않습니다.

## 재무 필터

아래 조건을 모두 만족해야 1차 후보가 됩니다.

- 시가총액 500억 원 이상
- 당일 거래대금 5억 원 이상
- 부채비율 100% 미만
- 유동비율 150% 이상
- 영업이익 3년 연속 흑자
- PBR 1.5 미만

## 시장 국면 필터

코스피 종목은 KOSPI, 코스닥 종목은 KOSDAQ150 추종 지표가 200일 이동평균선 아래에 있으면 Risk-Off로 판단하고 신규 매수 후보 스캔을 중단합니다.

## 기술적 필터

재무 필터를 통과한 종목에만 적용합니다.

- 현재가가 20일 이동평균선 지지권 안에 있음
- 20일 이동평균선이 상승 중
- 20일 이동평균선이 60일 이동평균선 위
- RSI(14)가 40~55 진입 구간
- 최근 120거래일 변동성이 시장 변동성의 110% 이하

## 리스크 관리

- ATR(14)을 계산합니다.
- 손절선은 `현재가 - 2 * ATR`로 표시합니다.
- 유동성이 낮은 종목은 호가 공백과 체결 리스크가 크기 때문에 사전에 제외합니다.
- 자동매매는 1회 주문 수, 종목당 예산, 1회 총 노출 한도, 동일 종목 재진입 쿨다운을 적용합니다.
- 주문 실행 직전에도 시장 국면을 재확인하고, Risk-Off면 대기 주문을 폐기합니다.
- 실전 주문은 `AUTO_TRADE_CONFIRM_REAL_TRADING=YES`가 없으면 코드상에서 차단됩니다.

## 수급 매집 필터

기술적 필터를 통과한 종목에만 적용합니다.

- 최근 20거래일 외국인/기관 합산 순매수
- 합산 순매수량이 상장주식수 대비 0.1% 이상
- 최근 20거래일 중 10일 이상 양수급
- 20거래일 주가 변화율이 ±5% 이내

## 구조

- `FinancialScanner`: 전종목 유니버스 구성, yfinance 재무제표 수집, 재무 필터링
- `KISDataProvider`: 한국투자증권 접근토큰 발급/캐시, 국내주식 기간별시세와 현재가 조회
- `TradingEngine`: 종목 발굴 결과를 주문 계획으로 변환하고 KIS 현금 주문을 실행
- `RealtimeScanner`: 아침 후보군을 장중 KIS 현재가로 감시하고 조건 포착 시 즉시 알림
- `MarketRegimeFilter`: KOSPI/KOSDAQ150 200일 이동평균선 기반 Risk-On/Risk-Off 판단
- `TechnicalAnalyzer`: RSI, 20일/60일 이동평균선, 저변동성 기반 기술적 분석
- `AccumulationAnalyzer`: 네이버 금융 외국인/기관 순매매 기반 수급 매집 분석
- `Notifier`: 텔레그램 리포트 전송
- `FinancialHealthBot`: 전체 실행 흐름과 스케줄 관리

## 참고

전종목 재무제표 조회는 시간이 걸릴 수 있습니다. 재무 데이터는 `cache/fundamentals.json`에 7일간 캐시되어 다음 실행부터 속도가 빨라집니다. 조회 실패 종목도 3일간 캐시해서 매일 같은 실패를 반복하지 않습니다.
