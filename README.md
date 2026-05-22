# Stock Telegram Bot

일본 주요 종목의 최근 6개월 주가를 수집하고 RSI, 20일 이동평균선 기준으로 매수 후보를 골라 텔레그램으로 전송하는 Python 봇입니다.

## 설치

```powershell
pip install -r requirements.txt
```

## 설정

`stock_telegram_bot.py` 상단의 값을 입력하세요.

```python
TELEGRAM_TOKEN = "텔레그램 봇 토큰"
CHAT_ID = "텔레그램 채팅 ID"
```

## 실행

```powershell
python stock_telegram_bot.py
```

프로그램은 시작 직후 한 번 분석을 실행하고, 이후 매일 한국 시간 기준 오후 4시에 다시 실행됩니다.

## 추천 기준

- RSI 14일 기준 30 이하
- 현재가가 20일 이동평균선에 3% 이내로 근접했거나 20일 이동평균선을 돌파하려는 경우

## 대상 종목

- `8035.T` 도쿄일렉트론
- `6857.T` 어드반테스트
- `7203.T` 토요타
- `6758.T` 소니
- `9984.T` 소프트뱅크
