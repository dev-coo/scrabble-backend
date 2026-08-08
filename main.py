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
from typing import Annotated, List

from fastapi import FastAPI, HTTPException, Query, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import AfterValidator, BaseModel, Field, field_validator

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
def clean_nickname(value: str) -> str:
    """닉네임의 앞뒤 공백을 정리하고 규칙에 맞는지 검사합니다.

    이 함수 하나를 POST·PUT(보내는 값)과 중복 확인(주소 뒤 물음표로 오는 값)이
    **함께** 씁니다. 규칙이 여러 군데로 갈라지면 나중에 한쪽만 고쳐서
    서로 다르게 동작하는 사고가 납니다.
    """
    # 앞뒤 공백은 실수로 들어오기 쉬우니 백엔드가 정리해 줍니다.
    value = value.strip()
    if not value:
        raise ValueError("닉네임은 비어 있을 수 없습니다")
    if len(value) > 20:
        raise ValueError("닉네임은 20자 이하여야 합니다")
    return value


class NicknameBody(BaseModel):
    """닉네임을 담아 보내는 값의 모양 + 검사 규칙.

    추가(POST)와 수정(PUT)이 **똑같은 규칙**을 써야 하므로 여기 한 번만
    적어 두고 아래 두 클래스가 이어받습니다.
    """

    nickname: str = Field(..., description="플레이어 닉네임", examples=["수진"])

    @field_validator("nickname")
    @classmethod
    def _clean(cls, value: str) -> str:
        return clean_nickname(value)


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


# ─────────────────────────────────────────────────────────────
# 닉네임 중복 확인 API
#
# 프론트엔드가 "이 닉네임 쓸 수 있나요?"를 물어보는 API입니다.
# 저장(POST)하기 전에 미리 물어봐서, 사용자가 입력하는 도중에
# "이미 사용 중인 닉네임입니다"를 띄울 수 있게 해 줍니다.
#
# 주소 뒤에 `?nickname=수진` 처럼 붙여 보냅니다. 이렇게 물음표 뒤에
# 붙이는 값을 "쿼리 파라미터"라고 부릅니다. GET 은 보낼 값(body)을
# 쓰지 않는 게 관례라서, 조회 조건은 주소에 실어 보냅니다.
# ─────────────────────────────────────────────────────────────
class NicknameCheckOut(BaseModel):
    """백엔드 → 프론트엔드, 중복 확인 결과."""

    nickname: str = Field(..., description="공백이 정리된 최종 닉네임")
    exists: bool = Field(..., description="True면 이미 쓰는 사람이 있음")


@app.get("/api/players/check-nickname", response_model=NicknameCheckOut)
def check_nickname(
    nickname: Annotated[
        str,
        AfterValidator(clean_nickname),  # POST·PUT 과 똑같은 규칙을 적용
        Query(description="확인할 닉네임", examples=["수진"]),
    ],
):
    """닉네임이 이미 쓰이고 있는지 알려줍니다.

    이 API 는 **알려주기만 하고 아무것도 저장하지 않습니다.** 조회만 하는
    기능이라 GET 을 씁니다.

    없는 닉네임이어도 404 가 아니라 200 입니다. "찾는 게 없다"가 곧
    이 API 가 듣고 싶어 하는 정답 중 하나이기 때문입니다.
    (`exists: false` = 쓸 수 있음)

    ⚠️ 확인 시점과 저장 시점 사이에 다른 사람이 같은 닉네임을 먼저
    저장할 수 있습니다. 이 API 만으로는 중복을 완전히 막지 못합니다.
    확실히 막으려면 DB 테이블에 "같은 닉네임 금지" 제약을 거는
    **별도 작업**이 필요합니다.
    """
    with get_connection() as conn:
        with conn.cursor() as cur:
            # 전부 가져와서 파이썬에서 세지 않고 DB에게 "있냐?"만 묻습니다.
            # 데이터가 많아져도 빠르고, 주고받는 양도 적습니다.
            cur.execute(
                "SELECT EXISTS (SELECT 1 FROM players WHERE nickname = %s)",
                (nickname,),
            )
            exists = cur.fetchone()[0]

    return NicknameCheckOut(nickname=nickname, exists=exists)


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


# ─────────────────────────────────────────────────────────────
# 웹소켓 — 초기 세팅 (연결 확인용 통로 하나)
#
# 지금까지 만든 API 와 무엇이 다른가:
#   HTTP API 는 "물어보면 답하고 끊는" 방식입니다. 프론트엔드가
#   물어보지 않으면 백엔드는 아무 말도 할 수 없습니다.
#   웹소켓은 한 번 연결해 두면 **선이 계속 이어져 있어서**, 백엔드가
#   먼저 말을 걸 수 있습니다. "누가 방에 들어왔다"처럼 다른 사람 때문에
#   생긴 일을 알려주려면 이게 필요합니다.
#
# ⚠️ 여기 있는 건 **연결이 되는지 확인하는 통로**까지입니다.
#    방 입장 알림·채팅·게임 진행 같은 실제 기능은 아직 없습니다.
#    그것들은 각각 별도 기능 단위로 붙일 예정입니다.
#
# ⚠️ 이 경로는 **스와거(/docs)에 나오지 않습니다.** FastAPI 가 자동
#    문서화해 주는 건 HTTP API 뿐입니다. 그래서 웹소켓은 사람이 직접
#    쓴 명세서 `docs/ws-contract.md` 가 계약서 역할을 합니다.
# ─────────────────────────────────────────────────────────────
@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """연결을 받아주고, 받은 말을 그대로 되돌려 줍니다. (메아리)

    되돌려 주기만 하는 이유: 프론트엔드가 "선이 진짜 연결됐고 양방향으로
    오간다"를 눈으로 확인할 수 있는 가장 단순한 방법이기 때문입니다.
    실제 기능이 붙으면 이 메아리는 없어집니다.
    """
    # 웹소켓은 HTTP 와 달리 서버가 "받겠다"고 명시해야 연결이 열립니다.
    await websocket.accept()

    # 연결되자마자 서버가 먼저 말을 겁니다. 프론트엔드는 이 메시지를
    # 받아야 "연결 완료"를 확신할 수 있습니다.
    await websocket.send_json({"type": "connected", "message": "웹소켓 연결됨"})

    try:
        # HTTP 는 한 번 답하면 끝이지만, 웹소켓은 끊길 때까지 계속
        # 주고받습니다. 그래서 무한 반복문 안에서 기다립니다.
        while True:
            text = await websocket.receive_text()
            await websocket.send_json({"type": "echo", "message": text})
    except WebSocketDisconnect:
        # 브라우저 탭을 닫는 등 상대가 먼저 끊는 건 **정상**입니다.
        # 에러로 처리하면 서버 로그가 쓸데없이 지저분해집니다.
        pass
