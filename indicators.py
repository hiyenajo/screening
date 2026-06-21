"""
indicators.py — 기술적 지표 계산 (순수 함수)
================================================
현업에서는 지표 계산을 신호 로직과 분리된 별도 모듈로 둔다.
이유:
  - 지표만 독립적으로 단위 테스트 가능 (값이 맞는지 검증)
  - 여러 전략에서 재사용
  - 외부 의존성(pandas-ta 등) 없이 표준 공식만으로 구현 → 환경 의존성 최소화

모든 함수는 입력을 변형하지 않는 순수 함수이며, 외부 라이브러리를 쓰지 않는다.
"""
from typing import List, Optional, Tuple


def ema(values: List[float], period: int) -> List[Optional[float]]:
    """
    지수이동평균 (Exponential Moving Average).

    관행(TradingView / ta-lib 등 대부분의 차팅 플랫폼):
      - 첫 EMA 값은 앞 `period`개의 단순평균(SMA)으로 시드
      - 이후 EMA_t = (price_t - EMA_{t-1}) * k + EMA_{t-1},  k = 2/(period+1)

    데이터가 충분히 쌓이면(수십 봉 이상) 최신 EMA 값은
    시딩 방식 차이와 무관하게 동일 값으로 수렴한다.

    반환: 입력과 같은 길이 리스트. 시드 이전 구간은 None.
    """
    n = len(values)
    if n < period:
        return [None] * n

    out: List[Optional[float]] = [None] * n
    k = 2.0 / (period + 1)

    seed = sum(values[:period]) / period   # 첫 period개 SMA로 시드
    out[period - 1] = seed
    prev = seed
    for i in range(period, n):
        prev = (values[i] - prev) * k + prev
        out[i] = prev
    return out


def rsi(closes: List[float], period: int = 14) -> Optional[float]:
    """
    RSI (Relative Strength Index) — Wilder's smoothing (현업 표준).

    단순평균이 아니라 Wilder 지수평활을 쓴다:
      초기 avg_gain/avg_loss = 첫 period개의 단순평균
      이후 avg = (이전avg * (period-1) + 현재값) / period

    반환: 최신 RSI 값(0~100) 또는 데이터 부족 시 None.
    """
    if len(closes) < period + 1:
        return None

    deltas = [closes[i] - closes[i - 1] for i in range(1, len(closes))]
    gains = [d if d > 0 else 0.0 for d in deltas]
    losses = [-d if d < 0 else 0.0 for d in deltas]

    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period

    for i in range(period, len(deltas)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period

    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100.0 - (100.0 / (1.0 + rs))


def macd(
    closes: List[float],
    fast: int = 12,
    slow: int = 26,
    signal: int = 9,
) -> Tuple[Optional[List], Optional[List], Optional[List]]:
    """
    MACD (Moving Average Convergence Divergence).

      MACD line   = EMA(fast) - EMA(slow)
      signal line = EMA(signal) of MACD line
      histogram   = MACD line - signal line

    히스토그램 해석:
      > 0  : MACD가 시그널 위 → 상승 모멘텀(bullish)
      < 0  : MACD가 시그널 아래 → 하락 모멘텀(bearish)
      상승 : 모멘텀 개선(전환 가능성)
      하락 : 모멘텀 악화

    안정적인 신호선까지 얻으려면 최소 slow + signal(=35)봉 필요.
    데이터 부족 시 (None, None, None).

    반환: (macd_line, signal_line, histogram) — 각각 입력 길이 리스트,
          계산 불가 구간은 None.
    """
    n = len(closes)
    if n < slow + signal:
        return None, None, None

    ema_fast = ema(closes, fast)
    ema_slow = ema(closes, slow)

    macd_line: List[Optional[float]] = [
        (f - s) if (f is not None and s is not None) else None
        for f, s in zip(ema_fast, ema_slow)
    ]

    # 시그널선: MACD line의 유효 구간에만 EMA 적용 후 원래 인덱스로 복원
    valid = [m for m in macd_line if m is not None]
    sig_valid = ema(valid, signal)

    signal_line: List[Optional[float]] = [None] * n
    j = 0
    for i, m in enumerate(macd_line):
        if m is not None:
            signal_line[i] = sig_valid[j]
            j += 1

    histogram: List[Optional[float]] = [
        (m - s) if (m is not None and s is not None) else None
        for m, s in zip(macd_line, signal_line)
    ]

    return macd_line, signal_line, histogram
