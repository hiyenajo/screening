# 📈 Stock Screening Automation

> 매일 조건을 충족하는 미국 주식을 자동으로 스크리닝하고, **보유 종목 대조 + 거래량/추세/급등 필터링** 후 Slack으로 알림을 보내는 자동화 시스템

![Python](https://img.shields.io/badge/Python-3.11-blue)
![AWS EC2](https://img.shields.io/badge/AWS-EC2-orange)
![Slack](https://img.shields.io/badge/Slack-Webhook-purple)

---

## 🗂 프로젝트 구조

```
screening/
├── w1_price.py          # W1: 종목 가격 수집 → Slack 알림
├── w2_screening.py      # W2: 조건 필터 + 상태 비교 → 변화만 알림
├── w3_sanity.py         # W3: 보유대조 + 거래량/추세/급등 심사 → 진짜 후보만
├── indicators.py        # 기술적 지표(RSI/MACD) 계산 모듈
├── test_indicators.py   # 지표 단위 테스트
├── positions.csv        # 보유 종목 목록 (개인 데이터, git 제외 권장)
├── state_w3.json        # 전일 후보 상태 (자동 생성)
├── run.log              # 실행 로그 (자동 생성)
└── README.md
```

---

## ✨ 주요 기능

### W1 — 데이터 수집 & 알림
- `yfinance`로 미국 주식 가격/RSI/등락률 수집
- Slack Webhook으로 자동 메시지 전송
- EC2 + cron으로 자동 실행

### W2 — 1차 스크리닝 (조건 필터)
- RSI / 등락률 기준으로 **조건 충족 종목만** 필터링
- `state.json`으로 전일 상태 비교 → **신규/이탈만** 알림
- 변화 없는 날은 Slack 무음 처리

### W3 — 2차 심사 (헛손질 제거) ⭐
W2 결과 위에 4단계 필터를 얹어 "실제로 살 만한 후보"만 남긴다.

| 순서 | 필터 | 제외 기준 | 의미 |
|------|------|-----------|------|
| 1 | 보유 대조 | positions.csv에 있으면 | 이미 갖고 있음 |
| 2 | 거래량 | 오늘 < 평균의 0.5배 | 사고팔기 어려움 |
| 3 | 추세(MACD) | 히스토그램 음수 + 악화 중 | 떨어지는 칼날 |
| 4 | 급등 추격 | 전일 대비 +8% 이상 | 고점 추격 위험 |

> 목표는 후보를 많이 뽑는 게 아니라 **헛손질을 줄이는 것**. 후보 0개도 정상.

```
[S2 W3 sanity] 2026-06-21 05:23

💼 보유 중 (대조 완료)
  • XXXX | RSI 31.1 | 등락 +2.90% | 보유중

🚫 제외
  • AMD  | 거래량 빈약 (평균 대비 0.3배)
  • NVDA | 추세 악화(MACD) (MACD -2.00 ↓)
  • AAPL | 급등 추격

🆕 신규 후보
  • TSLA | RSI 28.0 | 등락 -6.20% | 250.0 | 거래량 1.13배 | MACD -0.50 ↗(전환) | ✅

🎯 최종 후보 1개
  • TSLA | RSI 28.0 | 등락 -6.20% | 250.0 | MACD -0.50 ↗(전환)
```

---

## 🧠 핵심 설계: MACD 추세 필터

MACD 히스토그램은 단순히 "음수면 제외"하지 않는다.
과매도(RSI<35) 종목은 본래 MACD가 음수인 경우가 많아, 음수를 전부 제외하면 후보가 사라진다.

대신 **방향(개선/악화)** 을 본다 — 떨어지는 칼날만 거르고 반등 신호는 살린다.

```
NVDA: MACD -1.0 → -2.0  (악화)    → 떨어지는 칼날, 제외 ❌
TSLA: MACD -1.2 → -0.5  (개선)    → 반등 신호, 통과 ✅
```

지표 계산(`indicators.py`)은 신호 로직과 분리해 단위 테스트로 검증한다.
- EMA / RSI(Wilder 평활) / MACD를 외부 라이브러리 없이 표준 공식으로 구현
- `test_indicators.py`로 값 회귀 방지

---

## 🏗 아키텍처

```
cron (3회 실행: 아침 9시 / 밤 10시 30분 / 새벽 6시)
  │
  ▼
collect()
  ├─── yfinance API ──▶ 가격 / RSI / MACD / 거래량 수집 (6개월치)
  │
passes() ──▶ 1차 조건 필터 (W2)
  │
evaluate() ──▶ 보유? / 거래량? / 추세? / 급등? 심사 (W3)
  │
state 비교 ──▶ 어제 후보와 비교 (변화만 알림)
  │
  └─── Slack ──▶ 신규/이탈 있을 때만
```

**인프라**: AWS EC2 (Amazon Linux 2023, t3.micro) · IAM Role · SSM Session Manager

---

## 🚀 설치 & 실행

### 1. EC2 인스턴스 준비
- Amazon Linux 2023, t3.micro
- IAM Role에 `AmazonSSMManagedInstanceCore` 정책 연결

### 2. 패키지 설치
```bash
sudo dnf update -y
sudo dnf install -y python3-pip git cronie
pip3 install yfinance requests --ignore-installed
```

### 3. 레포 클론
```bash
git clone https://github.com/hiyenajo/screening.git
cd screening
```

### 4. 보유 종목 설정 (선택)
보유 종목이 있으면 `positions.csv` 생성. 형식 예시:

```csv
symbol,qty,avg_price
AAAA,10,100.0
BBBB,5,50.0
```

> 개인 보유 정보이므로 `.gitignore`에 추가해 깃에 올리지 않는 것을 권장.

### 5. 지표 테스트 (선택)
```bash
python3 test_indicators.py   # 8/8 통과 확인
```

### 6. 자동 실행 설정 (cron)
```bash
crontab -e
```

```
# 아침 9시 (전날 종가 기준)
0 9 * * 1-5 SLACK_WEBHOOK_URL="https://hooks.slack.com/services/..." /usr/bin/python3 /home/ec2-user/screening/w3_sanity.py >> /home/ec2-user/screening/run.log 2>&1

# 밤 10시 30분 (미국 장 개장 직전)
30 22 * * 0-4 SLACK_WEBHOOK_URL="https://hooks.slack.com/services/..." /usr/bin/python3 /home/ec2-user/screening/w3_sanity.py >> /home/ec2-user/screening/run.log 2>&1

# 새벽 6시 (미국 장 마감 후)
0 6 * * 2-6 SLACK_WEBHOOK_URL="https://hooks.slack.com/services/..." /usr/bin/python3 /home/ec2-user/screening/w3_sanity.py >> /home/ec2-user/screening/run.log 2>&1
```

> 웹훅 URL은 본인 것으로 교체. cron은 `.bashrc`를 읽지 않으므로 환경변수를 줄 앞에 직접 지정.

---

## ⚙️ 커스터마이징

### 워치리스트 (감시할 종목)
`w3_sanity.py` 상단:
```python
WATCHLIST = ["NVDA", "TSLA", "AAPL", "MSFT", "AMZN", "AMD"]
```

### 필터 임계값
```python
RSI_MAX = 35              # 1차: RSI 이 값 미만이면 통과
CHG_MIN = 3.0             # 1차: |등락| 이 값 이상이면 통과
VOLUME_RATIO_MIN = 0.5    # 오늘 거래량 < 평균의 이 배수면 제외
CHASING_PCT = 8.0         # 전일 대비 +이 % 이상이면 추격 금지
```

---

## 🛠 기술 스택

| 분류 | 기술 |
|------|------|
| Language | Python 3.11 |
| 데이터 수집 | yfinance |
| 지표 | RSI(Wilder), MACD — 자체 구현 + 단위 테스트 |
| 인프라 | AWS EC2, IAM, SSM |
| 알림 | Slack Incoming Webhook |
| 자동화 | cron (3회/일) |
| 상태 관리 | JSON 파일 (state) |

---

## 📌 설계 포인트

- **멱등성 보장**: 같은 종목이 며칠째 조건 충족해도 **변화가 있을 때만** 알림
- **보유 대조**: 이미 보유한 종목은 신규 후보에서 제외
- **거래량 심사**: 절대값이 아닌 "평소 대비 비율"로 판단 → 종목 규모 무관 공정 비교
- **추세 필터**: MACD 방향(개선/악화)으로 떨어지는 칼날 회피
- **지표 모듈 분리 + 테스트**: 신호 로직과 지표 계산 분리, 값 회귀 방지
- **데이터 충분량 확보**: MACD 계산을 위해 6개월치 데이터 사용
- **부분 실패 허용**: 특정 종목 수집 실패 시 해당 종목만 스킵
- **절대경로 사용**: cron과 수동 실행 환경의 경로 차이 방지

---

## 🔍 문제 해결

| 증상 | 원인 | 해결 |
|------|------|------|
| Slack이 안 옴 | 웹훅이 cron에 안 들어감 | crontab 줄 앞에 `SLACK_WEBHOOK_URL="..."` 직접 지정 |
| 계속 "신규"로 뜸 | state.json 상대경로 | 절대경로 사용 (이미 적용됨) |
| MACD가 n/a | 데이터 부족 | 6개월치 수집 (이미 적용됨) |
| yfinance가 nan 반환 | 장중 미확정 데이터 | `dropna()` 처리 (이미 적용됨) |

---

## 📊 로그 확인
```bash
tail -50 ~/screening/run.log
```
