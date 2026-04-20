# 한국 주식 테마 탐지 시스템 (Python)

뉴스/공시/거래데이터를 결합해 **현재 부각되거나 곧 부각될 테마주**를 자동 탐지하는 시스템입니다.

## 🚀 진짜 빠른 실행(처음 사용자용)

아래 5개만 하면 바로 동작합니다.

1. 가상환경 생성/활성화
```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
```

2. 패키지 설치
```bash
pip install -r requirements.txt
```

3. 환경변수 파일 생성
```bash
cp .env.example .env
```
`.env`에서 최소한 아래를 채워주세요.
- `DART_API_KEY` (없어도 실행은 되지만 공시는 스킵)
- `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID` (텔레그램 알림 사용할 때만)

4. 즉시 1회 실행
```bash
python -m src.main --run-now
```

5. 매일 오전 8:30 자동 실행
```bash
python -m src.main --schedule
```

백테스트는 이렇게 실행합니다.
```bash
python -m src.main --run-now --backtest-date 2026-04-10
```

## 1) 주요 기능

- 뉴스 RSS(네이버 금융, 연합뉴스, 한국경제) 수집 및 키워드 급증 감지
- pykrx 기반 거래량/가격 이상 종목 탐지
- 종목→테마 매핑 및 테마 활성화 판정
- 가중치 기반 테마 점수화(0~100) 및 Top 5 추출
- 오전 8:30 자동 실행 스케줄러(APScheduler)
- 텔레그램 알림 전송
- SQLite 누적 저장 + 과거 날짜 백테스트
- 모듈 장애 격리: 한 모듈 실패 시 나머지 지속 실행

---

## 2) 설치 방법

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\\Scripts\\activate
pip install -r requirements.txt
```

Java/Konlpy 환경이 필요합니다.

---

## 3) 환경 변수 설정

`.env.example`을 복사해서 `.env` 파일을 만든 뒤 값 입력:

```bash
cp .env.example .env
```

필수/선택 키:

- `DART_API_KEY` (공시)
- `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID` (알림)

---

## 4) 설정(config.yaml)

`config.yaml`에서 아래를 조정할 수 있습니다.

- 데이터 소스 URL
- 거래량/수익률/시총 임계값
- 테마 가중치(뉴스/거래량/수익률/공시/커뮤니티)
- 스케줄 시간(기본 08:30, Asia/Seoul)
- DB/로그 경로

---

## 5) 실행

### 즉시 1회 실행

```bash
python -m src.main --run-now
```

### 스케줄 실행 (매일 08:30)

```bash
python -m src.main --schedule
```

### 백테스트 실행

```bash
python -m src.main --run-now --backtest-date 2026-04-10
```

---

## 6) 출력 예시

```text
[테마 탐지 리포트] 2026-04-20

1위 테마: 방산 (종합점수: 87점)
 - 관련 종목: A, B, C
 - 부각 이유: 뉴스 키워드 평균 증가율 340%
 - 거래량 급증 종목 수: 2개
```

---

## 7) 데이터 저장 구조 (SQLite)

- `news_items`: 뉴스 원문 메타
- `keyword_stats`: 키워드 언급/증가율 스냅샷
- `stock_anomalies`: 이상 종목 스냅샷
- `theme_scores`: 테마 점수/근거

DB 경로 기본값: `data/theme_detector.db`

---

## 8) 모듈 설명

- `src/news_crawler.py`: 뉴스 수집, 형태소 분석, 키워드 급증 감지, DART 공시 호출
- `src/volume_detector.py`: 거래량/주가/시총 필터로 이상 종목 감지
- `src/theme_mapper.py`: 종목-테마 매핑, 클러스터 생성/활성화 판정
- `src/theme_scorer.py`: 5개 지표 가중합 점수 계산
- `src/alert_reporter.py`: 리포트 포맷팅 + 텔레그램 발송 + 스케줄링
- `src/backtester.py`: 과거 탐지 테마의 이후 수익률 평가
- `src/main.py`: 전체 오케스트레이션

---

## 9) robots.txt 및 크롤링 예의

- RSS/API 위주로 수집하여 robots.txt 정책을 준수합니다.
- 요청 간 1~2초 랜덤 딜레이를 삽입합니다(`config.yaml`).

---

## 10) 전체 파일 구조

```text
thema-stock/
├─ .env.example
├─ config.yaml
├─ requirements.txt
├─ README.md
├─ data/
│  └─ theme_detector.db        # 실행 후 생성
├─ logs/
│  └─ theme_detector.log       # 실행 후 생성
└─ src/
   ├─ __init__.py
   ├─ utils.py
   ├─ news_crawler.py
   ├─ volume_detector.py
   ├─ theme_mapper.py
   ├─ theme_scorer.py
   ├─ alert_reporter.py
   ├─ backtester.py
   └─ main.py
```
