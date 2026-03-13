# High Leverage Scalper Bot (50x)

Bot trading tự động cho Binance Futures với leverage 50x, optimized cho scalp strategy.

## ⚠️ Risk Warning

**Đây là high-risk trading. Chỉ dùng vốn bạn có thể mất hoàn toàn.**

- 50x leverage = 50x profit nhưng cũng 50x loss
- 0.3% move ngược = 15% loss trên margin
- 2% risk per trade = max loss 2% portfolio nếu SL hit

## 🎯 Chiến Lược

### Setup Types
1. **Rejection Setup**: Râu trên/dưới ở S/R + volume giảm
2. **Liquidity Sweep**: Phá schelling point rồi revert

### Entry Rules
- **Limit orders only** - Không market (slippage giết 50x)
- **Entry zone chặt** - Max 0.1% range
- **SL chặt** - Max 0.3% (15% loss on 50x)
- **Chờ confirm** - M15/M5 rejection pattern

### Exit Rules
- **TP1 (1.5R)**: Close 33%
- **TP2 (2.5R)**: Close 33%
- **TP3 (3.5R)**: Close 34%
- **SL**: Close 100%
- **Funding**: Close 5 phút trước 8h UTC

### Risk Management
| Parameter | Value |
|-----------|-------|
| Max Leverage | 50x |
| Max Risk/Trade | 2% portfolio |
| Max SL Distance | 0.3% |
| Max Positions | 2 |
| Margin Type | Isolated |

## 📁 Structure

```
trading_bot/
├── strategies/
│   └── high_lev_scalper.py    # Core strategy
├── runners/
│   └── scalper_runner.py      # Bot runner
├── config/
│   └── scalper_config.yaml    # Configuration
└── README_SCALPER.md          # This file
```

## 🚀 Setup

### 1. Environment Variables

```bash
export BINANCE_API_KEY="your_api_key"
export BINANCE_API_SECRET="your_api_secret"
```

### 2. Install Dependencies

```bash
pip install python-binance asyncio pyyaml
```

### 3. Test Mode (Paper Trading)

```python
# Trong scalper_runner.py, thay:
self.client = Client(self.api_key, self.api_secret, testnet=True)
```

### 4. Run Bot

```bash
cd trading_bot
python -m runners.scalper_runner
```

## 📊 Position Size Calculation

Ví dụ với portfolio $10,000:

```
Risk: 2% = $200
SL distance: 0.3%
Leverage: 50x

Position Size = $200 / (0.3% × 50)
              = $200 / 15%
              = $1,333

Margin Required = $1,333 / 50
                = $26.67

Max Loss = $200 (2% portfolio)
```

## 🎮 Example Trade

### SOL Short Setup

```
Price: $88.78
Resistance: $89.50 (schelling point)
Wick High: $90.20

Entry: $89.50
SL: $89.77 (0.3%)
TP1: $89.10 (1.5R)
TP2: $88.75 (2.5R)
TP3: $88.28 (3.5R)

Position: $1,333
Margin: $26.67
```

## ⚙️ Configuration

Edit `config/scalper_config.yaml`:

```yaml
risk_management:
  max_risk_per_trade: 2.0  # Thay đổi risk %
  max_positions: 2         # Số position tối đa

trading:
  scan_interval: 60        # Tần suất scan (giây)
  min_confidence: 0.65     # Ngưỡng confidence
```

## 📈 Monitoring

### Logs
```bash
tail -f logs/scalper.log
```

### Check Positions
```python
from binance.client import Client
client = Client(api_key, api_secret)
positions = client.futures_position_information()
for p in positions:
    if float(p['positionAmt']) != 0:
        print(f"{p['symbol']}: {p['positionAmt']} @ {p['entryPrice']}")
```

## 🚨 Safety Features

1. **Isolated Margin**: Loss giới hạn trong position
2. **Auto SL**: SL được attach ngay khi entry
3. **Funding Protection**: Auto close trước funding
4. **Max Positions**: Không over-trade
5. **Position Sizing**: Auto calculate theo risk

## 🔧 Troubleshooting

### "Failed to set leverage"
- Check API key có futures permission
- Đổi sang testnet để test

### "No valid setups found"
- Normal - chỉ vào khi có setup đẹp
- Check log để xem market data

### "Trade failed: margin insufficient"
- Giảm risk % hoặc tăng balance
- Check có position đang mở không

## 📚 References

- [Binance Futures API](https://binance-docs.github.io/apidocs/futures/en/)
- [Python-Binance](https://python-binance.readthedocs.io/)
- Original plan: `plan_short_h1.md`

## 📝 TODO

- [ ] Add backtesting module
- [ ] Add Telegram notifications
- [ ] Add liquidation heatmap integration
- [ ] Add funding rate filter
- [ ] Add correlation check

---

**Disclaimer**: Bot này được cung cấp "as-is". Bạn chịu trách nhiệm hoàn toàn cho các giao dịch của mình.
