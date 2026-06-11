# 📈 Stock Screening Automation

> 매일 오전 9시, 관심 종목을 자동으로 스크리닝해 **조건 충족 시에만** Slack으로 알림을 보내는 자동화 시스템

![Python](https://img.shields.io/badge/Python-3.11-blue)
![AWS EC2](https://img.shields.io/badge/AWS-EC2-orange)
![Slack](https://img.shields.io/badge/Slack-Webhook-purple)

---

## 🗂 프로젝트 구조

```
screening/
├── w1_price.py       # W1: 종목 가격 수집 → Slack 알림
├── screen.py         # W2: 조건 필터 + 상태 비교 → 변화만 알림
├── state.json        # 전일 상태 저장 (자동 생성)
└── README.md
```

---

## ✨ 주요 기능

### W1 — 데이터 수집 & 알림
- `yfinance`로 미국 주식 실시간 가격 수집
- Slack Webhook으로 자동 메시지 전송
- EC2 + cron으로 평일 매일 자동 실행

### W2 — 스마트 필터링 (상태 기반 알림)
- RSI / 등락률 기준으로 **조건 충족 종목만** 필터링
- `state.json`으로 전일 상태를 기억해 **신규 진입 / 이탈 종목만** 알림
- 변화 없는 날은 Slack 무음 처리 (노이즈 제거)

```
[09:00 조건 충족]
🆕 신규: TSLA 등락 -6.2% / RSI 28
👋 이탈: NVDA
```

---

## 🏗 아키텍처

```
cron (평일 09:00)
      │
      ▼
  screen.py
      │
      ├─── yfinance API ──▶ 가격 / RSI 수집
      │
      ├─── passes()     ──▶ 조건 필터 (RSI < 35 or 등락 ±3%)
      │
      ├─── state.json   ──▶ 전일 상태와 비교 (신규 / 이탈 감지)
      │
      └─── Slack        ──▶ 변화 있을 때만 알림
```

**인프라**: AWS EC2 (Amazon Linux 2023, t3.micro) · IAM Role · SSM Session Manager

---

## 🚀 실행 환경 설정

### 1. EC2 인스턴스 준비
- Amazon Linux 2023, t3.micro
- IAM Role에 `AmazonSSMManagedInstanceCore` 정책 연결

### 2. 패키지 설치

```bash
sudo dnf update -y
sudo dnf install -y python3-pip git
pip3 install yfinance requests --ignore-installed
```

### 3. 레포 클론

```bash
git clone https://github.com/hiyenajo/screening.git
cd screening
```

### 4. 환경변수 설정

```bash
export SLACK_WEBHOOK_URL="https://hooks.slack.com/services/xxx/yyy/zzz"
```

### 5. 실행

```bash
# W1: 주가 수집 및 Slack 전송
python3 w1_price.py

# W2: 조건 필터링 + 상태 비교
python3 screen.py
```

---

## ⏰ 자동화 (cron 등록)

```bash
crontab -e
```

```
# 평일 오전 9시 자동 실행
0 9 * * 1-5 SLACK_WEBHOOK_URL="https://hooks.slack.com/..." /usr/bin/python3 /home/ec2-user/screening/screen.py >> /home/ec2-user/screening/run.log 2>&1
```

---

## ⚙️ 조건 커스터마이징

`screen.py`의 `passes()` 함수에서 본인 기준으로 수정:

```python
def passes(row: dict) -> bool:
    return row["rsi"] < 35 or abs(row["chg"]) >= 3.0
```

| 파라미터 | 기본값 | 설명 |
|----------|--------|------|
| RSI 기준 | 35 미만 | 과매도 구간 진입 시 |
| 등락률 기준 | ±3% 이상 | 단기 급등락 시 |

---

## 🛠 기술 스택

| 분류 | 기술 |
|------|------|
| Language | Python 3.11 |
| 데이터 수집 | yfinance |
| 인프라 | AWS EC2, IAM, SSM |
| 알림 | Slack Incoming Webhook |
| 자동화 | cron |
| 상태 관리 | JSON 파일 (state.json) |

---

## 📌 설계 포인트

- **멱등성 보장**: `state.json`으로 중복 알림 방지. 같은 종목이 며칠째 조건 충족해도 첫날만 알림
- **부분 실패 허용**: 특정 종목 수집 실패 시 해당 종목만 스킵, 전체 실행은 계속
- **절대경로 사용**: cron 실행 환경과 수동 실행 환경의 경로 차이 방지

