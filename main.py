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
import json
import secrets
from collections import deque
from datetime import datetime
from pathlib import Path
from typing import Annotated, Deque, Dict, List, Optional

import yaml
from psycopg import errors as pg_errors
from fastapi import FastAPI, HTTPException, Query, WebSocket, WebSocketDisconnect
from fastapi.concurrency import run_in_threadpool
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, PlainTextResponse
from pydantic import AfterValidator, BaseModel, Field, field_validator
from starlette.websockets import WebSocketState

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


# ─────────────────────────────────────────────────────────────
# 방 만들고 기다리기 (웹소켓)
#
# 1:1 채팅이라 흐름이 이렇습니다:
#   1. 방장이 닉네임을 들고 웹소켓에 접속한다
#   2. 서버가 방을 만들고 **초대 코드를 바로 보내준다**
#   3. 방장은 연결을 붙잡은 채 **기다린다**
#   4. (다음 기능) 친구가 코드를 치고 들어오면 → 방장에게 알려준다
#
# 왜 HTTP API 가 아니라 웹소켓인가:
#   코드만 받는 것이라면 HTTP 로도 됩니다. 하지만 방장은 그 뒤에
#   **"친구가 들어왔다"는 소식을 받아야** 합니다. 그건 방장이 요청한 게
#   아니라 남 때문에 생긴 일이라, 서버가 먼저 말을 걸 수 있어야 합니다.
#   그러려면 방장의 연결이 그때까지 살아 있어야 하고, 그래서 방을 만드는
#   순간부터 웹소켓으로 이어져 있는 것입니다.
#   HTTP 로 방을 만들면 기다리는 연결이 없어서 아무도 들어올 수 없는
#   죽은 방이 됩니다.
# ─────────────────────────────────────────────────────────────

# 코드에 쓸 글자. O·0, I·1, L 은 일부러 뺐습니다.
# 친구에게 코드를 불러줄 때 "영어 오야, 숫자 영이야?"를 묻지 않아도
# 되게 하려는 것입니다. 눈으로 보고 옮겨 적는 값이라 이게 중요합니다.
ROOM_CODE_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"
ROOM_CODE_LENGTH = 4

# 코드가 이미 쓰이고 있으면 다시 뽑습니다. 몇 번까지 다시 뽑을지.
#
# 4자리면 만들 수 있는 코드가 92만 개쯤입니다. 6자리(8억 개)보다 훨씬
# 적으니 겹칠 일도 그만큼 잦아지는데, 겹치면 조용히 다시 뽑으므로
# 사용자는 알아채지 못합니다.
#
# ⚠️ 다만 **끝난 방의 코드도 계속 자리를 차지합니다.** 방이 수십만 개
#    쌓이면 다시 뽑기도 자주 실패하게 됩니다. 그때가 되면 끝난 방의
#    코드를 다시 쓸 수 있게 바꿔야 합니다. (지금 규모에서는 문제없음)
ROOM_CODE_TRIES = 10


class LiveRoom:
    """지금 서버에 살아 있는 방 하나.

    DB 의 `rooms` 행과는 **다른 것**입니다. DB 에는 "이런 방이 있었다"는
    기록이 남지만, 여기에는 **지금 연결돼 있는 실제 통로**가 들어 있습니다.
    연결은 저장할 수 있는 물건이 아니라서 메모리에만 둘 수 있습니다.
    """

    def __init__(self, room_id: int, code: str, host: WebSocket, host_nickname: str):
        # DB 의 rooms.id. 대화를 저장할 때 "어느 방의 말인지" 적는 데 씁니다.
        self.room_id = room_id
        self.code = code
        self.host = host                      # 방장의 연결
        self.host_nickname = host_nickname
        self.guest: Optional[WebSocket] = None  # 나중에 들어올 친구의 연결
        self.guest_nickname: Optional[str] = None


# 지금 살아 있는 방들. { 초대 코드: LiveRoom }
#
# 친구가 코드를 들고 오면 이 표에서 방을 찾아 방장에게 "들어왔다"고
# 알려줍니다. 표에 없는 코드는 곧 "들어갈 수 없는 코드"입니다.
#
# ⚠️ 이 표는 **서버 메모리에만** 있습니다. DB 가 아닙니다.
#    연결은 지금 켜져 있는 이 서버에만 존재하는 것이라 저장할 수가
#    없습니다. 그래서 서버를 껐다 켜면 기다리던 방은 모두 사라지고,
#    그 코드들은 못 쓰게 됩니다.
live_rooms: Dict[str, LiveRoom] = {}


