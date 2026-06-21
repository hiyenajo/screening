#!/usr/bin/env python3
"""
W3 — sanity check + 제외 조건 (+ MACD 추세 필터)
==================================================
W2 스크리닝 결과 '위에' 걸러내기 레이어를 얹어 헛손질을 줄인다.

제외 조건 (순서대로, 하나라도 걸리면 그 자리에서 제외):
  1) 이미 보유 중      → positions.csv 대조
  2) 거래량 빈약       → 오늘 거래량 < 평균의 0.5배 (사고팔기 어려움)
  3) 추세 악화         → MACD 히스토그램이 음수이면서 더 나빠지는 중 (떨어지는 칼날)
  4) 급등 추격 금지    → 전일 대비 +8% 이상 (고점 추격 위험)

지표(RSI/MACD)는 indicators.py에 분리해 단위 테스트로 검증한다.
"""
import os
import csv
import json
import sys
from datetime import datetime

import requests
import yfinance as yf

import indicators as ind   # 같은 폴더의 검증된 지표 모듈

# ── 설정 ─────────────────────────────────────────────────
WATCHLIST = ["NVDA", "TSLA", "QCOM", "MSFT", "MU", "SPCX", "LEU", "PLTR"]

BASE = os.path.dirname(os.path.abspath(__file__))
STATE_PATH = os.path.join(BASE, "state_w3.json")
POSITIONS_PATH = os.path.join(BASE, "positions.csv")

# MACD는 최소 35봉 필요 → 넉넉히 6개월치를 받는다 (1mo로는 계산 불가/부정확)
HISTORY_PERIOD = "6mo"

# ── 제외 조건 임계값 ─────────────────────────────────────
RSI_MAX = 35                 # 1차 스크리닝: RSI 이 값 미만이면 통과
CHG_MIN = 3.0                # 1차 스크리닝: |등락| 이 값 이상이면 통과
VOLUME_RATIO_MIN = 0.5       # 오늘 거래량이 평균의 이 배수 미만이면 제외
CHASING_PCT = 8.0            # 전일 대비 +이 % 이상이면 추격 금지


def passes(row: dict) -> bool:
    """1차 스크리닝: RSI 과매도 또는 큰 등락."""
    return row["rsi"] < RSI_MAX or abs(row["chg"]) >= CHG_MIN


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


def collect() -> list:
    rows = []
    for symbol in WATCHLIST:
        try:
            hist = yf.Ticker(symbol).history(period=HISTORY_PERIOD)
            closes = hist["Close"].dropna().tolist()
            volumes = hist["Volume"].dropna().tolist()
            if len(closes) < 2 or len(volumes) < 2:
                print(f"[warn] 데이터 부족: {symbol}")
                continue

            price = float(closes[-1])
            prev_close = float(closes[-2])
            chg = (price - prev_close) / prev_close * 100

            today_vol = int(volumes[-1])
            past_vols = volumes[:-1]   # 오늘 제외한 과거 평균 (오늘을 평균에 넣으면 왜곡)
            avg_vol = int(sum(past_vols) / len(past_vols)) if past_vols else today_vol
            vol_ratio = round(today_vol / avg_vol, 2) if avg_vol else 0.0

            # 지표 (검증된 모듈 사용)
            rsi_val = ind.rsi(closes)
            if rsi_val is None:
                print(f"[warn] RSI 계산 불가(데이터 부족): {symbol}")
                continue

            _, _, hist_line = ind.macd(closes)
            if hist_line is not None:
                valid_h = [h for h in hist_line if h is not None]
                macd_hist = round(valid_h[-1], 3) if valid_h else None
                macd_hist_prev = round(valid_h[-2], 3) if len(valid_h) >= 2 else None
            else:
                macd_hist = macd_hist_prev = None   # 데이터 부족 시 추세 필터는 건너뜀

            rows.append({
                "ticker": symbol,
                "price": round(price, 2),
                "chg": round(chg, 2),
                "rsi": round(rsi_val, 1),
                "today_vol": today_vol,
                "avg_vol": avg_vol,
                "vol_ratio": vol_ratio,
                "macd_hist": macd_hist,
                "macd_hist_prev": macd_hist_prev,
            })
        except Exception as e:
            print(f"[warn] 수집 실패 {symbol}: {e}")
            continue
    return rows


def macd_arrow(row: dict) -> str:
    """히스토그램 부호+방향을 화살표로. 표시용."""
    h, p = row["macd_hist"], row["macd_hist_prev"]
    if h is None:
        return "MACD n/a"
    if p is None:
        return f"MACD {h:+.2f}"
    rising = h > p
    if h > 0:
        return f"MACD {h:+.2f} {'↑' if rising else '→'}"   # 양수
    return f"MACD {h:+.2f} {'↗(전환)' if rising else '↓'}"   # 음수


def evaluate(row: dict, positions: dict):
    """
    반환: (상태문자열, 후보인가_bool, 보유인가_bool)
    순서대로 심사, 하나라도 걸리면 즉시 제외.
    """
    symbol = row["ticker"]

    # 1. 보유 대조
    if symbol in positions:
        return "holding", False, True

    # 2. 거래량 빈약
    if row["vol_ratio"] < VOLUME_RATIO_MIN:
        return "low volume", False, False

    # 3. 추세 악화 (MACD) — 음수이면서 '더 나빠지는 중'일 때만 제외 (떨어지는 칼날)
    #    음수라도 개선(↗) 중이면 반등 신호로 보고 통과시킨다.
    h, p = row["macd_hist"], row["macd_hist_prev"]
    if h is not None and p is not None:
        if h < 0 and h < p:          # 음수 + 악화
            return "downtrend", False, False

    # 4. 급등 추격 금지
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
        reason_kr = {
            "low volume": "거래량 빈약",
            "downtrend": "추세 악화(MACD)",
            "chasing": "급등 추격",
        }
        for r, s in excluded:
            detail = ""
            if s == "low volume":
                detail = f" (평균 대비 {r['vol_ratio']}배)"
            elif s == "downtrend":
                detail = f" ({macd_arrow(r)})"
            lines.append(f"  • {r['ticker']} | {reason_kr.get(s, s)}{detail}")

    if new:
        lines.append("\n🆕 신규 후보")
        for r, s, c, h in results:
            if r["ticker"] in new:
                lines.append(
                    f"  • {r['ticker']} | RSI {r['rsi']} | 등락 {r['chg']:+.2f}% | "
                    f"{r['price']} | 거래량 {r['vol_ratio']}배 | {macd_arrow(r)} | ✅"
                )
    if gone:
        lines.append("\n👋 후보 이탈")
        for t in sorted(gone):
            lines.append(f"  • {t}")

    candidates = [(r, s) for r, s, c, h in results if c]
    lines.append(f"\n🎯 최종 후보 {len(candidates)}개")
    if candidates:
        for r, s in candidates:
            lines.append(
                f"  • {r['ticker']} | RSI {r['rsi']} | 등락 {r['chg']:+.2f}% | "
                f"{r['price']} | {macd_arrow(r)}"
            )
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
