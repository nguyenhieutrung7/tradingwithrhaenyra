FROM python:3.11-slim

WORKDIR /app

# Install dependencies
RUN pip install --no-cache-dir flask flask-cors python-binance gunicorn

# Copy API code
COPY scalper_api.py .
COPY run_api.sh .

# Make script executable
RUN chmod +x run_api.sh

# Expose port
EXPOSE 5000

# Run with gunicorn for production
CMD ["gunicorn", "-w", "4", "-b", "0.0.0.0:5000", "scalper_api:app"]