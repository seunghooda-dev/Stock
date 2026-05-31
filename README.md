# Financial Health Stock Scanner

KOSPI/KOSDAQ 전종목 중 재무 건전성이 좋고 자산가치 대비 저평가된 종목을 1차로 추린 뒤, 시장 국면, 저변동성, 외국인/기관 수급, 기술적 진입 타점을 함께 통과한 후보만 텔레그램으로 전송하는 스캐너 봇입니다.

## 5분 운영 순서

처음 보는 PC에서도 아래 순서만 지키면 현재 상태를 객관적으로 판단할 수 있습니다.

1. `setup_windows_pc.bat` 실행
2. `.env`에 텔레그램/KIS 값을 입력
3. 바탕화면의 `StockBot_Check.bat` 실행
4. 점검 결과가 `ALERT_READY` 또는 `DEMO_TRADE_READY`이면 `StockBot_Run.bat` 실행
5. 운영 중에는 `StockBot_Status.bat`으로 최근 리서치, 후보군, 락, 로그를 확인
6. 실계좌 자동매매는 `operator_readiness.py --target live-trading`이 통과하고, 모의운영 로그를 충분히 확인한 뒤에만 전환

운영 판단 기준은 단순합니다.

- `ALERT_READY`: 종목 발굴/텔레그램 알림용으로 사용 가능
- `DEMO_TRADE_READY`: 모의 주문 또는 dry-run 자동매매 연습 가능
- `LIVE_TRADE_READY`: 실계좌 자동매매 설정까지 통과했지만, 실제 운용 전 사람이 최종 승인해야 함
- `ACTION_REQUIRED`: 차단 항목이 있으므로 실행 전 수정 필요

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

## 운영 준비도 점검

`operator_readiness.py`는 빌드/설정/데이터/API/위험한도를 한 번에 확인하는 운영 체크리스트입니다. 민감정보는 출력하지 않고 계좌번호는 마스킹합니다.

```powershell
.\.venv\Scripts\python.exe operator_readiness.py --target alert
.\.venv\Scripts\python.exe operator_readiness.py --target demo-trading
.\.venv\Scripts\python.exe operator_readiness.py --target live-trading
```

주요 점검 항목:

- Python과 필수 패키지 설치 여부
- `.env`, `.gitignore`, 실행 스크립트 존재 여부
- Telegram Bot API 연결과 선택적 테스트 메시지 전송
- KIS 계좌/모의투자/실전투자 설정과 현재가 조회
- KRX/FDR 가격 데이터 품질
- 전략 프로파일, 의사결정 등급, 자동매매 하위 점수 기준
- 최근 봇 실행 상태(`cache/bot_state.json`)와 마지막 리서치 성공/실패 여부
- 최근 백테스트 표본 수와 결과 파일 존재 여부

텔레그램 테스트 메시지를 같이 보내려면 아래처럼 실행합니다.

```powershell
.\.venv\Scripts\python.exe operator_readiness.py --target alert --send-telegram-test
```

JSON으로 저장해 운영 기록을 남길 수도 있습니다.

