#!/bin/bash
# Deploy Scalper API to production

set -e

echo "🚀 Deploying Scalper API..."

# Check env vars
if [ -z "$BINANCE_API_KEY" ] || [ -z "$BINANCE_API_SECRET" ]; then
    echo "❌ Error: BINANCE_API_KEY and BINANCE_API_SECRET must be set"
    echo "Example:"
    echo "  export BINANCE_API_KEY=xxx"
    echo "  export BINANCE_API_SECRET=yyy"
    exit 1
fi

# Build and run
echo "📦 Building Docker image..."
docker-compose build

echo "🚀 Starting container..."
docker-compose up -d

echo "⏳ Waiting for API to start..."
sleep 5

# Health check
echo "🏥 Health check..."
if curl -s http://localhost:5000/health | grep -q "ok"; then
    echo "✅ API is running!"
    echo ""
    echo "📡 API Endpoints:"
    echo "  - Health: http://localhost:5000/health"
    echo "  - Risk:   http://localhost:5000/api/risk"
    echo "  - Positions: http://localhost:5000/api/positions"
    echo "  - Scanner: http://localhost:5000/api/scanner"
    echo ""
    echo "🌐 Update UI to use: http://your-server-ip:5000"
else
    echo "❌ API failed to start"
    docker-compose logs
    exit 1
fi