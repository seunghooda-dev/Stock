import argparse
import json
import logging
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional

import FinanceDataReader as fdr
import pandas as pd
from ta.momentum import RSIIndicator
from ta.volatility import AverageTrueRange

from stock_telegram_bot import (
    ATR_STOP_MULTIPLIER,
    CACHE_DIR,
    EXCLUDE_DEPT_KEYWORDS,
    EXCLUDE_NAME_KEYWORDS,
    KOSDAQ_MARKET_INDEX_CODE,
    MA_LONG,
    MA_SHORT,
    MARKET_INDEX_CODE,
    MARKET_REGIME_MA,
    MARKETS,
    MAX_DISTANCE_ABOVE_MA20,
    MIN_DAILY_TRADING_VALUE,
    MIN_HISTORY_DAYS,
    MIN_MARKET_CAP,
    MIN_RSI,
    RSI_WINDOW,
    ATR_WINDOW,
    MAX_RSI,
    MA_SUPPORT_BAND,
    clamp,
)


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("stock-backtester")


@dataclass
class BacktestConfig:
    years: int = 3
    max_stocks: int = 200
    max_holding_days: int = 20
    exit_ma_break_pct: float = 0.03
    min_volume_ratio: float = 1.0
    output_dir: str = str(CACHE_DIR)


@dataclass
class BacktestTrade:
    code: str
    name: str
    market: str
    entry_date: str
    exit_date: str
    entry_price: float
    exit_price: float
    stop_loss: float
    return_pct: float
    holding_days: int
    exit_reason: str


