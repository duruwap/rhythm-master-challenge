# 🥁 리듬 마스터 챌린지 (Rhythm Master Challenge)

두근거리는 4개의 패드를 박자에 맞춰 누르는 드럼 리듬 연습 웹 게임입니다.
모바일·태블릿·PC 브라우저에서 동작하며, 한국어 / English / 简体中文 / 日本語, 라이트·다크 모드를 지원합니다.

## 빠른 시작 (Ubuntu)

```bash
sudo apt update && sudo apt install -y python3 python3-venv   # 최초 1회
./startup.sh            # 포그라운드 실행 → http://localhost:15002
```

| 명령 | 설명 |
|---|---|
| `./startup.sh` | 포그라운드 실행 (gunicorn, `0.0.0.0:15002`) |
| `./startup.sh start` | 백그라운드 실행, 로그 `logs/server.log` |
| `./startup.sh stop` / `restart` / `status` | 중지 / 재시작 / 상태 |
| `./startup.sh dev` | Flask 개발 서버 (자동 리로드) |

처음 실행하면 `.venv` 가상환경을 만들고 `requirements.txt` 를 설치합니다.
환경 변수: `PORT`(기본 15002), `HOST`(기본 0.0.0.0), `WORKERS`(기본 2), `RMC_DATABASE`(SQLite 경로).
같은 Wi‑Fi의 휴대폰·태블릿에서는 스크립트가 출력하는 `http://<서버 IP>:15002` 로 접속하세요.
(방화벽 사용 시 `sudo ufw allow 15002/tcp`)

## 구성

```
app.py              Flask 서버 (페이지 제공 + 같은 리듬 도전 통계 API)
static/index.html   게임 본체 — 바닐라 HTML/CSS/JS 단일 파일, 외부 라이브러리 없음
static/fonts/       Pretendard / Pretendard JP 가변 폰트 (자체 호스팅, SIL OFL 1.1)
startup.sh          Ubuntu 실행 스크립트
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

## 조작

- 모바일/태블릿: 패드 터치 (멀티터치 지원), 가운데 원 = 일시정지
- PC: 키패드 **7 · 9 · 1 · 3** (NumLock 무관) 또는 **Q · W · A · S** / **U · I · J · K**
- `Space` 일시정지/재개 · `Enter` 시작/다시 하기 · `Esc` 일시정지

## 기획서 대비 설계 판단

- **플레이 화면 최소화**: 상단 HUD·인디케이터 바를 없애고 화면 전체를 4분할 패드로 사용. 박자 인디케이터(4박 세그먼트 + 연속 재생헤드), 라운드 진행, 점수는 네 패드가 만나는 **가운데 원형 허브** 하나로 통합했고, 허브를 탭하면 일시정지.
- **패드 안 표시**: 큰 음표 1개(두근·접근 링의 초점) + 패드 바깥쪽 가장자리의 작은 **박자 스트립**(이번 마디 몇 박에 칠지, 판정 결과 색 표시, 4박째에 다음 라운드 NEXT 미리보기). 음표를 박자 수만큼 늘어놓으면 "지금 칠 타이밍" 신호가 약해지므로 둘을 분리.
- **폰트**: 전 언어 Pretendard 로 통일 (일본어 Pretendard JP, 중국어 간체는 Noto Sans SC 폴백).
- **타이밍**: 모든 시간은 `AudioContext` 시계 기준. `getOutputTimestamp()` 로 "실제로 들리는 시각"을 추정하고 입력 이벤트의 `timeStamp` 를 사용해 프레임 지연 없이 판정.
- **타이밍 보정 범위**를 ±150ms → **±300ms** 로 확장 (블루투스 이어폰 지연이 150ms를 넘는 경우가 흔함). 자동 보정은 중앙값 사용.
- 라운드 전환 효과음은 매 라운드가 아닌 **패드가 새로 켜지는 라운드(R3, R5)** 에만 재생 (매 마디 강박 틱과 겹쳐 산만함).
- "다시 하기"는 새 리듬, 친구 도전 링크로 들어온 경우엔 같은 리듬으로 재도전.
- 플레이 중 화면 꺼짐 방지(Wake Lock), 모바일 공유 시트 / PC 다운로드, `prefers-reduced-motion` 대응.

## 테스트

```bash
.venv/bin/pip install -r requirements-dev.txt
.venv/bin/python -m pytest -q
```
