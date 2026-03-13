"""
High Leverage Scalper Strategy (50x)
Optimized for Binance Futures Isolated Margin
"""

from dataclasses import dataclass
from typing import Optional, Dict, List
from enum import Enum
import logging

logger = logging.getLogger(__name__)


class TradeDirection(Enum):
    LONG = "LONG"
    SHORT = "SHORT"


@dataclass
class ScalpSetup:
    """Setup cho 1 lệnh scalp 50x"""
    symbol: str
    direction: TradeDirection
    entry: float
    sl: float
    tp1: float
    tp2: float
    tp3: float
    confidence: float  # 0.0 - 1.0
    timeframe: str  # M5, M15
    setup_type: str  # "rejection", "breakout", "liquidity_sweep"


@dataclass
class PositionSize:
    """Thông tin position size đã tính toán"""
    position_size_usd: float
    margin_required: float
    max_loss_usd: float
    risk_percent: float
    quantity: float  # Số coin


class HighLevScalper:
    """
    Chiến lược scalp 50x cho Binance Futures
    - Max risk: 2% portfolio per trade
    - Max SL distance: 0.3%
    - Entry: Limit orders only
    - Time in trade: 5-60 minutes
    """

    LEVERAGE = 50
    MAX_RISK_PERCENT = 2.0
    MAX_SL_DISTANCE = 0.003  # 0.3%
    MIN_CONFIDENCE = 0.65

    # Schelling Points - vùng giá key
    SCALPING_LEVELS = {
        "BTC": [1000, 500, 100],  # Round numbers
        "ETH": [50, 25, 10],
        "SOL": [5, 2, 1]
    }

    def __init__(self, binance_client):
        self.client = binance_client
        self.active_setups: List[ScalpSetup] = []

    def find_scalp_setups(self, market_data: Dict) -> List[ScalpSetup]:
        """
        Tìm setup scalp từ market data
        Ưu tiên: SOL > ETH > BTC
        """
        setups = []
        priority = ["SOLUSDT", "ETHUSDT", "BTCUSDT"]

        for symbol in priority:
            if symbol not in market_data:
                continue

            data = market_data[symbol]

            # Check rejection setup
            rejection = self._check_rejection_setup(symbol, data)
            if rejection and rejection.confidence >= self.MIN_CONFIDENCE:
                setups.append(rejection)
                continue

            # Check liquidity sweep
            sweep = self._check_liquidity_sweep(symbol, data)
            if sweep and sweep.confidence >= self.MIN_CONFIDENCE:
                setups.append(sweep)

        # Sắp xếp theo confidence
        setups.sort(key=lambda x: x.confidence, reverse=True)
        return setups[:2]  # Max 2 positions cùng lúc

    def _check_rejection_setup(self, symbol: str, data: Dict) -> Optional[ScalpSetup]:
        """
        Check setup rejection ở kháng cự/hỗ trợ
        - M15/M5 râu trên/dưới
        - Volume giảm
        - RSI không extreme
        """
        current_price = data.get("price", 0)
        h1_trend = data.get("h1_trend", "neutral")
        m15_candles = data.get("m15_candles", [])

        if len(m15_candles) < 3:
            return None

        last_candle = m15_candles[-1]
        high = last_candle.get("high", 0)
        low = last_candle.get("low", 0)
        open_p = last_candle.get("open", 0)
        close = last_candle.get("close", 0)
        volume = last_candle.get("volume", 0)
        avg_volume = sum(c.get("volume", 0) for c in m15_candles[-5:]) / 5

        # SHORT setup: râu trên ở kháng cự
        if h1_trend in ["bearish", "neutral"]:
            upper_wick = high - max(open_p, close)
            body = abs(close - open_p)

            # Râu trên > 2x body + volume giảm
            if upper_wick > body * 2 and volume < avg_volume * 0.8:
                resistance = self._find_nearest_resistance(symbol, current_price)
                if resistance and abs(high - resistance) / resistance < 0.001:
                    return self._build_short_setup(symbol, resistance, high)

        # LONG setup: râu dưới ở hỗ trợ
        if h1_trend in ["bullish", "neutral"]:
            lower_wick = min(open_p, close) - low
            body = abs(close - open_p)

            if lower_wick > body * 2 and volume < avg_volume * 0.8:
                support = self._find_nearest_support(symbol, current_price)
                if support and abs(low - support) / support < 0.001:
                    return self._build_long_setup(symbol, support, low)

        return None

    def _check_liquidity_sweep(self, symbol: str, data: Dict) -> Optional[ScalpSetup]:
        """
        Check liquidity sweep setup
        - Giá sweep liquidity rồi revert nhanh
        - Thường xảy ra ở round numbers
        """
        current_price = data.get("price", 0)
        m5_candles = data.get("m5_candles", [])

        if len(m5_candles) < 5:
            return None

        # Tìm schelling point gần nhất
        schelling = self._find_schelling_point(symbol, current_price)
        if not schelling:
            return None

        # Check sweep pattern
        recent_low = min(c.get("low", float('inf')) for c in m5_candles[-3:])
        recent_high = max(c.get("high", 0) for c in m5_candles[-3:])

        # Short sweep: phá trên schelling rồi revert
        if recent_high > schelling * 1.002 and current_price < schelling:
            return self._build_short_setup(symbol, schelling, recent_high)

        # Long sweep: phá dưới schelling rồi revert
        if recent_low < schelling * 0.998 and current_price > schelling:
            return self._build_long_setup(symbol, schelling, recent_low)

        return None

    def _build_short_setup(self, symbol: str, resistance: float, wick_high: float) -> ScalpSetup:
        """Build short setup từ resistance và wick high"""
        entry = resistance
        sl = min(wick_high * 1.001, resistance * 1.003)  # Max 0.3%
        distance = (sl - entry) / entry

        # TP levels: 1:1.5, 1:2.5, 1:3.5 R:R
        tp1 = entry * (1 - distance * 1.5)
        tp2 = entry * (1 - distance * 2.5)
        tp3 = entry * (1 - distance * 3.5)

        return ScalpSetup(
            symbol=symbol,
            direction=TradeDirection.SHORT,
            entry=entry,
            sl=sl,
            tp1=tp1,
            tp2=tp2,
            tp3=tp3,
            confidence=0.7,
            timeframe="M15",
            setup_type="rejection"
        )

    def _build_long_setup(self, symbol: str, support: float, wick_low: float) -> ScalpSetup:
        """Build long setup từ support và wick low"""
        entry = support
        sl = max(wick_low * 0.999, support * 0.997)  # Max 0.3%
        distance = (entry - sl) / entry

        tp1 = entry * (1 + distance * 1.5)
        tp2 = entry * (1 + distance * 2.5)
        tp3 = entry * (1 + distance * 3.5)

        return ScalpSetup(
            symbol=symbol,
            direction=TradeDirection.LONG,
            entry=entry,
            sl=sl,
            tp1=tp1,
            tp2=tp2,
            tp3=tp3,
            confidence=0.7,
            timeframe="M15",
            setup_type="rejection"
        )

    def calculate_position_size(self, setup: ScalpSetup, portfolio_value: float) -> PositionSize:
        """
        Tính position size cho 50x leverage
        Risk = 2% portfolio max
        """
        sl_distance = abs(setup.sl - setup.entry) / setup.entry

        # Đảm bảo SL distance hợp lệ
        if sl_distance > self.MAX_SL_DISTANCE:
            logger.warning(f"SL distance {sl_distance:.4f} > max {self.MAX_SL_DISTANCE}")
            # Adjust SL
            if setup.direction == TradeDirection.SHORT:
                setup.sl = setup.entry * (1 + self.MAX_SL_DISTANCE)
            else:
                setup.sl = setup.entry * (1 - self.MAX_SL_DISTANCE)
            sl_distance = self.MAX_SL_DISTANCE

        # Risk amount
        max_loss_usd = portfolio_value * (self.MAX_RISK_PERCENT / 100)

        # Position size = Risk / (SL% × Leverage)
        # Ví dụ: SL 0.3%, leverage 50x → risk per position = 15%
        position_size_usd = max_loss_usd / (sl_distance * self.LEVERAGE)
        margin_required = position_size_usd / self.LEVERAGE

        # Round quantity theo precision của symbol
        quantity = self._round_quantity(setup.symbol, position_size_usd / setup.entry)

        return PositionSize(
            position_size_usd=position_size_usd,
            margin_required=margin_required,
            max_loss_usd=max_loss_usd,
            risk_percent=self.MAX_RISK_PERCENT,
            quantity=quantity
        )

    def _round_quantity(self, symbol: str, quantity: float) -> float:
        """Round quantity theo precision của Binance"""
        precision_map = {
            "BTCUSDT": 3,
            "ETHUSDT": 3,
            "SOLUSDT": 2
        }
        precision = precision_map.get(symbol, 3)
        return round(quantity, precision)

    def _find_nearest_resistance(self, symbol: str, price: float) -> Optional[float]:
        """Tìm kháng cự gần nhất từ market structure"""
        # TODO: Implement với real S/R data
        # Tạm thời: round lên mức 0.5% hoặc schelling point
        base = self._get_base_asset(symbol)
        levels = self.SCALPING_LEVELS.get(base, [1])

        for level in sorted(levels, reverse=True):
            rounded = round(price / level) * level
            if rounded > price:
                return rounded
        return price * 1.005

    def _find_nearest_support(self, symbol: str, price: float) -> Optional[float]:
        """Tìm hỗ trợ gần nhất từ market structure"""
        base = self._get_base_asset(symbol)
        levels = self.SCALPING_LEVELS.get(base, [1])

        for level in sorted(levels, reverse=True):
            rounded = round(price / level) * level
            if rounded < price:
                return rounded
        return price * 0.995

    def _find_schelling_point(self, symbol: str, price: float) -> Optional[float]:
        """Tìm schelling point (round number) gần nhất"""
        base = self._get_base_asset(symbol)
        levels = self.SCALPING_LEVELS.get(base, [1])

        # Tìm round number gần nhất
        for level in sorted(levels, reverse=True):
            rounded = round(price / level) * level
            if abs(price - rounded) / price < 0.01:  # Within 1%
                return rounded
        return None

    def _get_base_asset(self, symbol: str) -> str:
        """Extract base asset từ symbol"""
        return symbol.replace("USDT", "")


