-- 사이트 전체 요약 (단일 행). 메인 화면의 "N명이 즐기고 있어요" 표시에 사용
CREATE TABLE IF NOT EXISTS site_summary (
    id            INTEGER PRIMARY KEY CHECK (id = 1),
    total_plays   INTEGER NOT NULL,
    total_players INTEGER NOT NULL,
    plays_today   INTEGER NOT NULL,   -- 서버 로컬 시간 기준 오늘
    players_today INTEGER NOT NULL,
    updated_at    TEXT    NOT NULL
);
