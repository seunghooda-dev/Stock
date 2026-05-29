import argparse
import json
import logging
from dataclasses import asdict
from datetime import datetime, timedelta
from typing import Dict, Optional

import FinanceDataReader as fdr
import pandas as pd

from stock_telegram_bot import (
    AccumulationAnalyzer,
    DataQualityValidator,
    FinancialScanner,
    KISDataProvider,
    StockMeta,
    TechnicalAnalyzer,
    mask_account,
)


def find_stock_meta(code: str) -> Optional[StockMeta]:
    listing = fdr.StockListing("KRX")
    listing = listing[listing["Code"].astype(str).str.zfill(6) == code]
    if listing.empty:
        return None
    row = listing.iloc[0]
    return StockMeta(
        code=code,
        name=str(row.get("Name", "")).strip(),
        market=str(row.get("Market", "")).strip(),
        market_cap=safe_float(row.get("Marcap")),
        shares=safe_float(row.get("Stocks")),
        trading_value=safe_float(row.get("Amount")),
        dept=str(row.get("Dept", "") or "").strip(),
    )


def safe_float(value: object) -> Optional[float]:
    try:
        if value is None or pd.isna(value):
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def frame_summary(frame: pd.DataFrame) -> Dict[str, object]:
    if frame is None or frame.empty:
        return {"rows": 0}
    index = frame.index
    if not isinstance(index, pd.DatetimeIndex):
        index = pd.to_datetime(index, errors="coerce")
    latest = index.max()
    result: Dict[str, object] = {"rows": int(len(frame))}
    if pd.notna(latest):
        result["latest_date"] = latest.strftime("%Y-%m-%d")
    if "Close" in frame.columns and not frame["Close"].dropna().empty:
        result["latest_close"] = float(frame["Close"].dropna().iloc[-1])
    return result


def main() -> None:
    logging.getLogger("financial-health-scanner").setLevel(logging.ERROR)

    parser = argparse.ArgumentParser(description="Validate stock data sources without printing secrets")
    parser.add_argument("--code", default="005930", help="KRX stock code, e.g. 005930")
    parser.add_argument("--days", type=int, default=220)
    args = parser.parse_args()

    code = "".join(ch for ch in args.code if ch.isdigit()).zfill(6)
    end_date = datetime.now().strftime("%Y-%m-%d")
    start_date = (datetime.now() - timedelta(days=max(30, args.days))).strftime("%Y-%m-%d")
    min_price_rows = max(30, min(80, int(max(30, args.days) * 0.55)))

    provider = KISDataProvider()
    payload: Dict[str, object] = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "code": code,
        "period": {"start": start_date, "end": end_date},
        "kis": {
            "enabled": provider.enabled,
            "trading_ready": provider.trading_ready,
            "env": provider.trading_env,
            "account": mask_account(provider.account_no, provider.account_product_code),
        },
    }

    kis_frame = None
    fdr_frame = None
    try:
        if provider.enabled:
            kis_frame = provider.fetch_daily_price(code, start_date, end_date)
            payload["kis_daily"] = {
                "summary": frame_summary(kis_frame),
                "quality": asdict(DataQualityValidator.validate_price_frame(kis_frame, "KIS 일봉", min_rows=min_price_rows)),
            }
    except Exception as exc:
        payload["kis_daily"] = {"error": str(exc)}

    try:
        fdr_frame = fdr.DataReader(code, start_date, end_date)
        payload["fdr_daily"] = {
            "summary": frame_summary(fdr_frame),
            "quality": asdict(DataQualityValidator.validate_price_frame(fdr_frame, "FDR 일봉", min_rows=min_price_rows)),
        }
    except Exception as exc:
        payload["fdr_daily"] = {"error": str(exc)}

    if kis_frame is not None and fdr_frame is not None:
        payload["price_crosscheck"] = asdict(
            DataQualityValidator.compare_price_sources(kis_frame, fdr_frame, "KIS", "FDR")
        )

    meta = find_stock_meta(code)
    if meta is None:
        payload["stock_meta"] = {"error": "KRX listing에서 종목을 찾지 못했습니다."}
    else:
        payload["stock_meta"] = asdict(meta)
        try:
            metrics = FinancialScanner().fetch_financial_metrics(meta)
            if metrics is None:
                payload["financials"] = {"error": "재무 데이터 조회 실패"}
            else:
                payload["financials"] = {
                    "source": metrics.financial_source,
                    "pbr": metrics.pbr,
                    "per": metrics.per,
                    "roe": metrics.roe,
                    "quality": {
                        "score": metrics.data_quality_score,
                        "grade": metrics.data_quality_grade,
                        "warnings": metrics.data_quality_warnings,
                    },
                }
        except Exception as exc:
            payload["financials"] = {"error": str(exc)}

        try:
            analyzer = AccumulationAnalyzer()
            investor_data = analyzer._fetch_investor_data(code)
            payload["investor_flow"] = {
                "summary": {
                    "rows": int(len(investor_data)),
                    "latest_date": investor_data["date"].max().strftime("%Y-%m-%d") if not investor_data.empty else "",
                },
                "quality": asdict(analyzer._validate_investor_data(investor_data)),
            }
        except Exception as exc:
            payload["investor_flow"] = {"error": str(exc)}

    try:
        selected_frame, selected_quality = TechnicalAnalyzer(provider)._fetch_price_data(code)
        payload["selected_price_source"] = {
            "summary": frame_summary(selected_frame),
            "quality": asdict(selected_quality),
        }
    except Exception as exc:
        payload["selected_price_source"] = {"error": str(exc)}

    print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
