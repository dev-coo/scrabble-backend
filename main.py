# ─────────────────────────────────────────────────────────────
# 스크래블 백엔드 — 기본용 (FastAPI)
#
# FastAPI는 코드를 짜면 자동으로 "스와거(Swagger)" 문서 화면을
# 만들어 줍니다. 브라우저에서 /docs 로 들어가면 API를 눈으로 보고
# 직접 눌러볼 수 있습니다.
#
# 실행:  .venv/bin/uvicorn main:app --host 0.0.0.0 --port 11000
#   - 리턴값 보기 : http://100.115.173.118:11000/
#   - 프론트가 호출: http://100.115.173.118:11000/api/hello
#   - 스와거 문서 : http://100.115.173.118:11000/docs
#   - API 계약서  : http://100.115.173.118:11000/openapi.json
# ─────────────────────────────────────────────────────────────
from datetime import datetime
from typing import List

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, field_validator

from db import get_connection

app = FastAPI(
    title="스크래블 백엔드",
    description="기본용 백엔드입니다. FastAPI가 자동으로 만들어 준 스와거 문서를 /docs 에서 볼 수 있어요.",
    version="0.1.0",
)

# CORS: 다른 주소(프론트엔드)에서 온 브라우저 호출을 허용합니다.
# 이게 없으면 프론트엔드가 백엔드를 호출할 때 브라우저가 막습니다.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
def root():
    # 백엔드는 화면을 그리지 않고, 이렇게 "값"을 돌려줍니다.
    return {"message": "기본용 백엔드입니다"}


@app.get("/api/hello")
def hello():
    # 프론트엔드가 실제로 호출하는 API 입니다.
    return {"message": "기본용 백엔드입니다", "from": "backend"}


# ─────────────────────────────────────────────────────────────
# 플레이어 추가 API
#
# 프론트엔드가 보내는 값(요청)과 백엔드가 돌려주는 값(응답)의
# "모양"을 아래 두 클래스로 미리 정해 둡니다. 이 모양이 곧 계약이고,
# FastAPI가 이걸 읽어서 /docs 문서와 /openapi.json 을 자동으로 만듭니다.
# ─────────────────────────────────────────────────────────────
class NicknameBody(BaseModel):
    """닉네임을 담아 보내는 값의 모양 + 검사 규칙.

    추가(POST)와 수정(PUT)이 **똑같은 규칙**을 써야 하므로 여기 한 번만
    적어 두고 아래 두 클래스가 이어받습니다. 규칙이 두 군데로 갈라지면
    나중에 한쪽만 고쳐서 서로 다르게 동작하는 사고가 납니다.
    """

    nickname: str = Field(..., description="플레이어 닉네임", examples=["수진"])

    @field_validator("nickname")
    @classmethod
    def clean_nickname(cls, value: str) -> str:
        # 앞뒤 공백은 실수로 들어오기 쉬우니 백엔드가 정리해 줍니다.
        value = value.strip()
        if not value:
            raise ValueError("닉네임은 비어 있을 수 없습니다")
        if len(value) > 20:
            raise ValueError("닉네임은 20자 이하여야 합니다")
        return value


class PlayerCreate(NicknameBody):
    """프론트엔드 → 백엔드, 새 플레이어를 추가할 때 보내는 값."""


class PlayerUpdate(NicknameBody):
    """프론트엔드 → 백엔드, 기존 플레이어의 닉네임을 바꿀 때 보내는 값."""


class PlayerOut(BaseModel):
    """백엔드 → 프론트엔드로 돌려주는 값의 모양."""

    id: int
    nickname: str
    created_at: datetime


