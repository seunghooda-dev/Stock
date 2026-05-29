# Financial Health Stock Scanner

KOSPI/KOSDAQ 전종목 중 재무 건전성이 좋고 자산가치 대비 저평가된 종목을 1차로 추린 뒤, 시장 국면, 저변동성, 외국인/기관 수급, 기술적 진입 타점을 함께 통과한 후보만 텔레그램으로 전송하는 스캐너 봇입니다.

## 데이터 소스

- `FinanceDataReader`: KRX 종목 목록, 시가총액, 국내 주가 데이터
- `KIS Open API`: 한국투자증권 국내주식 일봉/현재가 데이터
- `pykrx`: KRX 기준 PER/PBR/EPS/BPS 보강 및 ROE 추정
- `yfinance`: 재무제표, 대차대조표, 손익계산서
- `Naver Finance`: 최근 외국인/기관 순매매 데이터

## 설치

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

새 Windows PC에서 처음 세팅할 때는 저장소를 받은 뒤 아래 파일을 더블클릭하세요.

```text
setup_windows_pc.bat
```

이 파일은 `.venv` 생성, 의존성 설치, `.env.example` 복사, 바탕화면 실행/종료 배치파일 생성을 한 번에 처리합니다. 실제 토큰과 계좌 정보는 생성된 `.env`에 직접 입력해야 합니다.

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
KIS_MAX_RETRIES=2
KIS_RETRY_DELAY_SECONDS=1.0
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
AUTO_TRADE_USE_RISK_SIZING=true
AUTO_TRADE_RISK_PER_TRADE_KRW=50000
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

`ENABLE_PYKRX_FUNDAMENTALS=true`이면 KRX 기준 PER/PBR/EPS/BPS를 먼저 보강하고, pykrx 또는 KRX 응답이 불안정하면 자동으로 yfinance 재무제표 계산값만 사용합니다.

데이터 신뢰도 검증은 기본적으로 켜져 있습니다. `STRICT_DATA_VALIDATION=true`이면 가격, 재무, 수급의 통합 데이터 신뢰도가 `MIN_DATA_QUALITY_SCORE` 미만인 종목은 추천/주문 후보에서 제외합니다. `ENABLE_PRICE_CROSSCHECK=true`이면 KIS 일봉과 FDR 일봉의 공통 거래일 종가를 비교해 차이가 `MAX_CROSS_SOURCE_CLOSE_DIFF_PCT`를 넘는지 확인합니다. 두 소스의 종가가 같더라도 최신 거래일이 다르면 경고를 남기고, FDR이 더 최신이면 최신 가격 기준을 우선 사용합니다.

KIS 조회 API에서 일시적인 429/5xx 오류가 나면 `KIS_MAX_RETRIES`와 `KIS_RETRY_DELAY_SECONDS` 설정에 따라 재시도합니다. 실제 주문 전송 API는 중복 주문 방지를 위해 자동 재시도하지 않습니다.

## 실행

```powershell
.\.venv\Scripts\python.exe stock_telegram_bot.py
```

실행 직후 1회 스캔하고, 이후 매일 한국 시간 기준 오후 4시에 자동 실행됩니다.

바탕화면에서 실행하려면 `StockBot_Run.bat`을 더블클릭하세요. 종료가 필요하면 `StockBot_Stop.bat`을 더블클릭하면 실행 중인 봇 프로세스를 정리합니다.

다른 PC를 상시 운영용으로 쓸 때는 아래 순서로 진행하세요.

```powershell
git clone https://github.com/seunghooda-dev/Stock.git
cd Stock
.\setup_windows_pc.bat
notepad .env
.\.venv\Scripts\python.exe test_kis_connection.py
```

다른 PC에는 Git과 Python 3.11 이상이 먼저 설치되어 있어야 합니다. PC 로그인 시 자동 실행되게 하려면 `install_startup_task.bat`을 더블클릭하세요. 자동 실행을 제거하려면 `uninstall_startup_task.bat`을 사용합니다. 자동 실행 로그는 `logs/bot.log`에 저장되며, `logs/`는 Git에 올라가지 않습니다.

상시 운영용 PC는 전원이 켜져 있고 Windows 사용자가 로그인되어 있어야 알림/감시가 계속 동작합니다. 절전 모드에 들어가면 봇도 멈추므로, 운영 PC의 전원 설정에서 절전 모드를 꺼두는 것을 권장합니다.

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
- pykrx PER/PBR/EPS/BPS로 yfinance 재무제표를 보강
- ROE, 영업이익률, 매출 YoY, 영업이익 YoY로 가치함정 여부 점검

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
- `AUTO_TRADE_USE_RISK_SIZING=true`일 때는 고정 매수금액만 보지 않고, `매수가 - ATR 손절가` 기준으로 종목당 예상 손실이 `AUTO_TRADE_RISK_PER_TRADE_KRW`를 넘지 않게 수량을 줄입니다.