def new_room_code() -> str:
    """추측하기 어려운 초대 코드를 하나 만듭니다.

    `random` 이 아니라 `secrets` 를 쓰는 이유: `random` 으로 만든 값은
    규칙성이 있어서 다음 값을 예측할 수 있습니다. 초대 코드를 예측당하면
    **초대받지 않은 사람이 남의 방에 들어옵니다.** `secrets` 는 그런
    용도로 만들어진 도구입니다.
    """
    return "".join(secrets.choice(ROOM_CODE_ALPHABET) for _ in range(ROOM_CODE_LENGTH))


def insert_room(host_nickname: str):
    """방을 하나 만들어 저장하고, 저장된 내용을 돌려줍니다.

    방 이름은 따로 받지 않고 `"OO님의 방"` 으로 자동으로 짓습니다.
    (테이블에 이름 자리가 있어서 뭔가는 들어가야 하는데, 접속할 때
    오는 건 닉네임뿐이기 때문입니다.)

    코드를 만들지 못하면 `None` 을 돌려줍니다.
    """
    with get_connection() as conn:
        # 아주 낮은 확률로 이미 쓰이는 코드가 뽑힐 수 있습니다. 그때는
        # 에러를 내지 말고 조용히 다시 뽑는 게 맞습니다. 사용자 잘못이
        # 아니니까요.
        for _ in range(ROOM_CODE_TRIES):
            code = new_room_code()
            try:
                # 이 안에서 실패하면 이 INSERT 만 없던 일이 됩니다.
                # 그래야 다음 코드로 다시 시도할 수 있습니다.
                with conn.transaction():
                    with conn.cursor() as cur:
                        cur.execute(
                            "INSERT INTO rooms (code, host_nickname, name)"
                            " VALUES (%s, %s, %s)"
                            " RETURNING id, code, host_nickname, name, max_players",
                            (code, host_nickname, f"{host_nickname}님의 방"),
                        )
                        row = cur.fetchone()
                return {
                    "id": row[0],
                    "code": row[1],
                    "host_nickname": row[2],
                    "name": row[3],
                    "max_players": row[4],
                }
            except pg_errors.UniqueViolation:
                # DB 가 "그 코드는 이미 있다"고 막아준 경우입니다.
                continue

    # 열 번을 다시 뽑아도 계속 겹쳤다면 코드 자릿수가 부족하다는 뜻입니다.
    return None


def set_room_status(code: str, status: str) -> None:
    """방의 상태를 바꿉니다.

    `waiting`  = 방장 혼자 기다리는 중 (친구가 들어올 수 있음)
    `playing`  = 두 명이 다 모임 (더 이상 못 들어옴)
    `finished` = 방장이 나가서 끝난 방 (영영 못 들어옴)

    방장이 나갔는데 코드가 그대로 살아 있으면, 친구가 코드를 쳤을 때
    "있는데 못 들어가는 방"이 되어 더 헷갈립니다. 그래서 끝나면
    `finished` 로 표시해 둡니다.
    """
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("UPDATE rooms SET status = %s WHERE code = %s", (status, code))


# 한 번에 보낼 수 있는 글자 수. 제한이 없으면 아주 긴 글을 보내
# 서버 메모리를 밀어붙이거나 상대 화면을 망가뜨릴 수 있습니다.
CHAT_MAX_LENGTH = 500


def clean_chat_text(value: str) -> str:
    """채팅 메시지를 다듬고 규칙에 맞는지 봅니다.

    닉네임(`clean_nickname`)과 같은 모양의 함수입니다. 검사 규칙을
    한곳에 모아 두면 방장 쪽·친구 쪽이 서로 다르게 동작할 일이 없습니다.
    """
    value = value.strip()
    if not value:
        raise ValueError("빈 메시지는 보낼 수 없습니다")
    if len(value) > CHAT_MAX_LENGTH:
        raise ValueError(f"메시지는 {CHAT_MAX_LENGTH}자 이하여야 합니다")
    return value