@app.post("/api/players", response_model=PlayerOut, status_code=201)
def create_player(player: PlayerCreate):
    """새 플레이어 닉네임을 DB에 저장하고, 저장된 결과를 돌려줍니다.

    201은 "새로 만들어졌다"는 뜻의 HTTP 상태 코드입니다.
    (200은 그냥 성공, 201은 성공 + 새 데이터가 생김)
    """
    with get_connection() as conn:
        with conn.cursor() as cur:
            # 값을 문자열로 이어 붙이지 않고 %s 자리에 따로 넘깁니다.
            # 이렇게 해야 닉네임에 이상한 값이 들어와도 DB가 명령어로
            # 오해하지 않습니다. (SQL 인젝션 방지)
            cur.execute(
                "INSERT INTO players (nickname) VALUES (%s)"
                " RETURNING id, nickname, created_at",
                (player.nickname,),
            )
            row = cur.fetchone()

    return PlayerOut(id=row[0], nickname=row[1], created_at=row[2])


@app.get("/api/players", response_model=List[PlayerOut])
def list_players():
    """저장된 플레이어를 전부 돌려줍니다. (id 오름차순 = 먼저 만든 순서)

    POST 와 주소가 똑같고 메서드만 다릅니다. "players 라는 대상"에
    추가하면 POST, 조회하면 GET — 이게 REST 라고 부르는 규칙입니다.

    데이터가 하나도 없으면 에러가 아니라 빈 목록 `[]` 을 돌려줍니다.
    "찾는 게 없는 것"은 잘못이 아니니까요.
    """
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT id, nickname, created_at FROM players ORDER BY id")
            rows = cur.fetchall()

    return [PlayerOut(id=r[0], nickname=r[1], created_at=r[2]) for r in rows]


@app.put("/api/players/{player_id}", response_model=PlayerOut)
def update_player(player_id: int, player: PlayerUpdate):
    """기존 플레이어의 닉네임을 바꿉니다.

    주소에 `{player_id}` 가 들어간 게 POST·GET 과 다른 점입니다.
    "누구를" 바꿀지 지정해야 하니까요. 프론트엔드는 GET 목록에서 받은
    `id` 를 그대로 여기에 넣으면 됩니다.

    없는 id 를 보내면 404 로 알려줍니다. 조용히 아무것도 안 하면
    프론트엔드는 성공한 줄 알기 때문에, 실패는 반드시 알려야 합니다.
    """
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE players SET nickname = %s WHERE id = %s"
                " RETURNING id, nickname, created_at",
                (player.nickname, player_id),
            )
            row = cur.fetchone()

    # 바꿀 대상이 없으면 UPDATE 는 에러가 아니라 "0건 처리"로 끝납니다.
    # 그래서 결과가 비었는지 직접 확인해서 404 를 돌려줘야 합니다.
    if row is None:
        raise HTTPException(status_code=404, detail=f"id {player_id} 인 플레이어가 없습니다")

    return PlayerOut(id=row[0], nickname=row[1], created_at=row[2])


@app.delete("/api/players/{player_id}", response_model=PlayerOut)
def delete_player(player_id: int):
    """플레이어를 삭제하고, 삭제된 사람의 정보를 돌려줍니다.

    보낼 값(body)이 없다는 점이 PUT 과 다릅니다. "누구를" 지울지만
    주소로 알려주면 되니까요.

    지워진 내용을 돌려주는 이유: 프론트엔드가 "OO 님을 삭제했습니다"
    처럼 이름을 띄울 수 있게 하기 위해서입니다. 지우고 나면 그 정보를
    다시 물어볼 방법이 없으므로, 이때 같이 주는 편이 친절합니다.

    없는 id 는 PUT 과 똑같이 404 입니다.
    """
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "DELETE FROM players WHERE id = %s"
                " RETURNING id, nickname, created_at",
                (player_id,),
            )
            row = cur.fetchone()

    # UPDATE 와 마찬가지로, 지울 대상이 없어도 DELETE 자체는 에러가
    # 아닙니다. 결과가 비었는지 직접 확인해야 합니다.
    if row is None:
        raise HTTPException(status_code=404, detail=f"id {player_id} 인 플레이어가 없습니다")

    return PlayerOut(id=row[0], nickname=row[1], created_at=row[2])
