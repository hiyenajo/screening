# 📈 Stock Screening Automation

> 매일 조건을 충족하는 미국 주식을 자동으로 스크리닝하고, **보유 종목 대조 + 거래량/급등 필터링** 후 Slack으로 알림을 보내는 자동화 시스템

![Python](https://img.shields.io/badge/Python-3.11-blue)
![AWS EC2](https://img.shields.io/badge/AWS-EC2-orange)
![Slack](https://img.shields.io/badge/Slack-Webhook-purple)

---

## 🗂 프로젝트 구조

```
screening/
├── w1_price.py       # W1: 종목 가격 수집 → Slack 알림
├── w2_screening.py   # W2: 조건 필터 + 상태 비교 → 변화만 알림
├── w3_sanity.py      # W3: 보유대조 + 거래량/급등 심사 → 진짜 후보만
├── positions.csv     # 보유 종목 목록 (자동 생성/편집)
├── state_w2.json     # W2 전일 후보 (자동 생성)
├── state_w3.json     # W3 전일 후보 (자동 생성)
├── run.log          # 실행 로그 (자동 생성)
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
- `state_w2.json`으로 전일 상태 비교 → **신규/이탈만** 알림
- 변화 없는 날은 Slack 무음 처리

### W3 — 2차 심사 (헛손질 제거) ⭐ NEW
- ✅ **보유 종목 대조**: positions.csv와 비교 → 이미 갖고 있으면 제외
- ✅ **거래량 심사**: 오늘 거래량이 평균의 0.5배 미만이면 제외 (사고팔기 어려움)
- ✅ **급등 추격 금지**: 전일 대비 +8% 이상이면 제외 (고점 매수 위험)
- **결과**: 후보를 많이 뽑는 게 아니라 **헛손질만 줄임** (후보 0개도 정상)

```
[S2 W3 sanity] 2026-06-21 04:56

💼 보유 중 (대조 완료)
  • LEU | RSI 18.6 | 등락 +0.13% | 보유중
  • PLTR | RSI 31.1 | 등락 +2.90% | 보유중

🚫 제외
  • AMD | 거래량 빈약 (평균 대비 0.3배)

🆕 신규 후보
  • MSFT | RSI 18.6 | 등락 +0.13% | 379.4 | 거래량 1.61배 | ✅

🎯 최종 후보 1개
  • MSFT | RSI 18.6 | 등락 +0.13% | 379.4
```

---

## 🏗 아키텍처

```
cron (3회 실행)
  │
  ├─ 아침 9시 (전날 종가 기준)
  ├─ 밤 10시 30분 (미국 장 시작 직전)
  └─ 새벽 6시 (미국 장 마감 후)
  │
  ▼
collect()
  ├─── yfinance API ──▶ 가격 / RSI / 거래량 수집
  │
passes() ──▶ 조건 필터 (W2)
  │
evaluate() ──▶ 보유? / 거래량? / 급등? 심사 (W3)
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

### 4. 보유 종목 설정
```bash
vi positions.csv
```

```csv
symbol,qty,avg_price
LEU,4,190.86
PLTR,6,128.47
```

(보유 중인 종목 입력. 없으면 빈 파일도 OK)

### 5. 자동 실행 설정 (cron)
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

(웹훅 URL은 본인 것으로 교체)

---

## ⚙️ 커스터마이징

### 워치리스트 (감시할 종목)
`w3_sanity.py` 상단:
```python
WATCHLIST = ["NVDA", "TSLA", "AAPL", "MSFT", "AMZN", "AMD", "LEU", "PLTR"]
```

### 1차 스크리닝 조건
```python
def passes(row: dict) -> bool:
    return row["rsi"] < 35 or abs(row["chg"]) >= 3.0
```

| 파라미터 | 기본값 | 설명 |
|----------|--------|------|
| RSI 기준 | 35 미만 | 과매도 구간 진입 시 |
| 등락률 기준 | ±3% 이상 | 단기 급등락 시 |

### 2차 제외 조건 (W3)
```python
VOLUME_RATIO_MIN = 0.5   # 거래량이 평균의 0.5배 미만이면 제외
CHASING_PCT = 8.0        # 전일 대비 +8% 이상이면 추격 금지
```

---

## 🛠 기술 스택

| 분류 | 기술 |
|------|------|
| Language | Python 3.11 |
| 데이터 수집 | yfinance |
| 인프라 | AWS EC2, IAM, SSM |
| 알림 | Slack Incoming Webhook |
| 자동화 | cron (3회/일) |
| 상태 관리 | JSON 파일 (state_w2.json, state_w3.json) |

---

## 📌 설계 포인트

- **멱등성 보장**: 같은 종목이 며칠째 조건 충족해도 **변화가 있을 때만** 알림 (state 비교)
- **보유 대조**: positions.csv로 이미 갖고 있는 종목은 제외 → 신규 후보만 알림
- **거래량 심사**: 절대값이 아닌 "평소 대비 비율"로 판단 → 큰 종목/작은 종목 공정 비교
- **3회 알림**: 아침/밤/새벽 시간대별로 다양한 데이터 포인트 제공
- **부분 실패 허용**: 특정 종목 수집 실패 시 해당 종목만 스킵, 전체 실행 계속
- **절대경로 사용**: cron과 수동 실행 환경의 경로 차이 방지

---

## 📊 실행 로그 확인
```bash
tail -50 ~/screening/run.log
```

---

## 🔍 문제 해결

| 증상 | 원인 | 해결 |
|------|------|------|
| Slack이 안 옴 | 웹훅 URL이 크론에 안 들어감 | crontab -e에 `SLACK_WEBHOOK_URL="..."` 직접 입력 |
| 계속 "신규"로 떠도 변화 없음 | state.json 상대경로 | 절대경로로 수정 (`BASE = os.path.dirname(...)`) |
| positions.csv가 작동 안 함 | 파일 없거나 형식 오류 | `symbol,qty,avg_price` 헤더 확인 |
| yfinance가 nan 반환 | 장중 미확정 데이터 | `dropna()`로 처리 (이미 적용됨) |