def insert_message(room_id: int, sender: str, text: str) -> datetime:
    """오간 말 한 줄을 저장하고, **DB 가 찍은 시각**을 돌려줍니다.

    시각을 파이썬에서 만들지 않고 DB 가 준 값을 그대로 쓰는 이유:
    저장된 기록과 상대 화면에 뜨는 시각이 **한 글자도 다르지 않게**
    하기 위해서입니다. 따로 만들면 아주 조금씩 어긋나고, 나중에
    "화면에는 3초인데 DB 에는 4초"처럼 설명하기 어려운 일이 생깁니다.
    """
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO messages (room_id, sender, text)"
                " VALUES (%s, %s, %s) RETURNING created_at",
                (room_id, sender, text),
            )
            return cur.fetchone()[0]


async def send_quietly(websocket: Optional[WebSocket], payload: dict) -> None:
    """상대에게 알림을 보내되, 이미 끊겼으면 조용히 넘어갑니다.

    뒷정리 도중에 쓰는 함수입니다. 상대가 이미 나간 뒤라면 보내기가
    실패하는데, 그건 **정상 상황**입니다. 여기서 에러를 터뜨리면
    남은 뒷정리(표에서 빼기 등)가 중간에 멈춰버립니다.
    """
    if websocket is None:
        return
    try:
        await websocket.send_json(payload)
    except Exception:
        pass


async def chat_loop(websocket: WebSocket, sender_nickname: str, find_context) -> None:
    """연결이 끊길 때까지 채팅 메시지를 받아 **저장하고 상대에게 건네줍니다.**

    방장 쪽과 친구 쪽이 이 함수 하나를 같이 씁니다. 1:1 이라 양쪽이
    하는 일이 완전히 똑같기 때문입니다. 두 벌로 나눠 적으면 나중에
    한쪽만 고쳐서 "방장은 되는데 친구는 안 되는" 사고가 납니다.

    `find_context` 는 "지금 어느 방이고 상대가 누구인지"를 그때그때
    알려주는 함수입니다. `(방, 상대)` 를 주고, 아직 상대가 없으면
    `None` 을 줍니다. 상대는 도중에 나갔다 다시 들어올 수 있어서,
    한 번 받아 들고 있으면 안 되고 보낼 때마다 다시 물어봐야 합니다.
    """
    while True:
        raw = await websocket.receive_text()

        # ① JSON 인가
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            await websocket.send_json(
                {
                    "type": "error",
                    "message": 'JSON 으로 보내주세요. 예: {"type":"message","text":"안녕"}',
                }
            )
            continue

        # ② 우리가 아는 종류인가
        if not isinstance(data, dict) or data.get("type") != "message":
            await websocket.send_json(
                {
                    "type": "error",
                    "message": '{"type":"message","text":"..."} 형식으로 보내주세요',
                }
            )
            continue

        # ③ 내용이 규칙에 맞는가
        try:
            text = clean_chat_text(str(data.get("text", "")))
        except ValueError as e:
            await websocket.send_json({"type": "error", "message": str(e)})
            continue

        # ④ 건네줄 상대가 있는가
        context = find_context()
        if context is None:
            await websocket.send_json(
                {"type": "error", "message": "상대가 아직 들어오지 않았습니다"}
            )
            continue

        room, partner = context

        # ⑤ 먼저 저장하고, 그다음 건네줍니다.
        #
        # 순서가 중요합니다. 건네준 뒤에 저장하면, 저장이 실패했을 때
        # **화면에는 떴는데 기록에는 없는** 말이 생깁니다. 나중에 대화를
        # 꺼내 보면 조용히 한 줄이 비어 있게 되는데, 그게 훨씬 나쁩니다.
        #
        # 대신 DB 에 문제가 생기면 대화 자체가 멈춥니다. 그건 눈에 띄는
        # 고장이라 오히려 고치기 쉽습니다.
        sent_at = await run_in_threadpool(
            insert_message, room.room_id, sender_nickname, text
        )

        # 보낸 사람에게는 되돌려 주지 않습니다. 자기가 쓴 말은 자기
        # 화면에 바로 그리면 되고, 되돌려 주면 두 번 그려지기 쉽습니다.
        await partner.send_json(
            {
                "type": "message",
                "from": sender_nickname,
                "text": text,
                # 시각은 **DB 가 저장하면서 찍은 값**입니다. 저장된 기록과
                # 화면에 뜨는 시각이 어긋나지 않게 하려는 것입니다.
                "at": sent_at.isoformat(),
            }
        )


