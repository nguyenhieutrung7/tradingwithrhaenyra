"""
High Leverage Scalper Bot Runner
Chạy liên tục, scan market và execute trades
"""

import asyncio
import logging
import os
from datetime import datetime, timedelta
from typing import Dict, List

from binance.client import Client
from binance.exceptions import BinanceAPIException

from ..strategies.high_lev_scalper import (
    HighLevScalper,
    BinanceFuturesExecutor,
    ScalpSetup,
    PositionSize
)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class ScalperRunner:
    """
    Runner cho high leverage scalper
    - Scan market mỗi 1 phút
    - Max 2 positions cùng lúc
    - Auto close trước funding (8h UTC)
    """

    def __init__(self):
        self.api_key = os.getenv('BINANCE_API_KEY')
        self.api_secret = os.getenv('BINANCE_API_SECRET')

        if not self.api_key or not self.api_secret:
            raise ValueError("BINANCE_API_KEY và BINANCE_API_SECRET required")

        self.client = Client(self.api_key, self.api_secret)
        self.strategy = HighLevScalper(self.client)
        self.executor = BinanceFuturesExecutor(self.client)

        self.active_positions: Dict[str, Dict] = {}
        self.max_positions = 2
        self.scan_interval = 60  # seconds

    async def run(self):
        """Main loop"""
        logger.info("Starting High Leverage Scalper Bot...")
        logger.info(f"Max positions: {self.max_positions}")
        logger.info(f"Leverage: 50x Isolated")
        logger.info(f"Scan interval: {self.scan_interval}s")

        while True:
            try:
                await self._scan_and_trade()
                await asyncio.sleep(self.scan_interval)
            except Exception as e:
                logger.error(f"Error in main loop: {e}")
                await asyncio.sleep(5)

    async def _scan_and_trade(self):
        """Scan market và execute nếu có setup"""
        # Check số lượng position hiện tại
        current_positions = self._get_open_positions()
        available_slots = self.max_positions - len(current_positions)

        if available_slots <= 0:
            logger.debug("Max positions reached, skipping scan")
            return

        # Fetch market data
        market_data = await self._fetch_market_data()

        # Find setups
        setups = self.strategy.find_scalp_setups(market_data)

        if not setups:
            logger.debug("No valid setups found")
            return

        # Filter setups cho symbols chưa có position
        for setup in setups:
            if setup.symbol in current_positions:
                continue

            if available_slots <= 0:
                break

            # Execute trade
            await self._execute_trade(setup)
            available_slots -= 1

    def _get_open_positions(self) -> List[str]:
        """Lấy danh sách symbol đang có position"""
        try:
            positions = self.client.futures_position_information()
            open_positions = [
                p['symbol'] for p in positions
                if float(p['positionAmt']) != 0
            ]
            return open_positions
        except Exception as e:
            logger.error(f"Failed to get positions: {e}")
            return []

    async def _fetch_market_data(self) -> Dict:
        """Fetch real-time market data cho BTC, ETH, SOL"""
        symbols = ["BTCUSDT", "ETHUSDT", "SOLUSDT"]
        market_data = {}

        for symbol in symbols:
            try:
                # Current price
                ticker = self.client.futures_symbol_ticker(symbol=symbol)
                price = float(ticker['lastPrice'])

                # Recent candles M15
                klines_m15 = self.client.futures_klines(
                    symbol=symbol,
                    interval='15m',
                    limit=5
                )

                # Recent candles M5
                klines_m5 = self.client.futures_klines(
                    symbol=symbol,
                    interval='5m',
                    limit=5
                )

                # H1 trend (simplified)
                klines_h1 = self.client.futures_klines(
                    symbol=symbol,
                    interval='1h',
                    limit=10
                )

                h1_trend = self._calculate_trend(klines_h1)

                market_data[symbol] = {
                    "price": price,
                    "h1_trend": h1_trend,
                    "m15_candles": self._parse_klines(klines_m15),
                    "m5_candles": self._parse_klines(klines_m5)
                }

            except Exception as e:
                logger.error(f"Failed to fetch {symbol}: {e}")

        return market_data

    def _parse_klines(self, klines: List) -> List[Dict]:
        """Parse klines từ Binance format"""
        candles = []
        for k in klines:
            candles.append({
                "open": float(k[1]),
                "high": float(k[2]),
                "low": float(k[3]),
                "close": float(k[4]),
                "volume": float(k[5])
            })
        return candles

    def _calculate_trend(self, klines: List) -> str:
        """Tính trend đơn giản từ H1 candles"""
        if len(klines) < 5:
            return "neutral"

        closes = [float(k[4]) for k in klines]
        ema_fast = sum(closes[-5:]) / 5
        ema_slow = sum(closes[-10:]) / 10 if len(closes) >= 10 else ema_fast

        if ema_fast > ema_slow * 1.002:
            return "bullish"
        elif ema_fast < ema_slow * 0.998:
            return "bearish"
        return "neutral"

    async def _execute_trade(self, setup: ScalpSetup):
        """Execute trade với risk management"""
        try:
            # Get account balance
            account = self.client.futures_account()
            balance = float(account['availableBalance'])

            # Calculate position size
            position = self.strategy.calculate_position_size(setup, balance)

            logger.info(f"Executing {setup.direction.value} on {setup.symbol}")
            logger.info(f"Entry: {setup.entry}, SL: {setup.sl}")
            logger.info(f"Margin: {position.margin_required:.2f} USDT")
            logger.info(f"Max Loss: {position.max_loss_usd:.2f} USDT")

            # Execute
            result = self.executor.enter_position(setup, position)

            if "error" in result:
                logger.error(f"Trade failed: {result['error']}")
                return

            # Track position
            self.active_positions[setup.symbol] = {
                "setup": setup,
                "position": position,
                "entry_time": datetime.now(),
                "entry_order": result['entry_order']
            }

            logger.info(f"Trade executed successfully: {setup.symbol}")

        except Exception as e:
            logger.error(f"Failed to execute trade: {e}")

    async def _check_funding_time(self):
        """Close positions trước funding (8h UTC)"""
        now = datetime.utcnow()

        # Funding times: 00:00, 08:00, 16:00 UTC
        funding_hours = [0, 8, 16]
        next_funding = None

        for hour in funding_hours:
            funding_time = now.replace(hour=hour, minute=0, second=0, microsecond=0)
            if funding_time > now:
                next_funding = funding_time
                break

        if not next_funding:
            next_funding = now.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)

        # Close 5 phút trước funding
        time_to_funding = (next_funding - now).total