class StrategyBacktester:
    def __init__(self, config: BacktestConfig) -> None:
        self.config = config
        self.end_date = datetime.now()
        self.start_date = self.end_date - timedelta(days=365 * config.years)
        self.warmup_start_date = self.start_date - timedelta(days=430)

    def run(self) -> Dict[str, object]:
        universe = self._fetch_universe()
        regimes = self._build_regime_series()

        trades: List[BacktestTrade] = []
        for index, stock in enumerate(universe, start=1):
            if index % 25 == 0:
                logger.info("백테스트 진행률: %d/%d, 누적 거래 %d건", index, len(universe), len(trades))
            try:
                data = self._fetch_price_data(stock["code"])
                stock_trades = self._simulate_stock(stock, data, regimes)
                trades.extend(stock_trades)
            except Exception as exc:
                logger.debug("%s(%s) 백테스트 제외: %s", stock["name"], stock["code"], exc)

        summary = self._summarize(trades)
        self._save_results(trades, summary)
        return summary

    def _fetch_universe(self) -> List[Dict[str, object]]:
        listing = fdr.StockListing("KRX")
        listing = listing[listing["Market"].isin(MARKETS)].copy()
        rows: List[Dict[str, object]] = []

        for row in listing.itertuples(index=False):
            code = str(row.Code).zfill(6)
            name = str(row.Name).strip()
            market = str(row.Market).strip()
            dept = str(getattr(row, "Dept", "") or "")
            market_cap = self._safe_float(getattr(row, "Marcap", None))
            trading_value = self._safe_float(getattr(row, "Amount", None))

            if any(keyword in name for keyword in EXCLUDE_NAME_KEYWORDS):
                continue
            if any(keyword in dept for keyword in EXCLUDE_DEPT_KEYWORDS):
                continue
            if market_cap is None or market_cap < MIN_MARKET_CAP:
                continue
            if trading_value is None or trading_value < MIN_DAILY_TRADING_VALUE:
                continue

            rows.append(
                {
                    "code": code,
                    "name": name,
                    "market": market,
                    "market_cap": market_cap,
                    "trading_value": trading_value,
                }
            )

        rows.sort(key=lambda item: float(item["trading_value"]), reverse=True)
        selected = rows[: max(1, self.config.max_stocks)]
        logger.info("백테스트 대상 종목: %d개", len(selected))
        return selected

    def _build_regime_series(self) -> Dict[str, pd.Series]:
        return {
            "KOSPI": self._regime_series(MARKET_INDEX_CODE),
            "KOSDAQ": self._regime_series(KOSDAQ_MARKET_INDEX_CODE),
        }

    def _regime_series(self, index_code: str) -> pd.Series:
        data = fdr.DataReader(
            index_code,
            self.warmup_start_date.strftime("%Y-%m-%d"),
            self.end_date.strftime("%Y-%m-%d"),
        )
        if data.empty or "Close" not in data.columns:
            raise RuntimeError(f"{index_code} 시장 국면 데이터를 가져오지 못했습니다.")
        close = data["Close"].astype(float)
        ma200 = close.rolling(MARKET_REGIME_MA).mean()
        return (close >= ma200).fillna(False)

    def _fetch_price_data(self, code: str) -> pd.DataFrame:
        data = fdr.DataReader(
            code,
            self.warmup_start_date.strftime("%Y-%m-%d"),
            self.end_date.strftime("%Y-%m-%d"),
        )
        if data.empty:
            raise ValueError("가격 데이터 없음")

        columns = [column for column in ["Open", "High", "Low", "Close", "Volume"] if column in data.columns]
        prices = data[columns].copy()
        for column in columns:
            prices[column] = pd.to_numeric(prices[column], errors="coerce")
        prices = prices.dropna(subset=["High", "Low", "Close"])
        if len(prices) < MIN_HISTORY_DAYS:
            raise ValueError(f"데이터 부족: {len(prices)}일")

        prices["MA20"] = prices["Close"].rolling(MA_SHORT).mean()
        prices["MA60"] = prices["Close"].rolling(MA_LONG).mean()
        prices["AVG_VOLUME20"] = prices["Volume"].rolling(MA_SHORT).mean() if "Volume" in prices else 0.0
        prices["RSI"] = RSIIndicator(close=prices["Close"], window=RSI_WINDOW).rsi()
        prices["ATR"] = AverageTrueRange(
            high=prices["High"],
            low=prices["Low"],
            close=prices["Close"],
            window=ATR_WINDOW,
        ).average_true_range()
        return prices.dropna()

    def _simulate_stock(
        self,
        stock: Dict[str, object],
        prices: pd.DataFrame,
        regimes: Dict[str, pd.Series],
    ) -> List[BacktestTrade]:
        market = str(stock["market"])
        risk_on = regimes.get(market, regimes["KOSPI"]).reindex(prices.index, method="ffill").fillna(False)
        trades: List[BacktestTrade] = []
        i = max(MA_LONG, MARKET_REGIME_MA)

        while i < len(prices) - 2:
            if prices.index[i] < pd.Timestamp(self.start_date.date()):
                i += 1
                continue
            if not bool(risk_on.iloc[i]):
                i += 1
                continue

            row = prices.iloc[i]
            five_days_ago = prices.iloc[max(0, i - 5)]
            current_price = float(row["Close"])
            ma20 = float(row["MA20"])
            ma60 = float(row["MA60"])
            avg_volume20 = float(row.get("AVG_VOLUME20", 0.0))
            volume = float(row.get("Volume", 0.0))
            volume_ratio = volume / avg_volume20 if avg_volume20 > 0 else 1.0

            entry_signal = (
                ma20 * (1 - MA_SUPPORT_BAND) <= current_price <= ma20 * (1 + MAX_DISTANCE_ABOVE_MA20)
                and ma20 > float(five_days_ago["MA20"])
                and ma20 > ma60
                and MIN_RSI <= float(row["RSI"]) <= MAX_RSI
                and volume_ratio >= self.config.min_volume_ratio
            )
            if not entry_signal:
                i += 1
                continue

            entry_index = i + 1
            entry_row = prices.iloc[entry_index]
            entry_price = float(entry_row.get("Open", entry_row["Close"]) or entry_row["Close"])
            stop_loss = max(0.0, entry_price - ATR_STOP_MULTIPLIER * float(row["ATR"]))
            exit_index, exit_price, exit_reason = self._find_exit(prices, entry_index, stop_loss)
            exit_date = prices.index[exit_index]
            holding_days = max(1, exit_index - entry_index)
            return_pct = (exit_price / entry_price - 1) * 100 if entry_price > 0 else 0.0

            trades.append(
                BacktestTrade(
                    code=str(stock["code"]),
                    name=str(stock["name"]),
                    market=market,
                    entry_date=prices.index[entry_index].strftime("%Y-%m-%d"),
                    exit_date=exit_date.strftime("%Y-%m-%d"),
                    entry_price=round(entry_price, 2),
                    exit_price=round(exit_price, 2),
                    stop_loss=round(stop_loss, 2),
                    return_pct=round(return_pct, 2),
                    holding_days=holding_days,
                    exit_reason=exit_reason,
                )
            )
            i = exit_index + 1

        return trades

    def _find_exit(self, prices: pd.DataFrame, entry_index: int, stop_loss: float) -> tuple[int, float, str]:
        max_exit = min(len(prices) - 1, entry_index + self.config.max_holding_days)
        for exit_index in range(entry_index, max_exit + 1):
            row = prices.iloc[exit_index]
            if float(row["Low"]) <= stop_loss:
                return exit_index, stop_loss, "ATR_STOP"
            if exit_index > entry_index and float(row["Close"]) < float(row["MA20"]) * (1 - self.config.exit_ma_break_pct):
                return exit_index, float(row["Close"]), "MA20_BREAK"
        return max_exit, float(prices.iloc[max_exit]["Close"]), "MAX_HOLD"

    def _summarize(self, trades: List[BacktestTrade]) -> Dict[str, object]:
        if not trades:
            return {
                "generated_at": datetime.now().isoformat(timespec="seconds"),
                "trades": 0,
                "message": "조건에 맞는 과거 거래가 없습니다.",
            }

        returns = pd.Series([trade.return_pct / 100 for trade in trades], dtype=float)
        wins = returns[returns > 0]
        losses = returns[returns <= 0]
        equity = (1 + returns).cumprod()
        drawdown = equity / equity.cummax() - 1
        profit_factor = wins.sum() / abs(losses.sum()) if abs(losses.sum()) > 0 else None

        return {
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "years": self.config.years,
            "max_stocks": self.config.max_stocks,
            "trades": len(trades),
            "win_rate_pct": round(float((returns > 0).mean() * 100), 2),
            "avg_return_pct": round(float(returns.mean() * 100), 2),
            "median_return_pct": round(float(returns.median() * 100), 2),
            "best_return_pct": round(float(returns.max() * 100), 2),
            "worst_return_pct": round(float(returns.min() * 100), 2),
            "profit_factor": round(float(profit_factor), 2) if profit_factor is not None else "inf",
            "max_drawdown_pct": round(float(drawdown.min() * 100), 2),
            "avg_holding_days": round(sum(trade.holding_days for trade in trades) / len(trades), 1),
        }

    def _save_results(self, trades: List[BacktestTrade], summary: Dict[str, object]) -> None:
        output_dir = Path(self.config.output_dir)
        output_dir.mkdir(exist_ok=True)
        trade_path = output_dir / "backtest_trades.csv"
        summary_path = output_dir / "backtest_summary.json"

        pd.DataFrame([asdict(trade) for trade in trades]).to_csv(trade_path, index=False, encoding="utf-8-sig")
        with summary_path.open("w", encoding="utf-8") as file:
            json.dump(summary, file, ensure_ascii=False, indent=2)
        logger.info("백테스트 결과 저장: %s, %s", trade_path, summary_path)

    @staticmethod
    def _safe_float(value: object) -> Optional[float]:
        try:
            if value is None or pd.isna(value):
                return None
            return float(value)
        except (TypeError, ValueError):
            return None


def parse_args() -> BacktestConfig:
    parser = argparse.ArgumentParser(description="Stock Telegram Bot strategy backtester")
    parser.add_argument("--years", type=int, default=3)
    parser.add_argument("--max-stocks", type=int, default=200)
    parser.add_argument("--max-holding-days", type=int, default=20)
    parser.add_argument("--exit-ma-break-pct", type=float, default=0.03)
    parser.add_argument("--min-volume-ratio", type=float, default=1.0)
    parser.add_argument("--output-dir", default=str(CACHE_DIR))
    args = parser.parse_args()
    return BacktestConfig(
        years=max(1, args.years),
        max_stocks=max(1, args.max_stocks),
        max_holding_days=max(1, args.max_holding_days),
        exit_ma_break_pct=max(0.0, args.exit_ma_break_pct),
        min_volume_ratio=clamp(args.min_volume_ratio, 0.0, 10.0),
        output_dir=args.output_dir,
    )


def main() -> None:
    config = parse_args()
    summary = StrategyBacktester(config).run()
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