@app.websocket("/ws/rooms")
async def host_room(websocket: WebSocket, nickname: str = Query(default="")):
    """방을 만들고, 친구가 들어올 때까지 연결을 붙잡은 채 기다립니다.

    접속 주소 예: `ws://localhost:11000/ws/rooms?nickname=수진`
    """
    # 먼저 연결을 받아줍니다. 받아주기 전에 거절하면 프론트엔드는
    # "왜 거절당했는지"를 알 방법이 없습니다. 일단 받아준 뒤 이유를
    # 말해주고 끊는 편이 훨씬 친절합니다.
    await websocket.accept()

    # 닉네임 규칙은 플레이어 추가와 **완전히 같은 함수**를 씁니다.
    try:
        host_nickname = clean_nickname(nickname)
    except ValueError as e:
        await websocket.send_json({"type": "error", "message": str(e)})
        # 1008 = "규칙에 안 맞아서 끊는다"는 뜻의 웹소켓 표준 코드입니다.
        await websocket.close(code=1008)
        return

    # DB 작업은 "끝날 때까지 기다리는" 방식이라, 그냥 부르면 그동안
    # 서버 전체가 멈춰서 다른 사람의 연결까지 같이 기다리게 됩니다.
    # 그래서 옆에서 따로 돌리도록 넘깁니다.
    room = await run_in_threadpool(insert_room, host_nickname)

    if room is None:
        await websocket.send_json(
            {"type": "error", "message": "방을 만들지 못했습니다. 잠시 후 다시 시도해 주세요"}
        )
        # 1011 = "서버 쪽 사정으로 끊는다"
        await websocket.close(code=1011)
        return

    code = room["code"]

    # 이 줄이 "대기 상태"의 실체입니다. 표에 올라가 있어야 나중에
    # 친구가 코드를 들고 왔을 때 이 연결을 찾아낼 수 있습니다.
    live = LiveRoom(room["id"], code, websocket, room["host_nickname"])
    live_rooms[code] = live

    # 방이 만들어지자마자 코드를 보냅니다. 프론트엔드는 이걸 받아서
    # 화면에 띄우고 "친구에게 알려주세요"라고 안내하면 됩니다.
    await websocket.send_json(
        {
            "type": "room_created",
            "code": code,
            "name": room["name"],
            "host_nickname": room["host_nickname"],
            "max_players": room["max_players"],
        }
    )

    try:
        # 여기서부터가 "기다리기"이자 "대화하기"입니다. 연결을 붙잡고
        # 있어야 나중에 서버가 먼저 말을 걸 수 있습니다.
        #
        # 상대(`live.guest`)를 미리 꺼내 두지 않고 그때그때 찾는 이유:
        # 지금은 아직 아무도 없고, 나중에 들어오기 때문입니다.
        await chat_loop(
            websocket,
            host_nickname,
            lambda: (live, live.guest) if live.guest is not None else None,
        )
    except WebSocketDisconnect:
        # 방장이 탭을 닫은 경우입니다. 정상입니다.
        pass
    finally:
        # 연결이 어떻게 끝나든 뒷정리는 반드시 합니다. 안 그러면 표에
        # 죽은 연결이 쌓여서, 나중에 친구가 코드를 쳤을 때 이미 끊긴
        # 방장에게 말을 걸려다 실패합니다.
        live_rooms.pop(code, None)

        # 방장이 나가면 1:1 대화는 더 이상 성립하지 않습니다. 친구를
        # 그대로 두면 아무 반응 없는 화면 앞에 앉아 있게 되므로,
        # 이유를 알려주고 함께 끊습니다.
        if live.guest is not None:
            await send_quietly(
                live.guest, {"type": "host_left", "message": "방장이 나갔습니다"}
            )
            try:
                # 1001 = "이쪽 사정으로 나간다"는 뜻의 웹소켓 표준 코드
                await live.guest.close(code=1001)
            except Exception:
                pass

        await run_in_threadpool(set_room_status, code, "finished")


