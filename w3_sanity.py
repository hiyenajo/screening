#!/usr/bin/env python3
"""
W3 — sanity check + 제외 조건 (거래량 = 평균 대비 비율 방식)
============================================================
W2 스크리닝 결과 '위에' 걸러내기 레이어를 얹는다.
목표: 후보를 많이 뽑는 게 아니라 '헛손질'을 줄이는 것.

제외 조건:
  1) 이미 보유 중      → positions.csv 대조
  2) 거래량 빈약       → 오늘 거래량 < 평균의 0.5배 (평소보다 거래가 죽음)
  3) 급등 추격 금지    → 전일 대비 +8% 이상
"""
import os
import csv
import json
import sys
from datetime import datetime

import requests
import yfinance as yf

# ── 설정 ─────────────────────────────────────────────────
WATCHLIST = ["NVDA", "TSLA", "LEU", "PLTR", "OKLO", "QCOM"]

BASE = os.path.dirname(os.path.abspath(__file__))
STATE_PATH = os.path.join(BASE, "state_w3.json")
POSITIONS_PATH = os.path.join(BASE, "positions.csv")

# ── 제외 조건 임계값 ─────────────────────────────────────
VOLUME_RATIO_MIN = 0.5       # 오늘 거래량이 평균의 이 배수 미만이면 '거래량 빈약'
CHASING_PCT = 8.0            # 전일 대비 +8% 이상이면 '추격 금지'


def passes(row: dict) -> bool:
    return row["rsi"] < 35 or abs(row["chg"]) >= 3.0


def load_positions(path: str) -> dict:
    positions = {}
    if not os.path.exists(path):
        print(f"[warn] positions.csv 없음 ({path}) — 보유 0개로 진행")
        return positions
    with open(path) as f:
        for r in csv.DictReader(f):
            sym = r["symbol"].strip().upper()
            positions[sym] = {"qty": float(r["qty"]), "avg_price": float(r["avg_price"])}
    return positions


def rsi(closes, period: int = 14) -> float:
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
    rows = []
    for symbol in WATCHLIST:
        try:
            hist = yf.Ticker(symbol).history(period="1mo")
            closes = hist["Close"].dropna().tolist()
            volumes = hist["Volume"].dropna().tolist()
            if len(closes) < 2 or len(volumes) < 2:
                print(f"[warn] 데이터 부족: {symbol}")
                continue
            price = float(closes[-1])
            prev_close = float(closes[-2])
            chg = (price - prev_close) / prev_close * 100

            today_vol = int(volumes[-1])                      # 오늘(최근) 거래량
            # 평균은 '오늘 제외한 과거' 기준 (오늘을 평균에 넣으면 자기 자신과 비교돼 왜곡)
            past_vols = volumes[:-1]
            avg_vol = int(sum(past_vols) / len(past_vols)) if past_vols else today_vol
            vol_ratio = round(today_vol / avg_vol, 2) if avg_vol else 0.0

            rows.append({
                "ticker": symbol,
                "price": round(price, 2),
                "chg": round(chg, 2),
                "rsi": round(rsi(closes), 1),
                "today_vol": today_vol,
                "avg_vol": avg_vol,
                "vol_ratio": vol_ratio,        # 오늘/평균 (1.0이면 평소만큼, 0.5면 절반)
            })
        except Exception as e:
            print(f"[warn] 수집 실패 {symbol}: {e}")
            continue
    return rows


def evaluate(row: dict, positions: dict):
    """반환: (상태문자열, 후보인가_bool, 보유인가_bool)"""
    symbol = row["ticker"]
    if symbol in positions:
        return "holding", False, True
    if row["vol_ratio"] < VOLUME_RATIO_MIN:        # 평소의 절반도 안 되면 제외
        return "low volume", False, False
    if row["chg"] >= CHASING_PCT:
        return "chasing", False, False
    return "candidate", True, False


def load_prev() -> set:
    if not os.path.exists(STATE_PATH):
        return set()
    try:
        with open(STATE_PATH) as f:
            return set(json.load(f))
    except (json.JSONDecodeError, ValueError):
        print("[warn] state_w3.json 손상 — 빈 상태로 처리")
        return set()


def save_state(tickers: set) -> None:
    with open(STATE_PATH, "w") as f:
        json.dump(sorted(tickers), f)


def build_message(results: list, new: set, gone: set) -> str:
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    lines = [f"{now}"]

    holdings = [(r, s) for r, s, c, h in results if h]
    if holdings:
        lines.append("\n💼 보유 중 (대조 완료)")
        for r, s in holdings:
            lines.append(f"  • {r['ticker']} | RSI {r['rsi']} | 등락 {r['chg']:+.2f}% | 보유중")

    excluded = [(r, s) for r, s, c, h in results if not c and not h]
    if excluded:
        lines.append("\n🚫 제외")
        reason_kr = {"low volume": "거래량 빈약", "chasing": "급등 추격"}
        for r, s in excluded:
            detail = ""
            if s == "low volume":
                detail = f" (평균 대비 {r['vol_ratio']}배)"
            lines.append(f"  • {r['ticker']} | {reason_kr.get(s, s)}{detail}")

    if new:
        lines.append("\n🆕 신규 후보")
        for r, s, c, h in results:
            if r["ticker"] in new:
                lines.append(f"  • {r['ticker']} | RSI {r['rsi']} | 등락 {r['chg']:+.2f}% | {r['price']} | 거래량 {r['vol_ratio']}배 | ✅")
    if gone:
        lines.append("\n👋 후보 이탈")
        for t in sorted(gone):
            lines.append(f"  • {t}")

    candidates = [(r, s) for r, s, c, h in results if c]
    lines.append(f"\n🎯 최종 후보 {len(candidates)}개")
    if candidates:
        for r, s in candidates:
            lines.append(f"  • {r['ticker']} | RSI {r['rsi']} | 등락 {r['chg']:+.2f}% | {r['price']}")
    else:
        lines.append("  • (없음 — 기준대로 걸렀으니 정상)")

    return "\n".join(lines)


def notify_slack(text: str) -> None:
    webhook = os.getenv("SLACK_WEBHOOK_URL", "")
    if not webhook:
        print("[info] 웹훅 없음 — 슬랙 스킵")
        return
    resp = requests.post(webhook, json={"text": text}, timeout=10)
    if resp.status_code == 200:
        print("[ok] 슬랙 전송")
    else:
        print(f"[err] 슬랙 실패 {resp.status_code}: {resp.text[:200]}")


def main() -> int:
    positions = load_positions(POSITIONS_PATH)
    screened = [r for r in collect() if passes(r)]

    results = []
    candidates = []
    for row in screened:
        status, is_candidate, is_holding = evaluate(row, positions)
        results.append((row, status, is_candidate, is_holding))
        if is_candidate:
            candidates.append(row["ticker"])

    cand_set = set(candidates)
    prev = load_prev()
    new = cand_set - prev
    gone = prev - cand_set
    save_state(cand_set)

    msg = build_message(results, new, gone)
    print(msg)

    if new or gone:
        notify_slack(msg)
    else:
        print("\n[quiet] 후보 변화 없음 — 슬랙 스킵")

    return 0


if __name__ == "__main__":
    sys.exit(main())
