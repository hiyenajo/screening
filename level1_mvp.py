#!/usr/bin/env python3
"""
Level 1 — 동작하는 MVP (W2 미션 통과)
조건 필터 + 어제와 비교(state) + 변화만 슬랙 알림.

W2 미션이 요구하는 두 레이어:
  1) 조건(condition): 언제 울릴지 = passes()
  2) 상태(state)    : 어제 뭐였는지 기억하고 비교 = state.json

핵심: 변화가 없으면 슬랙 안 보냄. 그게 정상.
"""
import os
import json
import sys
from datetime import datetime

import requests
import yfinance as yf

# ── 설정 ────────────────────────────────────────────────
# 본인이 감시할 종목 (US 예시). 한국 종목은 "005930.KS" 형식.
WATCHLIST = ["NVDA", "TSLA", "LEU", "OKLO", "QCOM"]

# state.json은 반드시 "절대경로"로. cron은 작업 디렉토리가 달라서
# 상대경로 쓰면 매일 다 신규로 떠버림 (미션 함정 1번).
STATE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "state.json")

SLACK_WEBHOOK_URL = os.getenv("SLACK_WEBHOOK_URL", "")


# ── 본인 조건 (여기를 바꾸세요) ──────────────────────────
def passes(row: dict) -> bool:
    """
    True면 '조건 충족'. 본인 투자 기준으로 바꾸세요.
    예: RSI 35 미만 이거나, 하루 등락 3% 이상.
    (미션 함정 3번: 너무 빡세면 매일 0 → 기준 완화 RSI 30->35, 등락 5->3)
    """
    return row["rsi"] < 35 or abs(row["chg"]) >= 3.0


# ── 데이터 수집 ──────────────────────────────────────────
def rsi(closes, period: int = 14) -> float:
    """간단 RSI. 데이터 부족하면 50(중립) 반환."""
    if len(closes) < period + 1:
        return 50.0
    gains, losses = [], []
    for i in range(1, len(closes)):
        diff = closes[i] - closes[i - 1]
        gains.append(max(diff, 0))
        losses.append(max(-diff, 0))
    avg_gain = sum(gains[-period:]) / period
    avg_loss = sum(losses[-period:]) / period
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


def collect() -> list:
    """워치리스트 각 종목의 가격/등락/RSI 수집."""
    rows = []
    for symbol in WATCHLIST:
        try:
            hist = yf.Ticker(symbol).history(period="1mo")
            if hist.empty or len(hist) < 2:
                print(f"[warn] no data: {symbol}")
                continue
#            closes = hist["Close"].tolist()
            closes = hist["Close"].dropna().tolist()
            price = float(closes[-1])
            prev_close = float(closes[-2])
            chg = (price - prev_close) / prev_close * 100
            rows.append({
                "ticker": symbol,
                "price": round(price, 2),
                "chg": round(chg, 2),
                "rsi": round(rsi(closes), 1),
            })
        except Exception as e:
            # 한 종목 실패가 전체를 죽이면 안 됨 (부분 실패 허용)
            print(f"[warn] collect failed {symbol}: {e}")
            continue
    return rows


# ── 상태 비교 (멱등성의 핵심) ────────────────────────────
def load_prev() -> set:
    if os.path.exists(STATE_PATH):
        try:
            with open(STATE_PATH) as f:
                return set(json.load(f))
        except (json.JSONDecodeError, ValueError):
            print("[warn] state.json corrupted, treating as empty")
            return set()
    return set()


def save_state(tickers: set) -> None:
    with open(STATE_PATH, "w") as f:
        json.dump(sorted(tickers), f)


# ── 메시지 ───────────────────────────────────────────────
def build_msg(new: set, gone: set, hits: list) -> str:
    by_ticker = {r["ticker"]: r for r in hits}
    lines = [f"{datetime.now():%Y-%m-%d %H:%M}"]
    if new:
        lines.append("🆕 신규:")
        for t in sorted(new):
            r = by_ticker.get(t, {})
            lines.append(f"  • {t} 등락 {r.get('chg','?')}% / RSI {r.get('rsi','?')}")
    if gone:
        lines.append("👋 이탈: " + ", ".join(sorted(gone)))
    return "\n".join(lines)


def notify_slack(text: str) -> None:
    webhook = os.getenv("SLACK_WEBHOOK_URL", "")  # 매번 새로 읽기
    if not webhook:
        print("[info] no webhook set, skipping slack")
        return
    resp = requests.post(webhook, json={"text": text}, timeout=10)
    if resp.status_code == 200:
        print("[ok] slack sent")
    else:
        print(f"[err] slack failed {resp.status_code}")


# ── 메인 ─────────────────────────────────────────────────
def main() -> int:
    hits = [r for r in collect() if passes(r)]
    now = {r["ticker"] for r in hits}
    prev = load_prev()

    new = now - prev    # 어제 없던 신규
    gone = prev - now   # 어제 있다 빠진 것

    save_state(now)     # 상태 갱신은 항상 (비교 끝난 뒤)

    if not new and not gone:
        print(f"[quiet] 조건 충족 {len(now)}개, 변화 없음 — 조용히 넘어감")
        return 0

    msg = build_msg(new, gone, hits)
    print(msg)
    notify_slack(msg)
    return 0


if __name__ == "__main__":
    sys.exit(main())