# ─────────────────────────────────────────────────────────────
# 랜덤 매칭 (웹소켓)
#
# 코드를 주고받는 대신, **아무나 기다리는 사람과 짝지어 줍니다.**
#
# 짝짓는 규칙은 "시간 순서" — 먼저 와서 기다린 사람이 먼저 짝을
# 만납니다. 이런 줄서기를 선착순(FIFO, First In First Out)이라고
# 부릅니다. 은행 번호표와 같습니다.
#
# 왜 "랜덤"인데 순서를 지키나: 누구와 짝이 될지는 알 수 없지만,
# 기다린 순서까지 뒤죽박죽이면 **먼저 온 사람이 계속 밀려서** 영영
# 짝을 못 만나는 일이 생깁니다. 그건 랜덤이 아니라 불공평한 것입니다.
#
# 짝이 지어진 뒤는 코드로 들어온 것과 **완전히 같습니다.** 같은 방,
# 같은 채팅을 씁니다. 만나는 방법만 다를 뿐이라 새로 만들지 않았습니다.
# ─────────────────────────────────────────────────────────────


class Waiter:
    """짝을 기다리는 사람 한 명.

    `room` 이 `None` 이면 아직 기다리는 중, 값이 있으면 짝을 만난 것입니다.
    이 값은 **나중에 온 사람이 채워 줍니다.** 기다리는 사람은 가만히
    있어도 되고, 그래서 따로 깨우는 장치가 필요 없습니다.
    """

    def __init__(self, websocket: WebSocket, nickname: str):
        self.websocket = websocket
        self.nickname = nickname
        self.room: Optional[LiveRoom] = None
        self.is_host = False
        # 짝지어진 상대. 상대가 나갔을 때 **그 사람을 다시 줄 세워 주려면**
        # 연결만이 아니라 이 사람 정보 전체가 필요합니다.
        self.partner: Optional["Waiter"] = None


# 짝을 기다리는 줄. 왼쪽이 가장 오래 기다린 사람입니다.
#
# ⚠️ 이것도 `live_rooms` 와 마찬가지로 **서버 메모리에만** 있습니다.
#    서버를 껐다 켜면 기다리던 사람들은 모두 사라집니다.
match_queue: Deque[Waiter] = deque()


def take_next_waiter() -> Optional[Waiter]:
    """가장 오래 기다린 사람을 줄에서 꺼냅니다. 없으면 `None`.

    이미 짝이 지어진 사람이 줄에 남아 있을 수 있어서(뒷정리가 늦어진
    경우) 건너뜁니다. 확인 없이 꺼내면 이미 대화 중인 사람에게
    또 짝을 붙여주는 사고가 납니다.
    """
    while match_queue:
        candidate = match_queue.popleft()
        if candidate.room is not None:
            continue
        # 방금 나간 사람이 아직 줄에 남아 있을 수 있습니다. 뒷정리는
        # 그 사람 차례가 와야 도는데, 그 사이에 내가 꺼낼 수 있기
        # 때문입니다. 끊긴 사람과 짝지으면 상대 없는 방이 됩니다.
        if candidate.websocket.client_state is not WebSocketState.CONNECTED:
            continue
        return candidate
    return None


def partner_of(me: Waiter) -> Optional[WebSocket]:
    """지금 내 상대가 누구인지 알려줍니다. 아직 짝이 없으면 `None`."""
    if me.room is None:
        return None
    return me.room.guest if me.is_host else me.room.host


def context_of(me: Waiter):
    """`(방, 상대)` 를 알려줍니다. 아직 짝이 없으면 `None`.

    `chat_loop` 이 대화를 저장하려면 상대뿐 아니라 **어느 방인지**도
    알아야 해서 둘을 함께 줍니다.
    """
    partner = partner_of(me)
    if me.room is None or partner is None:
        return None
    return me.room, partner


