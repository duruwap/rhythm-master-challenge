# 🥁 리듬 마스터 챌린지 (Rhythm Master Challenge)

패드마다 놓인 도형(점·선·삼각형·사각형 … 팔각형)의 꼭짓점 박자에 맞춰 누르는 **폴리리듬** 연습 웹 게임입니다.
모바일·태블릿·PC 브라우저에서 동작하며, 한국어 / English / 简体中文 / 日本語, 라이트·다크 모드를 지원합니다.

## 서버 배포 (Ubuntu)

디렉토리 규칙: 프로젝트 `/scsrun/app/rhythm-master-challenge`, PID `/scsrun/pid/rhythm-master-challenge.pid`,
로그 `/scslog/app/rhythm-master-challenge/app.log`, 가상환경 `<프로젝트>/venv`.

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

포트·워커 수 등은 `scsrun.conf` 에서 설정합니다 (`PORT` 기본 15002, `WORKERS` 기본 2, `RMC_DATABASE` SQLite 경로).
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
- `requirements.txt` 가 바뀌었을 때만 `pip install` 을 다시 실행하고, `git pull` 은 `--ff-only` 로 실행합니다.
- 기동 직후 프로세스가 죽으면 로그 마지막 20줄을 보여 주고 실패 코드로 종료합니다.

## 구성

```
app.py              Flask 서버 (페이지 제공 + 같은 리듬 도전 통계 API)
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
| GET | `/api/health` | 헬스 체크 |
| POST | `/api/scores` | `{seed, bpm, level, score, accuracy, maxCombo}` 기록 → `{plays, best, rank, topPercent}` |
| GET | `/api/scores?seed=&bpm=&level=` | 해당 리듬의 도전 횟수·최고 점수 |

점수는 클라이언트에서 계산되므로 경쟁용 랭킹이 아닌 "친구끼리 비교"용 가벼운 통계입니다(범위 검증 + IP당 분당 30회 제한).
서버 없이 `static/index.html` 을 직접 열어도 게임은 동작합니다(통계·자체 호스팅 폰트만 생략).

## 게임 규칙

- 메인 화면에서 난이도를 고르면 바로 시작합니다.
  - **쉬움**: 좌/우 2패드 · **보통**: 위 2조각 + 아래 1조각 피자형 3패드 · **어려움**: 4분할 4패드
- 패드마다 도형이 하나씩 있고, 공이 도형 둘레를 **한 마디(4박)에 한 바퀴** 돕니다. 꼭짓점 N개 = 한 마디에 N번 균등 간격으로 치기.
  1=점, 2=선, 3=삼각형 … 8=팔각형. 서로 다른 도형이 엇갈리며 폴리리듬이 됩니다 (예: 3 대 4).
- **8라운드**. 라운드마다 3초 준비 시간(마지막 4박은 4·3·2·1 카운트) 후 같은 리듬을 **2마디(8박)** 반복합니다.
- 라운드별 도형 후보는 `CONFIG.SHAPE_POOLS` (난이도·라운드별), 시드로 패드 수만큼 서로 다른 도형을 뽑습니다. 직전 라운드와 같은 조합은 나오지 않습니다.
- 여러 패드를 동시에 쳐야 하는 순간이 있습니다 (마디 첫 박은 모든 패드). 동시 입력 제한 없음.
- 판정 PERFECT ±45ms / GREAT ±90ms / GOOD ±140ms. 연주 중 빈 타이밍 누르기는 헛치기(−300).
- 라운드 등급: 전부 PERFECT·헛치기 0 = P, 정확도 90%↑ = G, 75%↑ = Go, 그 외 X
- 결과: 라운드별 등급, 점수, **총 등급** — 이론상 최대 점수 대비
  브론즈 < 25% ≤ 실버 < 45% ≤ 골드 < 65% ≤ 플래티넘 < 80% ≤ 다이아 < 93% ≤ 챌린저 (`TIERS` 상수).
  순위는 같은 난이도·BPM 전체 플레이 대비 "상위 N%" (친구 도전 리듬이면 같은 리듬 기준). "이미지 저장"은 결과 카드 PNG를 다운로드합니다.

## 조작

- 모바일/태블릿: 패드(조각) 터치, 멀티터치 지원. 가운데 원 = 일시정지
- PC: **Q · W · A · S** (화면 위치 그대로 — 쉬움은 Q·A=왼쪽, W·S=오른쪽 / 보통은 Q=왼쪽 위, W=오른쪽 위, A·S=아래)
- `Space` 일시정지/재개 · `Enter` 시작/다시 하기 · `Esc` 일시정지

## 설계 메모

- **타이밍**: 모든 시간은 `AudioContext` 시계 기준. `getOutputTimestamp()` 로 "실제로 들리는 시각"을 추정하고 입력 이벤트의 `timeStamp` 로 판정.
- **화면 분할**: 각 패드는 화면 전체 크기 레이어에 `clip-path` 다각형을 씌워 자기 조각만 남깁니다(터치 판정도 조각 모양).
  도형은 조각 안에서 가운데 허브·노치를 피해 가장 넓은 자리에 같은 크기로 배치됩니다.
- **타이밍 보정** ±300ms (블루투스 이어폰 지연 대응). 설정 > 자동 보정.
- **일시정지** 후 재개하면 현재 라운드를 준비 시간부터 다시 시작하고 그 라운드 점수는 롤백됩니다.
- 폰트: Pretendard (일본어 Pretendard JP, 중국어 간체 Noto Sans SC 폴백).

## 테스트

```bash
venv/bin/pip install -r requirements-dev.txt
venv/bin/python -m pytest -q
```
