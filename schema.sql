-- ─────────────────────────────────────────────────────────────
-- 데이터베이스 테이블 정의 (PostgreSQL)
--
-- 이 파일은 "DB가 어떤 모양이어야 하는가"를 적어 둔 설계도입니다.
-- 저장소를 새로 받은 사람은 이 파일 하나만 실행하면 똑같은 DB를
-- 만들 수 있습니다.
--
-- 적용 방법:
--   .venv/bin/python apply_schema.py
--
-- 모든 문장에 IF NOT EXISTS 가 붙어 있어서 여러 번 실행해도
-- 안전합니다. (이미 있으면 그냥 넘어감 — 데이터가 지워지지 않음)
-- ─────────────────────────────────────────────────────────────


-- ─────────────────────────────────────────────────────────────
-- players — 게임에 참여하는 사람
-- ─────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS players (
    id         serial PRIMARY KEY,
    nickname   text NOT NULL,
    created_at timestamp DEFAULT now()
);


-- ─────────────────────────────────────────────────────────────
-- rooms — 게임을 시작하기 전에 사람들이 모이는 "방"
--
-- 컬럼을 이렇게 정한 이유:
--   name        방 목록 화면에 뭐라고 표시할지. 이름이 없으면
--               사용자가 어느 방에 들어갈지 고를 수 없습니다.
--   max_players 정원. 입장 API에서 "꽉 찼습니다"를 판단하려면
--               방마다 정원이 저장돼 있어야 합니다.
--   status      방의 현재 상태. 이미 게임이 시작된 방에 새로
--               들어오면 안 되므로 구분이 필요합니다.
--   created_at  만들어진 시각. 방 목록을 최신순으로 정렬할 때 씁니다.
--
-- "누가 이 방에 들어와 있는가"는 여기 없습니다. 한 방에 여러 명이
-- 들어오는데, 한 칸에 여러 명을 욱여넣을 수 없기 때문입니다.
-- 그건 방 입장 기능을 만들 때 별도 테이블로 다룹니다.
-- ─────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS rooms (
    id          serial PRIMARY KEY,
    name        text NOT NULL,
    max_players integer NOT NULL DEFAULT 4,
    status      text NOT NULL DEFAULT 'waiting',
    created_at  timestamp NOT NULL DEFAULT now(),

    -- CHECK 는 "이 조건에 안 맞는 값은 아예 저장하지 마라"는 DB의 규칙입니다.
    -- 백엔드 코드에서도 검사하지만, DB에도 걸어 두면 코드에 실수가 있어도
    -- 이상한 데이터가 들어가지 않습니다. (마지막 방어선)

    -- 방 이름: 공백만 있는 이름 금지, 1~30자
    CONSTRAINT rooms_name_valid
        CHECK (length(trim(name)) BETWEEN 1 AND 30),

    -- 정원: 스크래블은 2~4명이 하는 게임
    CONSTRAINT rooms_max_players_range
        CHECK (max_players BETWEEN 2 AND 4),

    -- 상태: 이 세 가지 말고는 저장 불가
    --   waiting  = 사람 모으는 중 (입장 가능)
    --   playing  = 게임 진행 중 (입장 불가)
    --   finished = 끝난 방
    CONSTRAINT rooms_status_valid
        CHECK (status IN ('waiting', 'playing', 'finished'))
);

-- 방 목록 화면은 "입장 가능한 방을 최신순으로" 보여줍니다.
-- 인덱스는 책의 색인 같은 것으로, 그 조건으로 찾을 때 빨라집니다.
CREATE INDEX IF NOT EXISTS rooms_status_created_at_idx
    ON rooms (status, created_at DESC);