async def pair_up(first: Waiter, second: Waiter) -> bool:
    """두 사람을 한 방에 넣고 양쪽에 알립니다. 방을 못 만들면 `False`.

    `first` 는 **더 오래 기다린 사람**이며 방장이 됩니다.
    (방이 그 사람 이름으로 만들어집니다)
    """
    room = await run_in_threadpool(insert_room, first.nickname)
    if room is None:
        return False

    code = room["code"]
    live = LiveRoom(room["id"], code, first.websocket, first.nickname)
    live.guest = second.websocket
    live.guest_nickname = second.nickname
    live_rooms[code] = live

    # 양쪽 모두에게 "너는 이 방의 누구다"를 표시해 둡니다.
    first.room = live
    first.is_host = True
    first.partner = second
    second.room = live
    second.is_host = False
    second.partner = first

    await run_in_threadpool(set_room_status, code, "playing")

    # 기다리던 쪽에게는 **요청하지 않았는데** 오는 소식입니다.
    await send_quietly(
        first.websocket,
        {"type": "matched", "code": code, "partner_nickname": second.nickname},
    )
    await send_quietly(
        second.websocket,
        {"type": "matched", "code": code, "partner_nickname": first.nickname},
    )
    return True


async def join_queue(me: Waiter, front: bool = False) -> None:
    """줄에 세우고 순번을 알려줍니다.

    `front=True` 는 **맨 앞**에 세웁니다. 짝이 지어졌다가 상대가 나가서
    다시 기다리게 된 사람에게 씁니다. 이미 한참 기다렸던 사람을 맨 뒤로
    보내면 기다린 시간이 없던 일이 되기 때문입니다.
    """
    me.room = None
    me.is_host = False
    me.partner = None

    if front:
        match_queue.appendleft(me)
        position = 1
    else:
        match_queue.append(me)
        position = len(match_queue)

    await send_quietly(
        me.websocket,
        {"type": "waiting", "position": position, "nickname": me.nickname},
    )


@app.websocket("/ws/match")
async def match_random(websocket: WebSocket, nickname: str = Query(default="")):
    """아무나 기다리는 사람과 짝지어 줍니다.

    접속 주소 예: `ws://localhost:11000/ws/match?nickname=엘리`

    기다리는 사람이 있으면 **바로** 짝이 되고, 없으면 줄을 서서 다음
    사람이 올 때까지 기다립니다.

    대화 중에 상대가 나가도 **연결은 끊기지 않습니다.** 서버가 알아서
    다시 줄을 세워 주고, 기다리는 사람이 있으면 바로 새 짝을 붙여
    줍니다. 기다렸던 시간을 없던 일로 만들지 않기 위해서입니다.
    """
    await websocket.accept()

    try:
        my_nickname = clean_nickname(nickname)
    except ValueError as e:
        await websocket.send_json({"type": "error", "message": str(e)})
        await websocket.close(code=1008)
        return

    me = Waiter(websocket, my_nickname)
    partner = take_next_waiter()

    if partner is None:
        # 아무도 없으면 줄 맨 뒤에 섭니다.
        await join_queue(me)
    elif not await pair_up(partner, me):
        await websocket.send_json(
            {"type": "error", "message": "방을 만들지 못했습니다. 잠시 후 다시 시도해 주세요"}
        )
        await websocket.close(code=1011)
        # 기다리던 사람은 잘못이 없으니 줄 맨 앞으로 되돌려 놓습니다.
        await join_queue(partner, front=True)
        return

    try:
        # 기다리는 중이든 대화 중이든 같은 반복문입니다. 아직 짝이 없으면
        # `context_of` 가 None 을 주고, chat_loop 가 "상대가 아직
        # 들어오지 않았습니다"라고 알려줍니다.
        await chat_loop(websocket, my_nickname, lambda: context_of(me))
    except WebSocketDisconnect:
        pass
    finally:
        if me.room is None:
            # 아직 줄 서 있는 상태로 나갔습니다. 줄에서 빼지 않으면
            # 다음 사람이 이미 없는 사람과 짝지어집니다.
            try:
                match_queue.remove(me)
            except ValueError:
                pass
        else:
            live = me.room
            other = me.partner

            # 상대가 먼저 나가서 이미 정리됐다면 할 일이 없습니다.
            if live_rooms.get(live.code) is live:
                live_rooms.pop(live.code, None)
                await run_in_threadpool(set_room_status, live.code, "finished")

                if other is not None:
                    await send_quietly(
                        other.websocket,
                        {"type": "partner_left", "nickname": my_nickname},
                    )

                    # 남은 사람의 연결은 **끊지 않습니다.** 그 사람은 잘못이
                    # 없는데 처음부터 다시 접속하게 하면, 기다렸던 시간이
                    # 없던 일이 되고 줄 맨 뒤로 밀립니다.
                    if other.websocket.client_state is WebSocketState.CONNECTED:
                        waiting_person = take_next_waiter()

                        if waiting_person is None:
                            # 기다리는 사람이 없으면 줄 맨 앞에 다시 세웁니다.
                            await join_queue(other, front=True)
                        elif not await pair_up(waiting_person, other):
                            # 방을 못 만들었으면 둘 다 줄로 돌려보냅니다.
                            await join_queue(waiting_person, front=True)
                            await join_queue(other, front=True)
                        # 짝이 지어졌으면 pair_up 이 양쪽에 알렸습니다.
                    else:
                        # 남은 사람도 이미 끊긴 상태였습니다. 그 사람의
                        # 뒷정리는 그쪽 차례가 오면 알아서 돕니다.
                        other.room = None
                        other.partner = None


