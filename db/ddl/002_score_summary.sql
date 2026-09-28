-- 점수 분포 요약 (배치가 주기적으로 재생성)
-- 난이도별로 점수를 내림차순 정렬했을 때 rank_pos 번째(1부터) 점수.
-- 최대 1000개 지점을 표본으로 저장하므로 기록이 1000판 이하면 모든 기록이 그대로 들어간다.
-- 클라이언트는 "내 점수보다 높은 기록 수"를 이 표로 계산해 상위 %를 즉시 구한다.
CREATE TABLE IF NOT EXISTS score_summary (
    level     TEXT    NOT NULL,
    rank_pos  INTEGER NOT NULL,
    score     INTEGER NOT NULL,
    PRIMARY KEY (level, rank_pos)
);

-- 난이도별 요약
CREATE TABLE IF NOT EXISTS level_summary (
    level      TEXT    PRIMARY KEY,
    plays      INTEGER NOT NULL,
    players    INTEGER NOT NULL,
    best_score INTEGER NOT NULL,
    avg_score  REAL    NOT NULL,
    updated_at TEXT    NOT NULL
);
