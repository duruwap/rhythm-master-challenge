# 🥁 리듬 마스터 챌린지 (Rhythm Master Challenge)

패드마다 놓인 도형(점·선·삼각형·사각형 … 팔각형)의 꼭짓점 박자에 맞춰 누르는 **폴리리듬** 연습 웹 게임입니다.
모바일·태블릿·PC 브라우저에서 동작하며, 한국어 / English / 简体中文 / 日本語, 라이트·다크 모드를 지원합니다.

## 서버 배포 (Ubuntu)

디렉토리 규칙: 프로젝트 `/scsrun/app/rhythm-master-challenge`, PID `/scsrun/pid/rhythm-master-challenge.pid`,
로그 `/scslog/app/rhythm-master-challenge/app.log`, 데이터(DB) `/scsdat/app/rhythm-master-challenge/rhythm_master.sqlite3`, 가상환경 `<프로젝트>/venv`.

DB 는 SQLite 파일이라 별도 DB 계정이 없습니다. 서버(`startup.sh`)와 배치(cron)를 **같은 일반 사용자**로 실행하고,
그 사용자가 `/scsrun`·`/scslog`·`/scsdat` 에 쓸 수 있어야 합니다 (최초 1회: `sudo mkdir -p /scsdat/app && sudo chown -R <사용자>: /scsdat`).

```bash
sudo apt update && sudo apt install -y python3 python3-venv git   # 최초 1회
cd /scsrun/app && git clone https://github.com/duruwap/rhythm-master-challenge.git
cd rhythm-master-challenge && ./startup.sh      # → http://<서버 IP>:15002
```

| 명령 | 설명 |
|---|---|
| `./startup.sh` | 기존 프로세스 종료 → `git pull` → venv·의존성 준비 → gunicorn 기동 → 헬스 체크 |
| `./startup.sh --no-pull` | git pull 없이 재기동 |
| `./startup.sh stop` / `status` | 중지 / 상태 확인 |
| `./startup.sh dev` | Flask 개발 서버 (포그라운드, 자동 리로드) |

포트·워커 수 등은 `scsrun.conf` 에서 설정합니다 (`PORT` 기본 15002, `WORKERS` 기본 2, `RMC_DATABASE` SQLite 경로, 기본 `/scsdat/app/<앱이름>/rhythm_master.sqlite3`).
방화벽 사용 시 `sudo ufw allow 15002/tcp`.

### 공통 런처 `scripts/scs-run.sh`

`/scsrun/app` 아래의 다른 프로젝트에도 그대로 쓸 수 있는 공통 기동 스크립트입니다.

```bash
cp scripts/scs-run.sh ~/scs-run.sh
~/scs-run.sh standard-of-lotto            # 종료 → git pull → 의존성 → 기동
~/scs-run.sh standard-of-lotto stop       # status / restart / --no-pull 도 지원
```

- 프로젝트에 `scsrun.conf` 가 없으면 `venv/bin/python app.py` 로 실행합니다 (기존 run-*.sh 와 동일).
- `scsrun.conf` 에서 `APP_CMD`(실행 명령), `HEALTH_URL`(기동 후 확인 URL)과 앱 환경 변수를 정할 수 있습니다.
- 데이터 디렉토리 `/scsdat/app/<앱이름>` 을 만들고 앱에 `SCS_DATA_DIR` 환경 변수로 전달합니다.
- `requirements.txt` 가 바뀌었을 때만 `pip install` 을 다시 실행하고, `git pull` 은 `--ff-only` 로 실행합니다.
- 기동 직후 프로세스가 죽으면 로그 마지막 20줄을 보여 주고 실패 코드로 종료합니다.

## 구성

```
app.py              Flask 서버 (페이지 제공 + 결과 기록·통계 API)
game_rules.py       서버 측 점수 검증 규칙 (난이도별 이론상 최대 점수)
db/, batch/         DDL · 통계 배치
static/index.html   게임 본체 — 바닐라 HTML/CSS/JS 단일 파일, 외부 라이브러리 없음
static/fonts/       Pretendard / Pretendard JP 가변 폰트 (자체 호스팅, SIL OFL 1.1)
startup.sh          기동 스크립트 (scripts/scs-run.sh 사용)
scsrun.conf         기동 설정 (포트·gunicorn 명령·헬스 체크 URL)
scripts/scs-run.sh  /scsrun 공통 앱 기동 스크립트
tests/              서버 테스트 (pytest)
```

### API

| 메서드 | 경로 | 설명 |
|---|---|---|
| GET | `/` | 게임 페이지 — 최신 통계를 HTML 에 바로 넣어 보냄(`window.__RMC_STATS__`) → 결과 화면에서 대기 없음 |
| GET | `/api/stats` | 같은 통계 JSON (플레이어 수, 난이도별 점수 분포) |
| POST | `/api/plays` | 한 판 결과 기록 `{level, bpm:90, seed, score, maxPossible, accuracy, maxCombo, playerId, tier}` — 클라이언트는 응답을 기다리지 않음 |
| GET | `/api/health` | 헬스 체크 |

검증: 음수 점수, 리듬 최대치(`maxPossible`)를 넘는 점수, 난이도별 이론상 최대 점수(`game_rules.py`)를 넘는 점수, BPM ≠ 90 은 400 으로 거부합니다. IP당 분당 30회 제한.

## DB · 통계 배치

```
db/ddl/001_play_detail.sql    플레이 상세 (플레이 일시·익명 플레이어 ID·난이도·시드·점수·최대 점수·정확도·콤보·등급)
db/ddl/002_score_summary.sql  score_summary (난이도별 점수 분포) · level_summary (난이도별 요약)
db/ddl/003_site_summary.sql   site_summary (누적 플레이어 수·플레이 수, 오늘 기준)
batch/build_summary.py        play_detail → summary 테이블 재생성 (한 트랜잭션)
batch/run_summary.sh          cron 실행용 래퍼 (로그: /scslog/app/rhythm-master-challenge/batch.log,
                              실행마다 난이도별 등급 점수 범위도 기록)
```