## 수급 매집 필터

기술적 필터를 통과한 종목에만 적용합니다.

- 최근 20거래일 외국인/기관 합산 순매수
- 합산 순매수량이 상장주식수 대비 0.1% 이상
- 합산 순매수금액이 시가총액 대비 0.05% 이상
- 최근 20거래일 중 10일 이상 양수급
- 20거래일 주가 변화율이 ±5% 이내

## 팩터 점수화

최종 후보는 단순 조건 통과가 아니라 100점 만점 점수로 다시 정렬합니다. 기본 통과선은 `MIN_FACTOR_SCORE=60`입니다.

- 재무 30점: PBR, 부채비율, 유동비율, ROE, 영업이익률, 매출 성장
- 수급 25점: 상장주식수 대비 순매수, 시총 대비 순매수금액, 양수급 일수, 횡보 여부
- 기술 25점: RSI 위치, 20/60일선 스프레드, 20일선 근접도, 거래량, 상향 돌파
- 리스크 20점: 시장 국면, 시장 대비 변동성, ATR 손절 폭, 거래대금

## 데이터 검증

추천 리포트에는 `데이터 신뢰도`가 함께 표시됩니다. 이 점수는 가격 데이터, 재무 데이터, 수급 데이터를 각각 검증한 뒤 통합한 값입니다.

- 가격: 필수 OHLC 컬럼, 최신성, 중복 날짜, 음수/0 가격, OHLC 범위 오류, 거래량, 단일 급변동, KIS/FDR 종가 교차검증
- 재무: 시가총액, 부채비율, 유동비율, PBR 범위, 영업이익 연속성, pykrx/yfinance PBR 괴리, ROE/성장률 누락 여부
- 수급: 네이버 수급 테이블 컬럼, 최신성, 중복 날짜, 종가 유효성, 분석 가능 일수

개별 종목의 데이터 소스를 점검하려면 아래 명령을 사용하세요.

```powershell
.\.venv\Scripts\python.exe validate_data_sources.py --code 005930
```

이 검증 스크립트는 계좌번호를 마스킹하고 토큰/시크릿은 출력하지 않습니다.

## 백테스트

전략 조건이 과거 데이터에서 어떻게 작동했는지 빠르게 점검할 수 있습니다.

```powershell
.\.venv\Scripts\python.exe backtest_stock_bot.py --years 3 --max-stocks 200
```

결과는 `cache/backtest_trades.csv`, `cache/backtest_summary.json`에 저장됩니다. 이 백테스트는 가격/거래량/시장 국면 기반의 구조 검증용이며, 과거 시점별 재무제표와 수급 데이터까지 완전 재현하는 회계 기준 백테스트는 아닙니다.

## 구조

- `FinancialScanner`: 전종목 유니버스 구성, yfinance 재무제표 수집, 재무 필터링
- `KISDataProvider`: 한국투자증권 접근토큰 발급/캐시, 국내주식 기간별시세와 현재가 조회
- `TradingEngine`: 종목 발굴 결과를 주문 계획으로 변환하고 KIS 현금 주문을 실행
- `RealtimeScanner`: 아침 후보군을 장중 KIS 현재가로 감시하고 조건 포착 시 즉시 알림
- `MarketRegimeFilter`: KOSPI/KOSDAQ150 200일 이동평균선 기반 Risk-On/Risk-Off 판단
- `TechnicalAnalyzer`: RSI, 20일/60일 이동평균선, 저변동성 기반 기술적 분석
- `FactorScorer`: 재무/수급/기술/리스크를 100점 만점으로 점수화
- `AccumulationAnalyzer`: 네이버 금융 외국인/기관 순매매 기반 수급 매집 분석
- `Notifier`: 텔레그램 리포트 전송
- `FinancialHealthBot`: 전체 실행 흐름과 스케줄 관리

## 참고

전종목 재무제표 조회는 시간이 걸릴 수 있습니다. 재무 데이터는 `cache/fundamentals.json`에 7일간 캐시되어 다음 실행부터 속도가 빨라집니다. 조회 실패 종목도 3일간 캐시해서 매일 같은 실패를 반복하지 않습니다.