@app.websocket("/ws/rooms/{code}")
async def join_room(websocket: WebSocket, code: str, nickname: str = Query(default="")):
    """초대 코드로 친구의 방에 들어갑니다.

    접속 주소 예: `ws://localhost:11000/ws/rooms/K7Q2?nickname=엘리`

    들어가는 데 성공하면 **방장에게도** "누가 들어왔다"고 알려줍니다.
    그게 이 기능을 웹소켓으로 만든 이유입니다.
    """
    await websocket.accept()

    # 닉네임 규칙은 방을 만들 때와 **완전히 같은 함수**를 씁니다.
    try:
        guest_nickname = clean_nickname(nickname)
    except ValueError as e:
        await websocket.send_json({"type": "error", "message": str(e)})
        await websocket.close(code=1008)
        return

    # 코드는 사람이 눈으로 보고 옮겨 적는 값입니다. 소문자로 쳤다고
    # 못 들어가게 하면 불친절하므로 대문자로 맞춰줍니다.
    code = code.strip().upper()

    room = live_rooms.get(code)

    # "없는 코드"와 "방장이 이미 나간 코드"를 굳이 구분해서 알려주지
    # 않습니다. 어느 쪽이든 친구가 할 수 있는 일은 똑같고(코드를 다시
    # 받아오기), 구분해서 알려주면 아무 코드나 넣어보며 "이 코드는
    # 있었네"를 알아내는 데 쓰일 수 있습니다.
    if room is None:
        await websocket.send_json(
            {"type": "error", "message": "그런 방이 없습니다. 코드를 다시 확인해 주세요"}
        )
        await websocket.close(code=1008)
        return

    # 1:1 채팅이라 자리는 하나뿐입니다.
    #
    # 여기서 확인하고 바로 아래에서 자리를 채웁니다. 그 사이에 다른
    # 처리를 기다리는(await) 지점을 두면 안 됩니다. 두 명이 거의 동시에
    # 들어올 때 둘 다 "자리 비었네"를 보고 통과해 버립니다.
    if room.guest is not None:
        await websocket.send_json(
            {"type": "error", "message": "방이 꽉 찼습니다"}
        )
        await websocket.close(code=1008)
        return

    room.guest = websocket
    room.guest_nickname = guest_nickname

    # 두 명이 다 모였으니 더 이상 들어올 수 없는 상태로 바꿉니다.
    await run_in_threadpool(set_room_status, code, "playing")

    # 들어온 사람에게: 어디에 들어왔는지 알려줍니다.
    await websocket.send_json(
        {
            "type": "joined",
            "code": code,
            "host_nickname": room.host_nickname,
            "guest_nickname": guest_nickname,
        }
    )

    # 방장에게: **요청하지도 않았는데** 소식이 갑니다.
    # 이게 웹소켓으로 만든 이유 그 자체입니다. HTTP 였다면 방장은
    # "혹시 들어왔나요?"를 계속 물어봐야 했을 것입니다.
    await send_quietly(
        room.host, {"type": "guest_joined", "nickname": guest_nickname}
    )

    try:
        # 들어온 사람 쪽의 상대는 언제나 방장입니다.
        await chat_loop(websocket, guest_nickname, lambda: (room, room.host))
    except WebSocketDisconnect:
        pass
    finally:
        # 방장이 먼저 나가서 방이 이미 정리됐다면 여기서 할 일이 없습니다.
        # 확인하지 않으면, 끝난 방을 되살려 `waiting` 으로 되돌려 놓는
        # 사고가 납니다.
        if live_rooms.get(code) is room and room.guest is websocket:
            room.guest = None
            room.guest_nickname = None
            # 자리가 다시 비었으니 방장은 새 친구를 기다릴 수 있습니다.
            await run_in_threadpool(set_room_status, code, "waiting")
            await send_quietly(
                room.host, {"type": "guest_left", "nickname": guest_nickname}
            )