- DB 파일: `/scsdat/app/rhythm-master-challenge/rhythm_master.sqlite3` (WAL 모드라 같은 폴더에 `-wal`·`-shm` 파일도 생김).
- DDL 은 서버 기동 시·배치 실행 시 자동 적용됩니다(모두 `IF NOT EXISTS`). summary 가 비어 있으면 서버 기동 시 1회 자동 생성합니다.
- 주기 실행(예: 10분마다) — `crontab -e`:
  ```
  */10 * * * * /scsrun/app/rhythm-master-challenge/batch/run_summary.sh
  ```
- **상위 %**: 같은 난이도 기록을 점수 내림차순으로 정렬한 분포(최대 1000개 지점, 기록이 1000판 이하면 전체)를 이용해
  `(내 점수보다 높은 기록 수 + 1) / (기록 수 + 1)` 로 계산합니다. 사이트 진입 시 받은 분포로 브라우저에서 즉시 계산합니다.
- **등급**(같은 난이도 상위 %): 챌린저 1% · 마스터 3% · 다이아 7% · 플래티넘 14% · 골드 20% · 실버 25% · 브론즈 30%
  (누적: ≤1% · ≤4% · ≤11% · ≤25% · ≤45% · ≤70% · 나머지). 난이도별 기록이 20판 미만일 때는 임시로 최대 점수 대비 비율로 매깁니다.
- 메인 화면에 "🎮 N명이 즐기고 있어요"(누적 플레이어 수)를 표시합니다.

## 게임 규칙

- 메인 화면에서 난이도를 고르면 바로 시작합니다.
  - **쉬움**: 좌/우 2패드 (세로 화면에서는 위/아래) · **보통**: 위 2칸 + 아래 1칸(가로 전체) 3패드 · **어려움**: 4분할 4패드
- 패드마다 도형이 하나씩 있고, 공이 도형 둘레를 **한 마디(4박)에 한 바퀴** 돕니다. 꼭짓점 N개 = 한 마디에 N번 균등 간격으로 치기.
  1=점, 2=선, 3=삼각형 … 8=팔각형. 서로 다른 도형이 엇갈리며 폴리리듬이 됩니다 (예: 3 대 4).
- **8라운드**. 라운드마다 **4박 카운트**(4·3·2·1, 화면에 ROUND n 크게 표시) 후 같은 리듬을 **2마디(8박)** 반복하고, 공이 시작 꼭짓점으로 돌아오는 **마무리 박**(모든 패드 동시)을 친 뒤 다음 라운드 카운트로 이어집니다 (마무리 박 1박 동안 도형 유지).
- 라운드별 도형 후보는 `CONFIG.SHAPE_POOLS` (난이도·라운드별), 시드로 패드 수만큼 서로 다른 도형을 뽑습니다. 직전 라운드와 같은 조합은 나오지 않습니다.
- 여러 패드를 동시에 쳐야 하는 순간이 있습니다 (마디 첫 박은 모든 패드). 동시 입력 제한 없음.
- 판정 PERFECT ±45ms / GREAT ±90ms / GOOD ±140ms. 라운드 끝부분(패드별 마지막 연주 음과 마무리 박)은 늦게 쳐도 +280ms까지 GOOD 인정. 연주 중 빈 타이밍 누르기는 헛치기(−300)이지만, 방금 친 노트 바로 옆(±250ms)의 재입력은 감점하지 않습니다.
- 라운드 등급: 전부 PERFECT·헛치기 0 = P, 정확도 90%↑ = G, 75%↑ = Go, 그 외 X
- 결과: 라운드별 등급, 점수, **총 등급** — 이론상 최대 점수 대비
  같은 난이도 플레이어 중 상위 % 로 매깁니다 (아래 'DB · 통계 배치' 참고).
  순위는 같은 난이도·BPM 전체 플레이 대비 "상위 N%" (친구 도전 리듬이면 같은 리듬 기준). "이미지 저장"은 결과 카드 PNG를 다운로드합니다.

## 조작

- 모바일/태블릿: 패드(조각) 터치, 멀티터치 지원. 가운데 원 = 일시정지
- PC: **Q · W · A · S** (화면 위치 그대로 — 쉬움은 Q·A=왼쪽, W·S=오른쪽(세로 화면이면 Q·W=위, A·S=아래) / 보통은 Q=왼쪽 위, W=오른쪽 위, A·S=아래)
- `Space` 일시정지/재개 · `Enter` 시작/다시 하기 · `Esc` 일시정지

## 설계 메모

- **타이밍**: 모든 시간은 `AudioContext` 시계 기준. `getOutputTimestamp()` 로 "실제로 들리는 시각"을 추정하고 입력 이벤트의 `timeStamp` 로 판정.
- **화면 분할**: `CONFIG.LAYOUTS` 의 사각형 영역(화면 비율)으로 정의. 도형은 영역 안에서 가운데 허브·노치를 피해 가장 넓은 자리에 같은 크기로 배치됩니다.
- **타이밍 보정** ±300ms (블루투스 이어폰 지연 대응). 설정 > 자동 보정.
- **일시정지** 후 재개하면 현재 라운드를 4박 카운트부터 다시 시작하고 그 라운드 점수는 롤백됩니다.
- 폰트: Pretendard (일본어 Pretendard JP, 중국어 간체 Noto Sans SC 폴백).

## 테스트

```bash
venv/bin/pip install -r requirements-dev.txt
venv/bin/python -m pytest -q
```
