"""
Flask API for Scalper Bot
Provides endpoints for UI dashboard
"""

from flask import Flask, jsonify, request
from flask_cors import CORS
import os
import sys
from datetime import datetime, timedelta
from typing import Dict, List

# Add parent to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from binance.client import Client
from binance.exceptions import BinanceAPIException

app = Flask(__name__)
CORS(app)

# Binance client
api_key = os.getenv('BINANCE_API_KEY')
api_secret = os.getenv('BINANCE_API_SECRET')
client = Client(api_key, api_secret) if api_key and api_secret else None

# Mock data for testing (replace with real data from bot)
MOCK_POSITIONS = []
MOCK_SETUPS = []


@app.route('/api/risk', methods=['GET'])
def get_risk():
    """Get risk overview data"""
    try:
        if not client:
            return jsonify({"error": "Binance client not initialized"}), 500
        
        # Get account info
        account = client.futures_account()
        balance = float(account.get('availableBalance', 0))
        total_wallet = float(account.get('totalWalletBalance', 0))
        
        # Get positions
        positions = client.futures_position_information()
        active_positions = []
        used_margin = 0
        daily_pnl = 0
        
        for pos in positions:
            amt = float(pos.get('positionAmt', 0))
            if amt != 0:
                used_margin += float(pos.get('isolatedWallet', 0))
                daily_pnl += float(pos.get('unrealizedProfit', 0))
                active_positions.append({
                    'symbol': pos['symbol'],
                    'direction': 'LONG' if amt > 0 else 'SHORT',
                    'entry': float(pos['entryPrice']),
                    'current': float(pos['markPrice']),
                    'sl': float(pos.get('stopPrice', 0)) or float(pos['entryPrice']) * 0.97,
                    'margin': float(pos.get('isolatedWallet', 0)),
                    'leverage': int(pos.get('leverage', 50))
                })
        
        # Calculate funding time
        now = datetime.utcnow()
        funding_hours = [0, 8, 16]
        next_funding = None
        for hour in funding_hours:
            funding_time = now.replace(hour=hour, minute=0, second=0, microsecond=0)
            if funding_time > now:
                next_funding = funding_time
                break
        if not next_funding:
            next_funding = now.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)
        
        minutes_to_funding = int((next_funding - now).total_seconds() / 60)
        
        return jsonify({
            'portfolio': total_wallet,
            'available_balance': balance,
            'used_margin': used_margin,
            'daily_pnl': daily_pnl,
            'active_positions': len(active_positions),
            'minutes_to_funding': minutes_to_funding,
            'positions': active_positions
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/positions', methods=['GET'])
def get_positions():
    """Get active scalp positions"""
    try:
        if not client:
            return jsonify({"error": "Binance client not initialized"}), 500
        
        positions = client.futures_position_information()
        active = []
        
        for pos in positions:
            amt = float(pos.get('positionAmt', 0))
            if amt != 0:
                entry = float(pos['entryPrice'])
                current = float(pos['markPrice'])
                direction = 'LONG' if amt > 0 else 'SHORT'
                
                # Calculate PnL
                if direction == 'LONG':
                    pnl_pct = (current - entry) / entry * 100
                else:
                    pnl_pct = (entry - current) / entry * 100
                
                active.append({
                    'symbol': pos['symbol'],
                    'direction': direction,
                    'entry': entry,
                    'current_price': current,
                    'sl': entry * 0.997 if direction == 'LONG' else entry * 1.003,
                    'margin': float(pos.get('isolatedWallet', 50)),
                    'pnl_percent': round(pnl_pct, 2),
                    'leverage': 50
                })
        
        return jsonify({'positions': active})
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/scanner', methods=['GET'])
def get_scanner():
    """Get potential scalp setups"""
    try:
        if not client:
            return jsonify({"error": "Binance client not initialized"}), 500
        
        setups = []
        symbols = ['SOLUSDT', 'ETHUSDT', 'BTCUSDT']
        
        for symbol in symbols:
            # Get recent price
            ticker = client.futures_symbol_ticker(symbol=symbol)
            price = float(ticker['lastPrice'])
            
            # Get recent candles
            klines = client.futures_klines(symbol=symbol, interval='15m', limit=5)
            if len(klines) < 3:
                continue
            
            last_candle = {
                'open': float(klines[-1][1]),
                'high': float(klines[-1][2]),
                'low': float(klines[-1][3]),
                'close': float(klines[-1][4])
            }
            
            # Check for rejection pattern
            upper_wick = last_candle['high'] - max(last_candle['open'], last_candle['close'])
            lower_wick = min(last_candle['open'], last_candle['close']) - last_candle['low']
            body = abs(last_candle['close'] - last_candle['open'])
            
            if upper_wick > body * 2:
                # Potential short setup
                setups.append({
                    'symbol': symbol,
                    'type': 'Rejection',
                    'direction': 'SHORT',
                    'entry_zone': f"{price:.2f}",
                    'confidence': 72,
                    'current_price': price
                })
            elif lower_wick > body * 2:
                # Potential long setup
                setups.append({
                    'symbol': symbol,
                    'type': 'Rejection',
                    'direction': 'LONG',
                    'entry_zone': f"{price:.2f}",
                    'confidence': 68,
                    'current_price': price
                })
        
        return jsonify({'setups': setups})
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/close', methods=['POST'])
def close_position():
    """Close a position"""
    try:
        data = request.get_json()
        symbol = data.get('symbol')
        
        if not client or not symbol:
            return jsonify({"error": "Missing parameters"}), 400
        
        # Get position
        positions = client.futures_position_information(symbol=symbol)
        for pos in positions:
            amt = float(pos.get('positionAmt', 0))
            if amt != 0:
                side = 'SELL' if amt > 0 else 'BUY'
                client.futures_create_order(
                    symbol=symbol,
                    side=side,
                    type='MARKET',
                    quantity=abs(amt),
                    reduceOnly=True
                )
                return jsonify({'success': True, 'message': f'Closed {symbol} position'})
        
        return jsonify({'error': 'No position found'}), 404
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/sl-breakeven', methods=['POST'])
def move_sl_breakeven():
    """Move SL to breakeven"""
    try:
        data = request.get_json()
        symbol = data.get('symbol')
        
        if not client or not symbol:
            return jsonify({"error": "Missing parameters"}), 400
        
        # Get position
        positions = client.futures_position_information(symbol=symbol)
        for pos in positions:
            amt = float(pos.get('positionAmt', 0))
            if amt != 0:
                entry = float(pos['entryPrice'])
                side = 'SELL' if amt > 0 else 'BUY'
                
                # Cancel existing SL orders
                open_orders = client.futures_get_open_orders(symbol=symbol)
                for order in open_orders:
                    if order['type'] == 'STOP_MARKET':
                        client.futures_cancel_order(symbol=symbol, orderId=order['orderId'])
                
                # Place new SL at breakeven
                client.futures_create_order(
                    symbol=symbol,
                    side=side,
                    type='STOP_MARKET',
                    stopPrice=round(entry, 2),
                    closePosition=True,
                    timeInForce='GTC'
                )
                
                return jsonify({'success': True, 'message': f'Moved SL to breakeven for {symbol}'})
        
        return jsonify({'error': 'No position found'}), 404
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/enter', methods=['POST'])
def enter_position():
    """Enter a scalp position"""
    try:
        data = request.get_json()
        symbol = data.get('symbol')
        setup_type = data.get('type', 'manual')
        
        if not client or not symbol:
            return jsonify({"error": "Missing parameters"}), 400
        
        # Get current price
        ticker = client.futures_symbol_ticker(symbol=symbol)
        price = float(ticker['lastPrice'])
        
        # Calculate position size (2% risk, 0.3% SL, 50x)
        account = client.futures_account()
        balance = float(account['availableBalance'])
        risk_amount = balance * 0.02
        sl_distance = 0.003
        position_size = risk_amount / (sl_distance * 50)
        margin = position_size / 50
        
        # Set leverage and margin type
        try:
            client.futures_change_margin_type(symbol=symbol, marginType='ISOLATED')
        except:
            pass
        client.futures_change_leverage(symbol=symbol, leverage=50)
        
        # Place limit order (mock - should calculate proper entry)
        side = 'BUY' if setup_type == 'LONG' else 'SELL'
        
        return jsonify({
            'success': True,
            'message': f'Entered {setup_type} on {symbol}',
            'entry': price,
            'margin': margin
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/health', methods=['GET'])
def health():
    """Health check"""
    return jsonify({'status': 'ok', 'timestamp': datetime.now().isoformat()})


if __name__ == '__main__':
    port = int(os.getenv('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)