#!/bin/bash
set -e

# 패키지 업데이트 및 Python 패키지 설치
dnf update -y
dnf install -y python3-pip

pip3 install --user yfinance requests

# 작업 디렉토리 생성
mkdir -p /home/ec2-user/screening-challenge

# w1_price.py 생성
cat > /home/ec2-user/screening-challenge/w1_price.py << 'PYEOF'
from datetime import datetime
import yfinance as yf
import os
import requests

DOMAIN = "US"
SYMBOL = "NVDA"

ticker = yf.Ticker(SYMBOL)
history = ticker.history(period="1d")

if history.empty:
    raise RuntimeError(f"price not found: {SYMBOL}")

price = float(history["Close"].iloc[-1])
now = datetime.now().strftime("%Y-%m-%d %H:%M")

message = f"""[S2 W1]
domain: {DOMAIN}
symbol: {SYMBOL}
price: {price:.2f}
time: {now}"""

print(message)

webhook_url = os.getenv("SLACK_WEBHOOK_URL", "${slack_webhook_url}")
if webhook_url:
    resp = requests.post(webhook_url, json={"text": message}, timeout=10)
    if resp.status_code == 200:
        print("Slack: sent")
    else:
        print(f"Slack: failed ({resp.status_code})")
PYEOF

chown -R ec2-user:ec2-user /home/ec2-user/screening-challenge
