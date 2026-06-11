#!/usr/bin/env python3
"""
Level 2 — 안 깨지게 (신뢰성)
L1에 SRE가 반드시 넣는 4가지를 추가:

  1) 원자적 쓰기   : state.json 쓰다가 죽어도 안 깨짐
  2) 재시도        : yfinance/슬랙 일시 장애에 백오프 재시도
  3) 파일 락       : cron이 겹쳐 돌아도 동시 실행 방지
  4) 구조화 로그   : JSON 로그로 나중에 grep/분석 가능

L1과 인터페이스는 동일. collect()/passes()는 그대로 가져다 쓴다고 가정하고
신뢰성 패턴만 보여줍니다.
"""
import os
import json
import sys
import time
import fcntl
import tempfile
import logging
from datetime import datetime

import requests

STATE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "state.json")
LOCK_PATH = STATE_PATH + ".lock"
# SLACK_WEBHOOK_URL = os.getenv("SLACK_WEBHOOK_URL", "")


# ── 1. 구조화 로그 ───────────────────────────────────────
# 사람이 읽기도 좋고, 나중에 CloudWatch/jq로 파싱도 됨
def setup_logging():
    logging.basicConfig(
        level=logging.INFO,
        format='{"ts":"%(asctime)s","level":"%(levelname)s","msg":"%(message)s"}',
        datefmt="%Y-%m-%dT%H:%M:%S",
    )
    return logging.getLogger("screening")


log = setup_logging()


# ── 2. 원자적 쓰기 ───────────────────────────────────────
def atomic_write_json(path: str, data) -> None:
    """
    임시 파일에 먼저 쓰고 fsync 후 os.replace로 교체.
    os.replace는 같은 파일시스템에서 원자적이라,
    쓰는 도중 프로세스가 죽어도 기존 파일이 깨지지 않음.
    """
    dir_ = os.path.dirname(path) or "."
    fd, tmp = tempfile.mkstemp(dir=dir_, suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(data, f)
            f.flush()
            os.fsync(f.fileno())   # 디스크까지 확실히
        os.replace(tmp, path)      # 원자적 교체
    except Exception:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


def load_prev() -> set:
    if not os.path.exists(STATE_PATH):
        return set()
    try:
        with open(STATE_PATH) as f:
            return set(json.load(f))
    except (json.JSONDecodeError, ValueError):
        log.warning("state.json corrupted; treating as empty")
        return set()


# ── 3. 재시도 (지수 백오프) ──────────────────────────────
def with_retry(fn, tries: int = 3, base: float = 1.0):
    """일시적 실패는 재시도. 마지막까지 실패하면 예외 전파."""
    for attempt in range(1, tries + 1):
        try:
            return fn()
        except Exception as e:
            if attempt == tries:
                log.error(f"final failure after {tries} tries: {e}")
                raise
            wait = base * (2 ** (attempt - 1))   # 1s, 2s, 4s ...
            log.warning(f"attempt {attempt} failed: {e}; retry in {wait}s")
            time.sleep(wait)


def notify_slack(text: str) -> None:
    webhook = os.getenv("SLACK_WEBHOOK_URL", "")  # 매번 새로 읽기
    if not webhook:
        log.info("no webhook; skip slack")
        return
    def _post():
        resp = requests.post(webhook, json={"text": text}, timeout=10)
        if resp.status_code >= 500 or resp.status_code == 429:
            raise RuntimeError(f"slack {resp.status_code}")
        if resp.status_code != 200:
            log.error(f"slack non-retryable {resp.status_code}: {resp.text[:200]}")
        return resp
    with_retry(_post)
    log.info("slack sent")


# ── 4. 파일 락 (동시 실행 방지) ──────────────────────────
class SingleInstance:
    """
    cron이 겹쳐 돌거나 이전 실행이 안 끝났을 때
    두 번째 실행이 락을 못 잡고 즉시 종료.
    """
    def __init__(self, path):
        self.path = path
        self.fp = None

    def __enter__(self):
        self.fp = open(self.path, "w")
        try:
            fcntl.flock(self.fp, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            log.warning("another instance running; exiting")
            sys.exit(0)
        return self

    def __exit__(self, *args):
        fcntl.flock(self.fp, fcntl.LOCK_UN)
        self.fp.close()


# ── 메인 ─────────────────────────────────────────────────
def main() -> int:
    start = time.time()
    with SingleInstance(LOCK_PATH):
        # collect()/passes()는 level1에서 import해 쓴다고 가정
        from level1_mvp import collect, passes, build_msg

        hits = [r for r in with_retry(collect) if passes(r)]
        now = {r["ticker"] for r in hits}
        prev = load_prev()

        new, gone = now - prev, prev - now
        atomic_write_json(STATE_PATH, sorted(now))

        if not new and not gone:
            log.info(f"quiet: {len(now)} hits, no change")
        else:
            msg = build_msg(new, gone, hits)
            notify_slack(msg)
            log.info(f"notified new={sorted(new)} gone={sorted(gone)}")

    log.info(f"done in {time.time()-start:.1f}s")
    return 0


if __name__ == "__main__":
    sys.exit(main())