# ─────────────────────────────────────────────────────────────
# 웹소켓 명세 제공 — 스와거의 웹소켓 버전
#
# HTTP API 는 FastAPI 가 /openapi.json(기계용) 과 /docs(사람용 화면) 을
# 자동으로 만들어 줍니다. 웹소켓은 그게 없어서 같은 두 짝을 직접 만듭니다.
#
#   docs/asyncapi.yaml  = 원본 (손으로 씀)          ← openapi.json 자리
#   /asyncapi.yaml      = 그 파일을 그대로 제공
#   /asyncapi.json      = 같은 내용을 JSON 으로 제공 (화면이 읽어감)
#   /ws-docs            = 사람이 보는 화면            ← /docs 자리
#
# "AsyncAPI" 는 웹소켓용 명세 표준의 이름입니다. HTTP 쪽 표준이
# OpenAPI 인 것과 같은 관계입니다. 표준을 따르면 나중에 다른 도구를
# 붙이기 쉽습니다.
#
# 파일을 미리 읽어두지 않고 **요청이 올 때마다 읽습니다.** 명세를 고치면
# 서버를 껐다 켜지 않아도 화면에 바로 반영되도록 하기 위해서입니다.
# ─────────────────────────────────────────────────────────────
DOCS_DIR = Path(__file__).parent / "docs"
ASYNCAPI_FILE = DOCS_DIR / "asyncapi.yaml"
WS_DOCS_FILE = DOCS_DIR / "ws-docs.html"


def _read_docs_file(path: Path) -> str:
    """docs/ 안의 파일을 읽어 옵니다. 없으면 이유를 분명히 알려줍니다."""
    try:
        return path.read_text(encoding="utf-8")
    except FileNotFoundError:
        # 조용히 빈 화면을 주면 "왜 안 나오지?"로 한참 헤매게 됩니다.
        raise HTTPException(status_code=500, detail=f"{path.name} 파일이 없습니다")


@app.get("/asyncapi.yaml", response_class=PlainTextResponse, tags=["웹소켓 명세"])
def asyncapi_yaml():
    """웹소켓 명세 원본(YAML)을 그대로 돌려줍니다.

    `/openapi.json` 과 같은 자리의 "기계가 읽는 계약서"입니다.
    """
    return PlainTextResponse(
        _read_docs_file(ASYNCAPI_FILE),
        media_type="application/yaml; charset=utf-8",
    )


@app.get("/asyncapi.json", tags=["웹소켓 명세"])
def asyncapi_json():
    """같은 명세를 JSON 으로 돌려줍니다.

    YAML 과 JSON 은 **같은 내용을 적는 두 가지 표기법**입니다. 사람이 쓰기엔
    YAML 이 편하고, 브라우저·프로그램이 읽기엔 JSON 이 편해서 둘 다 냅니다.
    원본은 어디까지나 YAML 파일 하나뿐이라 서로 어긋날 일이 없습니다.
    """
    return yaml.safe_load(_read_docs_file(ASYNCAPI_FILE))


@app.get("/ws-docs", response_class=HTMLResponse, tags=["웹소켓 명세"])
def ws_docs():
    """웹소켓 명세를 눈으로 보는 화면. (스와거의 `/docs` 에 해당)

    이 화면은 내용을 스스로 갖고 있지 않고, `/asyncapi.json` 을 읽어서
    그리기만 합니다. 그래서 `docs/asyncapi.yaml` 만 고치면 화면이 따라옵니다.
    내용이 두 군데로 갈라지지 않게 하려는 것입니다.
    """
    return HTMLResponse(_read_docs_file(WS_DOCS_FILE))
