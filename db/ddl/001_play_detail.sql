-- 플레이 상세: 한 판이 끝날 때마다 1행 (클라이언트가 비동기로 전송)
CREATE TABLE IF NOT EXISTS play_detail (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    played_at    TEXT    NOT NULL,                  -- 플레이 일시 (UTC, ISO-8601 'YYYY-MM-DDTHH:MM:SSZ')
    player_id    TEXT    NOT NULL,                  -- 브라우저별 익명 플레이어 ID
    level        TEXT    NOT NULL CHECK (level IN ('easy', 'normal', 'hard')),
    bpm          INTEGER NOT NULL,
    seed         INTEGER NOT NULL,
    score        INTEGER NOT NULL CHECK (score >= 0),
    max_possible INTEGER NOT NULL CHECK (max_possible >= 0),
    accuracy     REAL    NOT NULL CHECK (accuracy BETWEEN 0 AND 100),
    max_combo    INTEGER NOT NULL CHECK (max_combo >= 0),
    tier         TEXT                                -- 클라이언트가 표시한 등급 (참고용)
);
CREATE INDEX IF NOT EXISTS idx_play_detail_level_score ON play_detail (level, bpm, score);
CREATE INDEX IF NOT EXISTS idx_play_detail_played_at  ON play_detail (played_at);
CREATE INDEX IF NOT EXISTS idx_play_detail_player     ON play_detail (player_id);
