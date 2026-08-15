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
--   code          친구에게 알려주는 초대 코드. 이걸로 방을 찾아
--                 들어옵니다. 방마다 서로 달라야 하므로 아래에
--                 "중복 금지" 규칙을 걸어 둡니다.
--   host_nickname 방을 만든 사람. 방장은 방마다 딱 한 명이라
--                 컬럼 하나로 충분합니다.
--   name          방 목록 화면에 뭐라고 표시할지. 이름이 없으면
--                 사용자가 어느 방에 들어갈지 고를 수 없습니다.
--   max_players   정원. 입장 API에서 "꽉 찼습니다"를 판단하려면
--                 방마다 정원이 저장돼 있어야 합니다.
--   status        방의 현재 상태. 이미 게임이 시작된 방에 새로
--                 들어오면 안 되므로 구분이 필요합니다.
--   created_at    만들어진 시각. 방 목록을 최신순으로 정렬할 때 씁니다.
--
-- "누가 이 방에 들어와 있는가"는 여기 없습니다. 한 방에 여러 명이
-- 들어오는데, 한 칸에 여러 명을 욱여넣을 수 없기 때문입니다.
-- 그건 방 입장 기능을 만들 때 별도 테이블로 다룹니다.
-- (host_nickname 은 "여러 명"이 아니라 "한 명"이라서 여기 둡니다.)
-- ─────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS rooms (
    id            serial PRIMARY KEY,
    code          text NOT NULL,
    host_nickname text NOT NULL,
    name          text NOT NULL,
    max_players   integer NOT NULL DEFAULT 4,
    status        text NOT NULL DEFAULT 'waiting',
    created_at    timestamp NOT NULL DEFAULT now(),

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


-- ─────────────────────────────────────────────────────────────
-- rooms 변경 이력 — 이미 만들어져 있는 DB 를 따라오게 하기
--
-- 위의 CREATE TABLE 은 "테이블이 아예 없을 때"만 동작합니다. 이미
-- rooms 를 만들어 둔 사람의 DB 에는 새 컬럼이 생기지 않습니다.
-- 그래서 아래 문장들이 필요합니다.
--
-- 결과적으로 두 경우가 똑같아집니다:
--   새로 만드는 사람  → CREATE TABLE 로 생기고, 아래는 전부 건너뜀
--   이미 있는 사람    → 아래 문장으로 따라옴
-- ─────────────────────────────────────────────────────────────

ALTER TABLE rooms ADD COLUMN IF NOT EXISTS code          text;
ALTER TABLE rooms ADD COLUMN IF NOT EXISTS host_nickname text;

-- "비어 있으면 안 된다"를 뒤늦게 거는 것이라, 이미 빈 값이 든 행이
-- 있으면 여기서 에러가 납니다. 그건 조용히 넘어가면 안 되는 상황이라
-- 일부러 막지 않았습니다. (지금 rooms 는 비어 있어서 문제없습니다)
ALTER TABLE rooms ALTER COLUMN code          SET NOT NULL;
ALTER TABLE rooms ALTER COLUMN host_nickname SET NOT NULL;

-- 초대 코드는 방마다 달라야 합니다. 코드가 겹치면 친구가 엉뚱한 방에
-- 들어가게 됩니다. 백엔드도 겹치지 않게 만들지만, DB 에도 걸어 둡니다.
CREATE UNIQUE INDEX IF NOT EXISTS rooms_code_key ON rooms (code);

-- 코드 모양 규칙: 대문자·숫자 4자리.
-- 헷갈리는 글자(O·0, I·1, L)는 아예 쓰지 않습니다. 친구에게 코드를
-- 불러줄 때 "영어 오야, 숫자 영이야?"를 묻지 않아도 되게 하려는 것입니다.
--
-- DROP 후 ADD 하는 이유: ADD CONSTRAINT 에는 IF NOT EXISTS 가 없어서
-- 두 번 실행하면 에러가 납니다. 먼저 지우고 다시 걸면 몇 번을 실행해도
-- 안전합니다.
--
-- NOT VALID 를 붙인 이유: 예전에 6자리로 만들어 둔 방들이 이미 DB 에
-- 들어 있습니다. NOT VALID 가 없으면 "옛날 데이터가 새 규칙에 안 맞는다"며
-- 이 문장이 실패해서, 스키마를 아예 적용할 수 없게 됩니다.
-- NOT VALID 는 **앞으로 들어오는 값만** 검사하고 옛날 것은 그냥 둡니다.
-- (옛날 방은 이미 끝난 방이라 다시 쓰이지 않습니다)
ALTER TABLE rooms DROP CONSTRAINT IF EXISTS rooms_code_valid;
ALTER TABLE rooms ADD  CONSTRAINT rooms_code_valid
    CHECK (code ~ '^[A-HJKMNP-Z2-9]{4}$') NOT VALID;

-- 방장 닉네임: 플레이어 닉네임과 같은 규칙 (공백만 금지, 1~20자)
ALTER TABLE rooms DROP CONSTRAINT IF EXISTS rooms_host_nickname_valid;
ALTER TABLE rooms ADD  CONSTRAINT rooms_host_nickname_valid
    CHECK (length(trim(host_nickname)) BETWEEN 1 AND 20);

-- 게임이 실제로 시작된 시각. 아직 시작 안 했으면 NULL.
--
-- status 로는 이걸 알 수 없습니다. status 가 'playing' 이 되는 시점은
-- **두 사람이 다 모였을 때**지, 방장이 시작을 누른 때가 아닙니다.
-- 그래서 "모였지만 아직 시작 전"과 "게임 중"이 status 만으로는
-- 구분되지 않습니다. 이 칸이 그 둘을 갈라 줍니다.
--
-- 시각(timestamp)으로 둔 이유: true/false 로 두면 "시작했다"만 알 수
-- 있지만, 시각으로 두면 **언제 시작했는지**까지 남습니다. 나중에
-- "이 게임은 몇 분 걸렸나"를 물어볼 때 칸을 새로 만들지 않아도 됩니다.
-- 값이 있으면 곧 "시작했다"는 뜻이라 잃는 것도 없습니다.
ALTER TABLE rooms ADD COLUMN IF NOT EXISTS started_at timestamp;


-- ─────────────────────────────────────────────────────────────
-- messages — 오간 대화 한 줄 한 줄
--
-- 지금까지 대화는 두 사람의 화면에만 있었습니다. 창을 닫으면 그대로
-- 사라졌습니다. 이 테이블이 그 내용을 남겨 둡니다.
--
-- 컬럼을 이렇게 정한 이유:
--   room_id    어느 방에서 오간 말인지. 이게 없으면 모든 대화가
--              한 덩어리로 섞여서 나중에 갈라낼 수 없습니다.
--   sender     누가 한 말인지. 지금은 닉네임을 글자 그대로 적습니다.
--              players 테이블과 이어져 있지 않기 때문입니다.
--   text       내용.
--   created_at 언제 한 말인지. **대화를 순서대로 보여주려면 필수**입니다.
--
-- 왜 방 코드가 아니라 room_id 인가: 코드는 사람이 읽는 값이고, 나중에
-- 규칙이 바뀔 수 있습니다(방금 6자리에서 4자리로 바꿨듯이). id 는
-- DB 가 매기는 번호라 절대 바뀌지 않아서 이어 붙이기에 안전합니다.
-- ─────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS messages (
    id         serial PRIMARY KEY,

    -- REFERENCES 는 "이 번호는 rooms 에 실제로 있는 방이어야 한다"는
    -- 규칙입니다. 없는 방의 대화가 저장되는 걸 DB 가 막아 줍니다.
    --
    -- ON DELETE CASCADE 는 "그 방이 지워지면 이 대화도 같이 지워라".
    -- 이게 없으면 방을 지울 때 "대화가 남아 있어서 못 지운다"고 막히거나,
    -- 주인 없는 대화만 덩그러니 남습니다.
    room_id    integer NOT NULL REFERENCES rooms (id) ON DELETE CASCADE,

    sender     text NOT NULL,
    text       text NOT NULL,
    created_at timestamp NOT NULL DEFAULT now(),

    -- 백엔드에서도 검사하지만 DB 에도 걸어 둡니다. (마지막 방어선)
    CONSTRAINT messages_sender_valid
        CHECK (length(trim(sender)) BETWEEN 1 AND 20),
    CONSTRAINT messages_text_valid
        CHECK (length(trim(text)) BETWEEN 1 AND 500)
);

-- 대화를 꺼내 볼 때는 언제나 "이 방의 말들을 시간 순서로"입니다.
-- 그 모양 그대로 색인을 만들어 두면 방이 많아져도 빠릅니다.
CREATE INDEX IF NOT EXISTS messages_room_id_created_at_idx
    ON messages (room_id, created_at);