class BinanceFuturesExecutor:
    """
    Executor cho Binance Futures
    Handle leverage, margin type, order placement
    """

    def __init__(self, client):
        self.client = client
        self.leverage_set = {}

    def prepare_symbol(self, symbol: str, leverage: int = 50):
        """Set leverage và margin type cho symbol"""
        if symbol in self.leverage_set and self.leverage_set[symbol] == leverage:
            return True

        try:
            # Set isolated margin
            self.client.futures_change_margin_type(
                symbol=symbol,
                marginType='ISOLATED'
            )
        except Exception as e:
            # Có thể đã là ISOLATED rồi
            logger.debug(f"Margin type might already be ISOLATED: {e}")

        try:
            # Set leverage
            self.client.futures_change_leverage(
                symbol=symbol,
                leverage=leverage
            )
            self.leverage_set[symbol] = leverage
            logger.info(f"Set {symbol} to {leverage}x isolated")
            return True
        except Exception as e:
            logger.error(f"Failed to set leverage for {symbol}: {e}")
            return False

    def enter_position(self, setup: ScalpSetup, position: PositionSize) -> Dict:
        """
        Vào lệnh với limit order
        Trả về order info
        """
        symbol = setup.symbol

        # Prepare symbol
        if not self.prepare_symbol(symbol, 50):
            return {"error": "Failed to prepare symbol"}

        side = "SELL" if setup.direction == TradeDirection.SHORT else "BUY"

        try:
            # Entry limit order
            entry_order = self.client.futures_create_order(
                symbol=symbol,
                side=side,
                type='LIMIT',
                quantity=position.quantity,
                price=round(setup.entry, 2),
                timeInForce='GTC',
                reduceOnly=False
            )

            logger.info(f"Entry order placed: {symbol} {side} @ {setup.entry}")

            # Attach SL/TP bracket
            self._attach_bracket_orders(setup, position, entry_order['orderId'])

            return {
                "entry_order": entry_order,
                "setup": setup,
                "position": position
            }

        except Exception as e:
            logger.error(f"Failed to enter position: {e}")
            return {"error": str(e)}

    def _attach_bracket_orders(self, setup: ScalpSetup, position: PositionSize, parent_order_id: str):
        """Attach SL và TP orders"""
        symbol = setup.symbol

        # SL order (STOP_MARKET)
        sl_side = "BUY" if setup.direction == TradeDirection.SHORT else "SELL"

        try:
            sl_order = self.client.futures_create_order(
                symbol=symbol,
                side=sl_side,
                type='STOP_MARKET',
                stopPrice=round(setup.sl, 2),
                closePosition=True,
                timeInForce='GTC'
            )
            logger.info(f"SL order placed: {symbol} @ {setup.sl}")
        except Exception as e:
            logger.error(f"Failed to place SL: {e}")

        # TP orders (TAKE_PROFIT_MARKET) - TP1, TP2, TP3
        tp_levels = [setup.tp1, setup.tp2, setup.tp3]
        for i, tp in enumerate(tp_levels, 1):
            try:
                tp_order = self.client.futures_create_order(
                    symbol=symbol,
                    side=sl_side,
                    type='TAKE_PROFIT_MARKET',
                    stopPrice=round(tp, 2),
                    quantity=round(position.quantity / 3, 3),  # Chia 3 phần
                    timeInForce='GTC'
                )
                logger.info(f"TP{i} order placed: {symbol} @ {tp}")
            except Exception as e:
                logger.error(f"Failed to place TP{i}: {e}")

    def close_position(self, symbol: str):
        """Close position immediately"""
        try:
            # Get position
            positions = self.client.futures_position_information(symbol=symbol)
            for pos in positions:
                if float(pos['positionAmt']) != 0:
                    side = "SELL" if float(pos['positionAmt']) > 0 else "BUY"
                    self.client.futures_create_order(
                        symbol=symbol,
                        side=side,
                        type='MARKET',
                        quantity=abs(float(pos['positionAmt'])),
                        reduceOnly=True
                    )
                    logger.info(f"Closed position: {symbol}")
        except Exception as e:
            logger.error(f"Failed to close position: {e}")


# Example usage
if __name__ == "__main__":
    # Mock data
    market_data = {
        "SOLUSDT": {
            "price": 88.78,
            "h1_trend": "bearish",
            "m15_candles": [
                {"open": 89.0, "high": 90.2, "low": 88.5, "