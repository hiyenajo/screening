from datetime import datetime
import yfinance as yf
import os
import requests

DOMAIN = "US"
SYMBOL = "LEU"

ticker = yf.Ticker(SYMBOL)
history = ticker.history(period="1d")

if history.empty:
    raise RuntimeError(f"price not found: {SYMBOL}")

price = float(history["Close"].iloc[-1])
now = datetime.now().strftime("%Y-%m-%d %H:%M")

message = f"""[💡Screening]
domain: {DOMAIN}
symbol: {SYMBOL}
price: {price:.2f}
time: {now}"""

print(message)

webhook_url = os.getenv("SLACK_WEBHOOK_URL", "")
if webhook_url:
    resp = requests.post(webhook_url, json={"text": message}, timeout=10)
    if resp.status_code == 200:
        print("Slack: sent")
    else:
        print(f"Slack: failed ({resp.status_code})")
