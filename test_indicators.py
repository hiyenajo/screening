"""
test_indicators.py — 지표 검증 테스트
pytest 없이도 `python3 test_indicators.py` 로 실행 가능.
돈이 걸린 지표는 반드시 테스트로 값을 고정해 둔다 (회귀 방지).
"""
import indicators as ind


def test_ema_hand_calc():
    # EMA(3) of [1,2,3,4,5], k=0.5, seed=SMA(1,2,3)=2.0
    assert ind.ema([1, 2, 3, 4, 5], 3) == [None, None, 2.0, 3.0, 4.0]


def test_ema_insufficient():
    assert ind.ema([1, 2], 3) == [None, None]


def test_rsi_all_gains():
    # 계속 오르기만 하면 RSI=100
    assert ind.rsi([1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16]) == 100.0


def test_rsi_insufficient():
    assert ind.rsi([1, 2, 3]) is None


def test_macd_direction_up():
    up = [100 + i * 0.5 + (i ** 1.5) * 0.1 for i in range(60)]
    _, _, h = ind.macd(up)
    assert h[-1] > 0          # 가속 상승 → 양수


def test_macd_direction_down():
    down = [200 - i * 0.5 - (i ** 1.5) * 0.1 for i in range(60)]
    _, _, h = ind.macd(down)
    assert h[-1] < 0          # 가속 하락 → 음수


def test_macd_insufficient():
    m, s, h = ind.macd([1, 2, 3])
    assert m is None and s is None and h is None


def test_macd_rebound_momentum():
    # 하락 후 반등 시작 → 최근 히스토그램이 개선(우상향)
    v = [100 - i for i in range(35)] + [65 + i * 2 for i in range(8)]
    _, _, h = ind.macd(v)
    recent = [x for x in h if x is not None][-5:]
    assert recent[-1] > recent[0]


if __name__ == "__main__":
    import sys
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    passed = 0
    for t in tests:
        try:
            t()
            print(f"  ✓ {t.__name__}")
            passed += 1
        except AssertionError as e:
            print(f"  ✗ {t.__name__}  실패: {e}")
        except Exception as e:
            print(f"  ✗ {t.__name__}  에러: {e}")
    print(f"\n{passed}/{len(tests)} 통과")
    sys.exit(0 if passed == len(tests) else 1)
