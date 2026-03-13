#!/bin/bash
# Run Scalper API Server

cd "$(dirname "$0")"

export BINANCE_API_KEY="${BINANCE_API_KEY:-your_api_key}"
export BINANCE_API_SECRET="${BINANCE_API_SECRET:-your_api_secret}"
export PORT="${PORT:-5000}"

echo "Starting Scalper API Server..."
echo "Port: $PORT"
echo ""

python3 scalper_api.py