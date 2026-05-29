from datetime import datetime, timedelta

from stock_telegram_bot import KISDataProvider, mask_account


def main() -> None:
    provider = KISDataProvider()
    if not provider.enabled:
        raise SystemExit("KIS_APP_KEY and KIS_APP_SECRET are required in .env.")

    print("KIS trading environment:")
    print(
        {
            "env": provider.trading_env,
            "base_url": provider.base_url,
            "trading_ready": provider.trading_ready,
            "account": mask_account(provider.account_no, provider.account_product_code),
        }
    )

    code = "005930"
    end_date = datetime.now().strftime("%Y-%m-%d")
    start_date = (datetime.now() - timedelta(days=14)).strftime("%Y-%m-%d")

    print("KIS current price:")
    print(provider.fetch_current_price(code))

    print("\nKIS daily price:")
    print(provider.fetch_daily_price(code, start_date, end_date).tail())


if __name__ == "__main__":
    main()