```powershell
.\.venv\Scripts\python.exe operator_readiness.py --target alert --json > cache\readiness_report.json
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
AUTO_TRADE_MIN_SCORE=82
AUTO_TRADE_MIN_DATA_QUALITY=85
AUTO_TRADE_MAX_STOP_LOSS_PCT=8
AUTO_TRADE_MIN_FINANCIAL_SCORE=20
AUTO_TRADE_MIN_ACCUMULATION_SCORE=12
AUTO_TRADE_MIN_TECHNICAL_SCORE=17
AUTO_TRADE_MIN_RISK_SCORE=13
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

텔레그램 전송도 네트워크 지연이나 429 응답을 견디도록 재시도합니다.

```text
TELEGRAM_MAX_RETRIES=3
TELEGRAM_RETRY_DELAY_SECONDS=2.0
TELEGRAM_TIMEOUT_SECONDS=20.0
```

## 전략 프로파일

기본값은 `STRATEGY_PROFILE=institutional`입니다. 프로파일은 명시적으로 개별 값을 지정하지 않은 설정의 기본 기준을 바꿉니다.

- `conservative`: 후보 수는 적지만 점수, 데이터 신뢰도, 손절폭 기준을 가장 엄격하게 적용
- `institutional`: 기본 추천값. 수급, 상대강도, 데이터 신뢰도, 리스크를 균형 있게 강화
- `balanced`: 후보 수와 엄격함을 중간으로 조절
- `aggressive`: 더 많은 후보를 보되 실전 주문 전 방어 게이트는 유지

현재 권장값은 `institutional`, `MIN_FACTOR_SCORE=72`, `MIN_DATA_QUALITY_SCORE=80`, `AUTO_TRADE_MIN_SCORE=82`, `AUTO_TRADE_MIN_DATA_QUALITY=85`입니다.

## 단계별 종목 발굴

기준이 너무 높아 후보를 놓치는 문제를 줄이기 위해 발굴 단계와 주문 단계를 분리했습니다. 기본값은 `WATCHLIST_ENABLED=true`입니다.

- `관찰 후보`: 재무 기준을 부채비율 180% 이하, 유동비율 100% 이상, PBR 2.5 이하, 최근 영업이익 2년 이상 흑자로 넓혀 먼저 레이더에 올립니다. 기술 기준도 RSI 30~65, 20일선 하단 10%~상단 20%, 60일 상대강도 -5%p 이상, 손익비 0.5 이상으로 넓혀 “놓치지 않는 감시”에 초점을 둡니다. 수급 매집은 점수에는 반영하지만 필수 조건은 아닙니다.
- `레이더 후보`: 관심 후보에도 못 미치지만 리서치할 만한 상위권 종목입니다. RSI 20~80, 20일선 하단 25%~상단 40%, 60일 상대강도 -20%p 이상처럼 넓은 기준을 씁니다. 이 단계는 매수 신호가 아니며 자동매매는 코드상에서 차단됩니다.
- `강력 후보`: 정규 기술 조건과 종합 점수를 통과했지만 자동매매 하위 점수, 손절폭, 데이터 신뢰도 중 일부가 부족한 알림 우선 후보입니다.
- `자동매매 가능`: 정규 후보 중 `AUTO_TRADE_MIN_SCORE`, `AUTO_TRADE_MIN_DATA_QUALITY`, 손절폭, 재무/수급/기술/리스크 하위 점수를 모두 통과한 경우에만 주문 계획으로 넘어갑니다.

추천 기본값은 `WATCHLIST_MIN_FACTOR_SCORE=58`, `WATCHLIST_MIN_INVESTMENT_THESIS_SCORE=55`, `WATCHLIST_MIN_DATA_QUALITY_SCORE=68`, `RADAR_MIN_FACTOR_SCORE=35`입니다. 이렇게 하면 발견 폭은 넓히되, 실전 주문은 기존보다 느슨해지지 않습니다.

텔레그램 리포트와 실시간 감시 후보군은 `종합점수 높은 순`으로 정렬됩니다. 봇은 전체 후보를 모두 리서치한 뒤 기본적으로 `TELEGRAM_RECOMMENDATION_LIMIT=3`에 맞춰 상위 3개만 텔레그램에 표시합니다. 나머지 상위 후보는 장중 감시 캐시에만 보관합니다. 등급은 매수 가능 여부를 판단하는 보조 정보이며, `레이더 후보`와 `관찰 후보`는 점수가 높아도 자동매매로 넘어가지 않습니다.

## 의사결정 등급

봇은 최종 후보를 바로 같은 수준의 매수 신호로 보지 않고, 근거와 보류 사유를 함께 붙여 3단계로 나눕니다.

- `관심 후보`: 최종 필터는 통과했지만 자동매매 기준에는 부족하므로 장중 감시 대상으로만 유지
- `강력 후보`: 점수와 근거가 강하지만 하위 점수, 데이터 품질, 손절폭 중 하나가 부족해 자동매매는 보류
- `자동매매 가능`: 종합점수, 데이터 신뢰도, 손절폭, 재무/수급/기술/리스크 하위 점수를 모두 통과

이 등급은 텔레그램 리포트의 `의사결정` 줄에 표시됩니다. 실계좌 자동매매는 등급이 `자동매매 가능`이어도 `.env`에서 실전 주문 확인값을 명시적으로 켜기 전까지 차단됩니다.

## 투자 가설 모델

종목 선정은 단순 저PBR이나 단순 차트 신호가 아니라 `품질 + 가치 + 모멘텀 + 심리 + 손익비`를 100점으로 다시 검증합니다. 기본값은 `MIN_INVESTMENT_THESIS_SCORE=70`입니다.

- 품질 25점: 부채비율, 유동비율, ROE, 영업이익률, 흑자 연속성, 매출 성장
- 가치 25점: PBR, PER, ROE 대비 저평가, 영업이익 성장
- 모멘텀 25점: 시장 대비 60일 상대강도, 120~20일 중기 모멘텀, 180일 고점 근접도, 20/60일선 구조, 거래량
- 심리 15점: 단기 과열 회피, 60일 최대낙폭, RSI 위치, 외국인/기관 매집 중 횡보 여부
- 손익비 10점: ATR 손절선 대비 목표 구간, 손절폭, 거래대금

이 모델의 의도는 세 가지입니다.

- 싸지만 부실한 가치함정을 제외합니다.
- 좋아 보이지만 이미 과열된 종목을 줄입니다.
- 손실폭 대비 기대 구간이 부족한 종목은 알림/주문 후보에서 낮춥니다.

참고한 공개 연구와 투자 원칙:

- Fama/French 5팩터: 가치, 수익성, 투자 패턴을 평균 수익률 설명 요인으로 봄
- AQR Quality Minus Junk: 수익성, 성장성, 안정성 중심의 품질 팩터
- Jegadeesh/Titman 모멘텀: 3~12개월 중기 승자 효과
- George/Hwang 52주 고점 모멘텀: 고점 근접도가 미래 수익 예측에 유용할 수 있음
- Cascade식 장기 기본가치 접근: 단기 신호보다 장기 품질과 리스크 관리 우선

## 실행

```powershell
.\.venv\Scripts\python.exe stock_telegram_bot.py
```

실행 직후 1회 스캔하고, 이후 매일 한국 시간 기준 오후 4시에 자동 실행됩니다.

바탕화면에서 실행하려면 `StockBot_Run.bat`을 더블클릭하세요. 종료가 필요하면 `StockBot_Stop.bat`을 더블클릭하면 실행 중인 봇 프로세스를 정리합니다.

실행 전에는 `StockBot_Check.bat`으로 운영 준비도를 먼저 확인하세요. 이 점검은 차단 항목이 있으면 종료 코드 1로 끝나므로, 자동 배포나 원격 PC 점검에도 사용할 수 있습니다.

다른 PC를 상시 운영용으로 쓸 때는 아래 순서로 진행하세요.

```powershell
git clone https://github.com/seunghooda-dev/Stock.git
cd Stock
.\setup_windows_pc.bat
notepad .env
.\.venv\Scripts\python.exe operator_readiness.py --target alert
.\.venv\Scripts\python.exe test_kis_connection.py
```

다른 PC에는 Git과 Python 3.11 이상이 먼저 설치되어 있어야 합니다. PC 로그인 시 자동 실행되게 하려면 `install_startup_task.bat`을 더블클릭하세요. 자동 실행을 제거하려면 `uninstall_startup_task.bat`을 사용합니다. 자동 실행 로그는 `logs/bot.log`에 저장되며, `logs/`는 Git에 올라가지 않습니다.

상시 운영용 PC는 전원이 켜져 있고 Windows 사용자가 로그인되어 있어야 알림/감시가 계속 동작합니다. 절전 모드에 들어가면 봇도 멈추므로, 운영 PC의 전원 설정에서 절전 모드를 꺼두는 것을 권장합니다.

## 운영 안정성 및 가시성

봇은 중복 실행과 상태 미확인을 줄이기 위해 아래 운영 파일을 자동으로 관리합니다.

- `logs/bot.log`: 콘솔과 별개로 남는 회전 로그 파일입니다. 파일이 커지면 자동으로 백업됩니다.
- `cache/bot_state.json`: 최근 장마감 리서치, 실시간 스캔, 뉴스 스캔, 자동매매 실행 상태와 후보 수, 상위 추천 요약을 저장합니다.
- `cache/latest_research_report.json`: 마지막 전체 리서치의 추천 Top 3, 내부 감시 후보, 점수/재무/기술/수급 근거, 필터별 탈락 병목을 저장합니다.
- `cache/*.lock`: 같은 작업이 중복 실행되지 않도록 막는 실행 락입니다. 오래된 락은 설정 시간 이후 자동 제거됩니다.

주요 JSON 캐시는 임시 파일에 먼저 기록한 뒤 교체하는 원자적 저장 방식을 사용합니다. PC 종료나 프로세스 강제 종료가 겹쳐도 `fundamentals.json`, `realtime_candidates.json`, `bot_state.json`, `latest_research_report.json` 같은 운영 파일이 반쯤 저장되는 위험을 줄입니다.

중복 실행 방지 기본값은 아래와 같습니다.

```text
RUN_LOCK_STALE_MINUTES=180
SCHEDULER_LOCK_STALE_MINUTES=720
```

현재 상태를 확인하려면 아래 명령을 실행하세요. `Bot state` 항목에서 마지막 리서치 성공/실패, 후보 수, 전송 수를 볼 수 있습니다.

```powershell
.\.venv\Scripts\python.exe operator_readiness.py --target alert --no-network
```

더 자세한 운영 대시보드는 아래 명령 또는 바탕화면의 `StockBot_Status.bat`으로 확인합니다.

```powershell
.\.venv\Scripts\python.exe status_stock_bot.py
.\.venv\Scripts\python.exe status_stock_bot.py --json
```

상태 대시보드는 실행 중인 봇 프로세스, 최근 작업별 성공/실패, 최신 리서치 Top 3, 실시간 후보군 수, 대기 주문, 뉴스 알림, 활성 락, 로그 마지막 줄을 보여줍니다. 최신 리서치 파일이 있으면 `유니버스 -> 재무 통과 -> 최종 후보` 경로와 `기술조건/팩터점수/투자가설/데이터품질` 등 주요 탈락 병목도 함께 표시합니다.

텔레그램 장마감 리포트 상단에는 전체 리서치 후보 수, 내부 감시 후보 수, 추천 컷 점수, 후보 분포가 표시됩니다. 상세 리포트는 `TOP 1~3`만 내려가므로 낮은 점수 후보가 추천처럼 섞이지 않습니다.

## 즉시 알림

장마감 종목 발굴은 전체 스캔이 끝난 뒤 종합점수 상위 3개만 텔레그램으로 보냅니다. 스캔 중 개별 종목을 발견하자마자 보내는 알림은 기본적으로 꺼져 있어 낮은 점수 후보가 먼저 전송되지 않습니다.

- 표시 개수는 `.env`의 `TELEGRAM_RECOMMENDATION_LIMIT`로 조정합니다.
- 내부 감시 후보군은 별도 캐시에 보관되며 장중 실시간 감시에 활용됩니다.
- 장중 실시간 감시는 후보군 안에서 조건이 새로 포착될 때 별도 알림을 보냅니다.

## 장중 실시간 알림

장중에는 전종목을 반복 분석하지 않고, 아침에 만든 후보군만 KIS 현재가 API로 감시합니다. 기본 흐름은 `08:40 후보군 준비 -> 09:20~14:50 실시간 감시 -> 16:00 장마감 리포트`입니다.

일봉 기반 기술분석은 기본적으로 `FinanceDataReader`를 먼저 사용합니다. 한국투자증권 일봉 API가 일시적으로 500 오류를 반복하면 전종목 스캔 시간이 크게 늘어날 수 있기 때문입니다. 장중 현재가, 실시간 알림, 주문은 계속 KIS API를 사용합니다. 일봉도 KIS 우선으로 쓰려면 `.env`에서 `KIS_DAILY_PRICE_ENABLED=true`로 바꾸면 됩니다.

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

## 뉴스 속보 레이더

뉴스는 매수 신호가 아니라 악재 회피와 테마 변화 감지용 리스크 레이더로 사용합니다. 기본값은 5분마다 Google News RSS를 확인하고, 시장/테마 키워드와 실시간 후보군 상위 종목명을 함께 감시합니다.

```text
NEWS_ALERT_ENABLED=true
NEWS_SCAN_INTERVAL_SECONDS=300
NEWS_LOOKBACK_MINUTES=90
NEWS_MAX_STOCK_QUERIES=10
NEWS_MIN_IMPACT_SCORE=4
NEWS_BLOCK_AUTO_TRADE_ON_RISK=true
NEWS_TRADE_BLOCK_LOOKBACK_HOURS=6
NEWS_TRADE_BLOCK_MIN_SCORE=6
```

속보 제목에 아래 유형의 키워드가 잡히면 텔레그램으로 즉시 보냅니다.

- 고위험: 거래정지, 상장폐지, 횡령, 배임, 감사의견, 불성실공시, 관리종목
- 악재: 유상증자, 전환사채, 실적 쇼크, 적자전환, 영업손실, 하한가, 리콜, 소송
- 호재: 수주, 공급계약, 어닝 서프라이즈, 흑자전환, 자사주, 배당, 목표가 상향

후보 종목에 대해 최근 고위험/악재 뉴스가 감지되면 자동매매 대기 주문은 `NEWS_BLOCK`으로 차단됩니다. RSS 제목 기반 1차 필터이므로 중요한 뉴스는 반드시 원문 기사와 DART/KRX 공시를 확인해야 합니다.

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
- 60일 수익률이 해당 시장 지수보다 우월한 상대강도 조건 통과
- 20일/120일 수익률 과열과 60일 최대낙폭 조건 통과
- 120~20일 중기 모멘텀과 180일 고점 근접도 조건 통과
- ATR 손절폭 대비 목표 구간 손익비 조건 통과

## 리스크 관리

- ATR(14)을 계산합니다.
- 손절선은 `현재가 - 2 * ATR`로 표시합니다.
- 유동성이 낮은 종목은 호가 공백과 체결 리스크가 크기 때문에 사전에 제외합니다.
- 자동매매는 1회 주문 수, 종목당 예산, 1회 총 노출 한도, 동일 종목 재진입 쿨다운을 적용합니다.
- 알림 후보보다 자동매매 후보 기준이 더 높습니다. 기본값은 종합점수 82점 이상, 데이터 신뢰도 85점 이상, ATR 손절폭 8% 이하입니다.
- 자동매매는 총점만 보지 않고 재무 20점, 수급 12점, 기술 17점, 리스크 13점 이상의 하위 점수 기준도 함께 확인합니다.
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

최종 후보는 단순 조건 통과가 아니라 100점 만점 점수로 다시 정렬합니다. `institutional` 프로파일의 기본 통과선은 `MIN_FACTOR_SCORE=72`입니다.

- 재무 30점: PBR, 부채비율, 유동비율, ROE, 영업이익률, 매출 성장
- 수급 25점: 상장주식수 대비 순매수, 시총 대비 순매수금액, 양수급 일수, 횡보 여부
- 기술 25점: RSI 위치, 20/60일선 스프레드, 20일선 근접도, 거래량, 시장 대비 60일 상대강도, 60일 최대낙폭, 상향 돌파
- 리스크 20점: 시장 국면, 시장 대비 변동성, ATR 손절 폭, 거래대금

별도로 `투자 가설 점수`가 계산됩니다. 팩터 점수는 정렬과 등급화에, 투자 가설 점수는 “왜 이 종목을 살 만한가”를 검증하는 2차 체크에 사용됩니다.

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
- `DecisionPolicy`: 관심 후보/강력 후보/자동매매 가능 등급과 보류 사유 판정
- `Notifier`: 텔레그램 리포트 전송
- `FinancialHealthBot`: 전체 실행 흐름과 스케줄 관리
- `operator_readiness.py`: 운영 PC, API, 데이터, 전략/위험 설정을 한 번에 점검하는 실행 전 감사 도구

## 참고

전종목 재무제표 조회는 시간이 걸릴 수 있습니다. 재무 데이터는 `cache/fundamentals.json`에 7일간 캐시되어 다음 실행부터 속도가 빨라집니다. 조회 실패 종목도 3일간 캐시해서 매일 같은 실패를 반복하지 않습니다.
