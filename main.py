# ─────────────────────────────────────────────────────────────
# 스크래블 백엔드 — 기본용 (FastAPI)
#
# FastAPI는 코드를 짜면 자동으로 "스와거(Swagger)" 문서 화면을
# 만들어 줍니다. 브라우저에서 /docs 로 들어가면 API를 눈으로 보고
# 직접 눌러볼 수 있습니다.
#
# 실행:  .venv/bin/uvicorn main:app --host 0.0.0.0 --port 11000
#   - 리턴값 보기 : http://localhost:11000/
#   - 프론트가 호출: http://localhost:11000/api/hello
#   - 스와거 문서 : http://localhost:11000/docs
#   - API 계약서  : http://localhost:11000/openapi.json
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

import sentry
from db import get_connection

# 에러 추적을 **앱을 만들기 전에** 켭니다.
#
# 순서가 중요합니다. Sentry 는 켜질 때 FastAPI 에 자기 부품을 끼워 넣는데,
# 앱이 이미 만들어진 뒤에 켜면 그 부품이 들어갈 자리를 놓칩니다.
# 그러면 오류가 나도 조용히 안 올라갑니다.
#
# `SENTRY_DSN` 환경변수가 없으면 아무 일도 안 일어납니다.
SENTRY_ON = sentry.setup()
from dictionary import MIN_WORD_LENGTH, WORD_COUNT, is_word
from game_data import (
    BLANK,
    BOARD_LAYOUT,
    BOARD_SIZE,
    CENTER,
    PREMIUM_LEGEND,
    RACK_SIZE,
    TILE_DISTRIBUTION,
    TILE_POINTS,
    TOTAL_TILES,
    build_bag,
)

# 스와거(`/docs`) 첫 화면에 뜨는 설명입니다. 마크다운이 그대로 그려집니다.
#
# 여기에 **웹소켓 안내를 크게 적어 두는 이유**: 스와거는 HTTP API 만
# 자동으로 그립니다. `@app.websocket()` 으로 만든 경로는 아무리 많이
# 만들어도 이 화면에 한 줄도 나오지 않습니다.
#
# 그래서 스와거만 본 사람은 이 백엔드에 방·채팅·게임 시작이 있다는 사실을
# **알 방법이 없습니다.** 실제로 지금 기능의 대부분이 웹소켓 쪽에 있는데
# 스와거에는 플레이어 API 다섯 개만 보입니다. 그 오해를 막는 게 이 글의
# 역할입니다.
API_DESCRIPTION = """
스크래블 백엔드입니다. **이 화면(스와거)에는 HTTP API 만 나옵니다.**

## ⚠️ 이 백엔드 기능의 대부분은 이 화면에 없습니다

방 만들기 · 코드로 입장 · 랜덤 매칭 · 1:1 채팅 · **게임 시작** 은 전부
**웹소켓**으로 되어 있습니다. 웹소켓은 스와거가 자동으로 그려주지 못해서
(FastAPI 가 `@app.websocket()` 경로를 `/openapi.json` 에 넣지 않습니다)
**여기에 한 줄도 나오지 않습니다.**

### 👉 웹소켓 문서는 여기입니다

| 무엇 | 주소 | 스와거로 치면 |
|------|------|---------------|
| 눈으로 보는 화면 | [`/ws-docs`](/ws-docs) | 이 화면(`/docs`) 자리 |
| 기계가 읽는 계약서 | [`/asyncapi.json`](/asyncapi.json) | `/openapi.json` 자리 |
| 사람이 읽는 설명 | `docs/ws-contract.md` | — |

**프론트엔드 담당은 `/docs` 와 `/ws-docs` 를 둘 다 봐야 합니다.**
한쪽만 보면 절반을 놓칩니다.

## 지금 있는 웹소켓 통로

| 주소 | 하는 일 |
|------|---------|
| `/ws/rooms` | 방 만들고 기다리기 (방장) |
| `/ws/rooms/{code}` | 초대 코드로 들어가기 (친구) |
| `/ws/match` | 코드 없이 랜덤 매칭 |
| `/ws` | 연결 확인용 (메아리) |

**게임 시작**은 위 통로 위에서 오가는 메시지입니다. 방장이 `{"type":"start"}`
를 보내면 양쪽에 `game_started` 가 가고, **칩 7개씩**이 함께 실려 옵니다.
자세한 내용은 [`/ws-docs`](/ws-docs) 를 보세요.

## 📌 문서 파일을 복사해 가지 마세요

이 화면(`/docs`)과 [`/ws-docs`](/ws-docs) 는 **요청받을 때마다 새로 그려집니다.**
여기 보이는 것이 **항상 지금 백엔드의 약속**입니다.

- `/docs` — 코드에서 **자동 생성**됩니다. 백엔드가 API 를 바꾸면 즉시 따라옵니다.
- `/ws-docs` — `docs/asyncapi.yaml` 을 **그때그때 읽어서** 그립니다.

저장소의 `.md` 파일을 받아 두면 **받은 순간부터 낡기 시작하고**, 백엔드가
바꿔도 알 방법이 없습니다. 두 주소를 **북마크해 두고 그때그때 보세요.**

> 계약이 바뀌면 이 두 화면이 먼저 바뀝니다. 별도 연락을 기다릴 필요가 없습니다.
"""

# 스와거는 태그(묶음)마다 설명을 달 수 있습니다. 경로 목록 바로 위에
# 뜨기 때문에, 웹소켓 안내를 한 번 더 눈에 띄게 둘 수 있는 자리입니다.
OPENAPI_TAGS = [
    {
        "name": "플레이어",
        "description": "닉네임을 더하고, 보고, 고치고, 지웁니다. 요청하면 답하는 **HTTP API** 입니다.",
    },
    {
        "name": "게임",
        "description": (
            "게임의 **고정된 규칙**입니다. 칩(타일) 구성과 보드 배열처럼 "
            "방마다 달라지지 않는 값이라, 프론트엔드가 시작할 때 한 번만 "
            "받아 두면 됩니다.\n\n"
            "게임을 실제로 **진행하는 것**(칩 나눠주기·단어 놓기·점수)은 "
            "웹소켓 쪽입니다. 아래 「웹소켓 명세」를 보세요."
        ),
    },
    {
        "name": "웹소켓 명세",
        "description": (
            "**웹소켓 기능은 이 화면에 나오지 않습니다.** 아래 주소로 가야 볼 수 있습니다.\n\n"
            "방 만들기 · 코드로 입장 · 랜덤 매칭 · 1:1 채팅 · **게임 시작"
            "(`start` → `game_started`)** 이 전부 거기 적혀 있습니다.\n\n"
            "👉 사람이 보는 화면: [`/ws-docs`](/ws-docs)"
        ),
    },
]

app = FastAPI(
    title="스크래블 백엔드",
    description=API_DESCRIPTION,
    version="0.1.0",
    openapi_tags=OPENAPI_TAGS,
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


@app.post("/api/players", response_model=PlayerOut, status_code=201, tags=["플레이어"])
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


@app.get("/api/players", response_model=List[PlayerOut], tags=["플레이어"])
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


@app.get("/api/players/check-nickname", response_model=NicknameCheckOut, tags=["플레이어"])
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


@app.put("/api/players/{player_id}", response_model=PlayerOut, tags=["플레이어"])
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


@app.delete("/api/players/{player_id}", response_model=PlayerOut, tags=["플레이어"])
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
@sentry.catch_ws
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

        # 방장이 "시작"을 눌렀는가.
        #
        # DB 의 `rooms.started_at` 에도 같은 사실이 남지만, 여기에도 두는
        # 이유는 **매번 물어보지 않기 위해서**입니다. "이미 시작했나?"는
        # 시작 요청이 올 때마다 확인해야 하는데, 그때마다 DB 에 다녀오면
        # 그 사이에 다른 사람의 처리가 끼어들 수 있습니다.
        # 지금 켜져 있는 이 방의 상태는 메모리가 가장 빠르고 정확합니다.
        self.started = False

        # 이번 게임에서 누가 먼저 두는가. 아직 시작 전이면 None.
        self.first_turn: Optional[str] = None

        # 지금 누구 차례인가. `True` 면 방장, `False` 면 친구, `None` 이면
        # 아직 시작 전입니다.
        #
        # 닉네임이 아니라 **자리(방장/친구)로** 들고 있는 이유:
        # 두 사람이 둘 다 "수진"일 수 있습니다. 닉네임으로 차례를 따지면
        # 그때 **상대 차례에도 내가 놓을 수 있게** 됩니다. 이름은 겹쳐도
        # 자리는 겹치지 않습니다.
        self.turn_is_host: Optional[bool] = None

        # ── 이번 판의 칩 ────────────────────────────────────
        #
        # 아직 아무에게도 가지 않은 타일들. 시작할 때 100개를 섞어 넣고,
        # 각자 7개씩 가져가면 86개가 남습니다.
        self.bag: List[str] = []

        # 각자 손에 들고 있는 칩.
        #
        # 닉네임이 아니라 **방장/친구 자리**로 나눠 둡니다. 둘 다 "수진"일
        # 수 있어서 닉네임을 열쇠로 쓰면 두 사람의 칩이 한 칸에 섞입니다.
        self.host_rack: List[str] = []
        self.guest_rack: List[str] = []

        # 판에서 **빈 타일로 놓인 자리들** `{(row, col), ...}`.
        #
        # 판(`board`)은 글자만 기억합니다. 빈 타일을 `S` 로 놓으면 판에는
        # `S` 라고만 남아서, 나중에 그 칸을 지나는 단어를 셀 때 **진짜 S
        # 처럼 1점을 매기게 됩니다.** 빈 타일은 언제나 0점이라 틀린 값입니다.
        #
        # 판에 `S*` 처럼 표시를 섞지 않고 따로 두는 이유: 그러면 판을 읽는
        # 곳마다 "별표를 떼고 봐야 하나"를 신경 써야 합니다. 글자는 글자대로
        # 두고, 성격은 옆에 적어 두는 편이 단순합니다.
        self.blank_spots = set()

        # 지금 판에 무엇이 놓여 있는가. 15×15 이고 빈 칸은 빈 문자열입니다.
        #
        # **두 사람이 함께 보는 판은 하나뿐**이고, 그 하나가 여기입니다.
        # 각자 화면에만 기억하면 둘이 서로 다른 판을 보게 되는데, 그때
        # 어느 쪽이 맞는지 판단할 방법이 없습니다.
        #
        # `game_data.BOARD_LAYOUT`(글자 2배 칸 등)과는 **다른 것**입니다.
        # 저쪽은 절대 안 바뀌는 규칙이고, 이쪽은 매 수마다 바뀌는 상태입니다.
        # 한 표에 섞으면 게임이 끝날 때마다 규칙을 다시 만들어야 합니다.
        self.board: List[List[str]] = new_board()

        # 지금까지 쌓인 점수. 매 수마다 더해집니다.
        #
        # 칩과 마찬가지로 **자리(방장/친구)로** 나눠 둡니다. 닉네임을
        # 열쇠로 쓰면 이름이 같을 때 두 사람 점수가 한 칸에 합쳐집니다.
        self.host_score = 0
        self.guest_score = 0

        # 게임이 끝났는가. 끝난 판에는 더 놓을 수 없습니다.
        #
        # `started` 를 False 로 되돌리지 않고 따로 두는 이유: 그러면
        # "아직 시작 안 함"과 "이미 끝남"이 같은 상태가 되어, 끝난 판에
        # 놓으려 할 때 "아직 시작되지 않았습니다"라는 엉뚱한 답을 하게
        # 됩니다. 사용자는 방금 게임을 끝냈는데 말이죠.
        self.finished = False

        # 아무도 칩을 안 내고 넘어간 턴이 몇 번 이어졌는가.
        #
        # 낼 수 있는 단어가 없으면 서로 넘기기만 하다가 게임이 영영
        # 안 끝납니다. 연속으로 쌓이면 끝냅니다.
        # **누가 하나라도 놓으면 0으로 되돌아갑니다.** 연속이 아니면
        # 세는 의미가 없기 때문입니다.
        self.passes = 0

    @property
    def turn_nickname(self) -> Optional[str]:
        """지금 차례인 사람의 닉네임. **화면에 보여줄 때만** 씁니다.

        판단에는 쓰지 마세요. 두 사람 이름이 같으면 구별이 안 됩니다.
        누구 차례인지 따질 때는 `turn_is_host` 를 씁니다.
        """
        if self.turn_is_host is None:
            return None
        return self.host_nickname if self.turn_is_host else self.guest_nickname

    def clear_game(self) -> None:
        """이번 판을 없던 것으로 되돌립니다.

        게임이 끝났거나(상대가 나감) 시작에 실패했을 때 씁니다. 지울 것을
        한 군데 모아 두는 이유: 나중에 게임 상태가 늘어날 때마다 "여기서도
        지워야 하나?"를 여러 곳에서 따지게 되는데, 한 군데를 빠뜨리면
        **지난 판의 칩이 다음 판에 섞여 들어옵니다.**
        """
        self.started = False
        self.first_turn = None
        self.turn_is_host = None
        self.bag = []
        self.host_rack = []
        self.guest_rack = []
        self.host_score = 0
        self.guest_score = 0
        self.finished = False
        self.passes = 0
        self.blank_spots = set()
        # 판도 비웁니다. 안 비우면 지난 판에 놓인 글자 위에서 새 게임이
        # 시작돼, 첫 수부터 "이미 글자가 있는 칸"이라고 막힙니다.
        self.board = new_board()


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


# 접속했을 때 되돌려 주는 지난 대화의 최대 줄 수.
#
# 전부 보내면 오래된 방일수록 접속이 느려지고, 화면도 옛날 이야기부터
# 그리게 됩니다. 사람이 거슬러 올라가 읽는 양은 이 정도면 충분합니다.
HISTORY_LIMIT = 100


def load_messages(room_id: int) -> List[dict]:
    """그 방에서 오간 지난 대화를 **시간 순서로** 꺼내 옵니다.

    최근 것부터 `HISTORY_LIMIT` 개를 가져온 뒤 **다시 뒤집어** 오래된
    것부터 돌려줍니다. 최근 것을 고르려면 내림차순으로 꺼내야 하지만,
    화면에 그릴 때는 위에서 아래로 시간이 흘러야 하기 때문입니다.
    """
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT sender, text, created_at FROM messages"
                " WHERE room_id = %s ORDER BY id DESC LIMIT %s",
                (room_id, HISTORY_LIMIT),
            )
            rows = cur.fetchall()

    return [
        {"from": sender, "text": text, "at": created_at.isoformat()}
        for sender, text, created_at in reversed(rows)
    ]


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


# ─────────────────────────────────────────────────────────────
# 게임 시작
#
# 두 사람이 다 모였다고 게임이 저절로 시작되지는 않습니다. 들어오자마자
# 판이 시작되면 준비할 틈이 없기 때문입니다. **방장이 "시작"을 눌러야**
# 비로소 시작됩니다.
#
# 왜 방장만 누를 수 있나: 둘 다 누를 수 있으면 거의 동시에 눌렀을 때
# 게임이 두 번 시작될 수 있고, 무엇보다 "언제 시작할지"를 정하는 사람이
# 둘이면 아무도 정하지 못합니다. 한 명에게 맡기는 편이 단순합니다.
#
# 방장이 누구인가:
#   코드로 만난 방  → 방을 만든 사람 (`/ws/rooms` 로 접속한 쪽)
#   랜덤 매칭       → 먼저 와서 기다린 사람 (`pair_up` 의 `first`)
# 어느 쪽이든 `LiveRoom.host` 에 그 사람의 연결이 들어 있어서, 굳이
# 나눠서 처리하지 않아도 됩니다.
#
# 시작하면 **칩을 7개씩 나눠 줍니다.** 100개를 섞어 가방에 넣고 각자
# 7개씩 가져가면 86개가 남습니다.
#
# ⚠️ 여기까지가 "시작"입니다. 판에 단어를 놓거나 점수를 매기는 일은
#    아직 없습니다. 그건 각각 따로 만들 기능입니다.
# ─────────────────────────────────────────────────────────────

# 칩을 섞는 데 쓸 주사위.
#
# 그냥 `random` 이 아니라 `secrets` 쪽을 쓰는 이유: `random` 으로 섞은
# 순서는 예측할 수 있습니다. 가방 순서를 예측당하면 **상대가 다음에 뽑을
# 칩을 미리 알게 됩니다.** 초대 코드에 `secrets` 를 쓴 것과 같은 이유입니다.
_shuffler = secrets.SystemRandom()


def deal_tiles(room: LiveRoom) -> None:
    """칩 100개를 섞어 **각자 7개씩** 나눠 주고, 나머지는 방 가방에 둡니다.

    `game_data.build_bag()` 은 항상 같은 순서(E 부터 쭉)로 주기 때문에
    **반드시 섞어야 합니다.** 안 섞으면 매 게임 두 사람 모두 E 만 일곱 개를
    받습니다.

    뒤에서부터 꺼내는(`pop`) 이유: 앞에서 꺼내면 남은 것을 매번 한 칸씩
    앞으로 당겨야 합니다. 이미 섞여 있으니 어느 쪽 끝에서 꺼내든 무작위인
    것은 같고, 뒤에서 꺼내는 편이 그냥 더 쌉니다.
    """
    bag = build_bag()
    _shuffler.shuffle(bag)

    room.host_rack = [bag.pop() for _ in range(RACK_SIZE)]
    room.guest_rack = [bag.pop() for _ in range(RACK_SIZE)]
    room.bag = bag


# ─────────────────────────────────────────────────────────────
# 보드 상태와 단어 제출
#
# 서버가 **판을 기억합니다.** 지금 어느 칸에 무슨 글자가 놓여 있는지를
# 방마다 들고 있고, 인정된 단어는 실제로 그 판에 올립니다.
#
# 왜 서버가 기억해야 하는가:
#   두 사람이 같은 판을 봅니다. 각자 자기 화면에만 기억하면 둘이 서로
#   다른 판을 보게 되고, 어느 쪽이 맞는지 판단할 방법이 없습니다.
#   **판은 하나뿐이어야 하고, 그 하나는 서버에 있어야 합니다.**
#
#   판을 기억하기 전에는 제출한 글자들만 단어로 읽었습니다. 그래서
#   두 번째 단어부터는 검증 자체가 성립하지 않았습니다. 스크래블은
#   이미 놓인 글자에 이어 붙이는 게임이기 때문입니다.
#
# 판에 놓을 때 지켜야 하는 규칙:
#   ① 이미 글자가 있는 칸에는 못 놓는다
#   ② 첫 수는 **한가운데(별표)를 지나야** 한다
#   ③ 두 번째부터는 **이미 놓인 글자에 닿아야** 한다 (따로 떨어져 못 놓음)
#   ④ 한 줄로, 사이가 비지 않게 (사이를 **이미 놓인 글자가 메우는 건 됨**)
#   ⑤ 이번 수로 **새로 생기는 단어가 전부** 사전에 있어야 한다
#
# ⑤ 가 중요합니다. 가로로 한 단어를 놓아도, 그 글자들이 위아래 글자와
# 붙으면서 **세로 단어가 여러 개 새로 생깁니다.** 그것들도 전부 진짜
# 단어여야 합니다. 안 그러면 판이 금방 엉터리 글자로 채워집니다.
#
# ⚠️ 아직 안 하는 것:
#      · 손에 그 칩을 정말 들고 있는지 확인 (없는 글자도 놓입니다)
#      · 놓은 만큼 칩을 다시 뽑기
#      · 점수 계산
#      · 차례 지키기 (지금은 아무나 아무 때나 놓을 수 있습니다)
# ─────────────────────────────────────────────────────────────

# 빈 칸을 나타내는 값. 보드는 15×15 이고, 글자가 없는 칸은 빈 문자열입니다.
EMPTY = ""


def new_board() -> List[List[str]]:
    """아무것도 안 놓인 새 판을 만듭니다.

    줄마다 **따로** 만드는 게 중요합니다. `[[EMPTY] * 15] * 15` 로 만들면
    같은 줄 하나를 열다섯 번 가리키게 되어, 한 칸에 글자를 놓으면
    **열다섯 줄에 동시에 나타납니다.**
    """
    return [[EMPTY] * BOARD_SIZE for _ in range(BOARD_SIZE)]


class SubmitError(ValueError):
    """제출을 받아줄 수 없을 때. 메시지를 그대로 사용자에게 보냅니다."""


def parse_tiles(tiles: object) -> List[tuple]:
    """보내온 좌표 목록의 **모양**을 확인하고 `(row, col, letter)` 로 정리합니다.

    받는 모양:
        [{"row": 7, "col": 7, "letter": "C"}, ...]

    `row` 는 위에서부터, `col` 은 왼쪽부터 **0 부터** 셉니다.
    `GET /api/game/setup` 의 `board[줄][칸]` 과 같은 방식입니다.

    여기서는 **판을 보지 않습니다.** 좌표 자체가 말이 되는지만 봅니다.
    판과 맞춰 보는 일은 `check_placement` 이 합니다. 나눠 두면 "보낸 값이
    이상한 것"과 "판에 놓을 수 없는 것"을 따로 설명해 줄 수 있습니다.
    """
    if not isinstance(tiles, list) or not tiles:
        raise SubmitError("놓은 칩이 없습니다")

    if len(tiles) > RACK_SIZE:
        # 손에 7개뿐이라 한 번에 8개를 놓을 수는 없습니다.
        raise SubmitError(f"한 번에 {RACK_SIZE}개까지만 놓을 수 있습니다")

    placed = []
    seen = set()
    for tile in tiles:
        if not isinstance(tile, dict):
            raise SubmitError('칩은 {"row":7,"col":7,"letter":"C"} 모양이어야 합니다')

        row, col, letter = tile.get("row"), tile.get("col"), tile.get("letter")

        # bool 은 파이썬에서 int 로도 통해서, True 를 좌표로 넘기면 1 로
        # 읽힙니다. 조용히 통과하면 엉뚱한 칸이 되므로 막습니다.
        if (
            not isinstance(row, int) or isinstance(row, bool)
            or not isinstance(col, int) or isinstance(col, bool)
        ):
            raise SubmitError("row 와 col 은 정수여야 합니다")

        if not (0 <= row < BOARD_SIZE and 0 <= col < BOARD_SIZE):
            raise SubmitError(
                f"보드 밖입니다. row·col 은 0~{BOARD_SIZE - 1} 사이여야 합니다"
            )

        if (
            not isinstance(letter, str) or len(letter) != 1
            or not letter.isascii() or not letter.isalpha()
        ):
            # 빈 타일(`?`)을 그대로 보내면 여기서 걸립니다. 빈 타일은
            # **무슨 글자로 쓸지 정해서** 그 글자를 보내야 합니다.
            # `?` 인 채로는 무슨 단어인지 판단할 수가 없습니다.
            raise SubmitError(
                "letter 는 알파벳 한 글자여야 합니다. "
                "빈 타일은 쓸 글자를 정해서 보내주세요"
            )

        if (row, col) in seen:
            # 같은 칸에 두 장을 놓을 수는 없습니다. 막지 않으면 뒤엣것이
            # 앞엣것을 덮어써서, 사용자가 보낸 것과 다른 단어가 됩니다.
            raise SubmitError("같은 칸에 두 번 놓았습니다")
        seen.add((row, col))

        # 이 자리에 놓은 게 **빈 타일인가.**
        #
        # 프론트엔드가 알려주지 않으면 서버는 알 수 없습니다. `S` 만 보고는
        # 진짜 S 를 놓은 건지 빈 타일을 S 로 쓴 건지 구분이 안 됩니다.
        # 그런데 **빈 타일은 0점**이라 이걸 모르면 점수가 틀립니다.
        #
        # 안 보내면 진짜 글자로 봅니다. 손에 그 글자가 없으면 그때만
        # 빈 타일을 쓴 것으로 처리합니다. (그것 말고는 놓을 방법이 없으니까요)
        is_blank = bool(tile.get("blank", False))

        placed.append((row, col, letter.upper(), is_blank))

    return placed


def check_placement(board: List[List[str]], placed: List[tuple]) -> str:
    """판에 놓을 수 있는 자리인지 보고, 방향(`across`/`down`)을 돌려줍니다.

    놓을 수 없으면 `SubmitError` 를 냅니다.
    """
    # ① 이미 글자가 있는 칸에는 못 놓습니다.
    for row, col, *_ in placed:
        if board[row][col] != EMPTY:
            raise SubmitError(
                f"이미 글자가 있는 칸입니다 ({row}, {col}): {board[row][col]}"
            )

    rows = {r for r, _c, *_ in placed}
    cols = {c for _r, c, *_ in placed}

    # ④-1 한 줄로 놓여야 합니다.
    #
    # 칩이 하나뿐이면 가로인지 세로인지 정할 수 없는데, 그건 문제가
    # 아닙니다. 한 칸짜리는 위아래·양옆 어느 쪽으로든 이미 놓인 글자에
    # 붙어서 단어를 만들 수 있고, 어느 쪽으로 붙었는지는 나중에
    # `words_formed` 가 알아서 찾아냅니다. 일단 가로로 봅니다.
    if len(rows) == 1:
        direction = "across"
    elif len(cols) == 1:
        direction = "down"
    else:
        raise SubmitError("한 줄로(가로 또는 세로) 놓아야 합니다")

    # ④-2 사이가 비면 안 됩니다.
    #
    # 다만 **이미 판에 놓인 글자가 사이를 메우는 것은 됩니다.** 그게
    # 스크래블에서 단어를 이어 붙이는 방식입니다.
    # (예: 판에 A 가 있을 때 C 와 T 를 양옆에 놓아 CAT 을 만드는 것)
    if direction == "across":
        row = next(iter(rows))
        line = sorted(cols)
        gaps = [
            c for c in range(line[0], line[-1] + 1)
            if c not in cols and board[row][c] == EMPTY
        ]
    else:
        col = next(iter(cols))
        line = sorted(rows)
        gaps = [
            r for r in range(line[0], line[-1] + 1)
            if r not in rows and board[r][col] == EMPTY
        ]
    if gaps:
        raise SubmitError("칩 사이가 비어 있습니다. 붙여서 놓아주세요")

    board_empty = all(cell == EMPTY for line_ in board for cell in line_)

    if board_empty:
        # ② 첫 수는 한가운데(별표)를 지나야 합니다. 이 규칙이 없으면
        #    구석에서 시작할 수 있고, 그러면 보드 가운데의 점수 칸들이
        #    아무 의미가 없어집니다.
        if not any(r == CENTER and c == CENTER for r, c, *_ in placed):
            raise SubmitError(
                f"첫 단어는 한가운데({CENTER}, {CENTER})를 지나야 합니다"
            )
    else:
        # ③ 두 번째부터는 이미 놓인 글자에 **닿아야** 합니다. 따로 떨어져
        #    놓을 수 있으면 한 판에 서로 상관없는 단어가 흩어지게 되는데,
        #    그건 스크래블이 아닙니다.
        touching = False
        for row, col, *_ in placed:
            for dr, dc in ((-1, 0), (1, 0), (0, -1), (0, 1)):
                r, c = row + dr, col + dc
                if 0 <= r < BOARD_SIZE and 0 <= c < BOARD_SIZE and board[r][c] != EMPTY:
                    touching = True
                    break
            if touching:
                break
        if not touching:
            raise SubmitError("이미 놓인 글자에 붙여서 놓아야 합니다")

    return direction


def _read_line(board: List[List[str]], row: int, col: int, step: tuple) -> dict:
    """한 칸에서 시작해 **양쪽 끝까지** 글자를 따라가 단어 하나를 읽습니다.

    `step` 은 진행 방향입니다. `(0, 1)` 이면 가로, `(1, 0)` 이면 세로.

    두 글자가 안 되면 단어가 아니므로 `None` 을 돌려줍니다.
    (한 글자만 덩그러니 있는 것은 단어로 치지 않습니다)
    """
    dr, dc = step

    # 시작점을 찾을 때까지 뒤로 갑니다.
    r, c = row, col
    while (
        0 <= r - dr < BOARD_SIZE and 0 <= c - dc < BOARD_SIZE
        and board[r - dr][c - dc] != EMPTY
    ):
        r, c = r - dr, c - dc

    # 이제 끝까지 앞으로 가며 글자를 모읍니다.
    tiles = []
    while 0 <= r < BOARD_SIZE and 0 <= c < BOARD_SIZE and board[r][c] != EMPTY:
        tiles.append({"row": r, "col": c, "letter": board[r][c]})
        r, c = r + dr, c + dc

    if len(tiles) < MIN_WORD_LENGTH:
        return None
    return {"word": "".join(t["letter"] for t in tiles), "tiles": tiles}


def words_formed(
    board: List[List[str]], placed: List[tuple], direction: str
) -> List[dict]:
    """이번 수로 **새로 생기는 단어를 전부** 찾습니다.

    하나가 아닙니다. 가로로 한 단어를 놓아도, 놓은 글자마다 위아래
    글자와 붙으면서 **세로 단어가 새로 생길 수 있습니다.** 그것들도
    전부 진짜 단어여야 합니다.

    `board` 는 **이미 새 글자가 올라간 판**이어야 합니다.
    """
    along = (0, 1) if direction == "across" else (1, 0)
    across_ = (1, 0) if direction == "across" else (0, 1)

    found = []
    seen = set()

    def add(word):
        if word is None:
            return
        # 같은 단어를 두 번 세지 않도록 자리로 구분합니다. 판에 같은
        # 단어가 두 군데 있을 수 있어서 글자만으로는 구분이 안 됩니다.
        key = (word["tiles"][0]["row"], word["tiles"][0]["col"], word["word"])
        if key not in seen:
            seen.add(key)
            found.append(word)

    # 놓은 방향으로 이어지는 **주 단어** 하나.
    row, col = placed[0][0], placed[0][1]
    add(_read_line(board, row, col, along))

    # 놓은 글자 하나하나가 만드는 **교차 단어**들.
    for row, col, *_ in placed:
        add(_read_line(board, row, col, across_))

    return found


# ─────────────────────────────────────────────────────────────
# 손패 관리 — 쓴 칩을 빼고, 그만큼 다시 뽑는다
#
# 놓은 만큼 가방에서 채워 넣어야 손에 늘 7개가 있습니다. 안 채우면
# 몇 수 만에 손이 비어서 게임이 멈춥니다.
#
# 채우려면 **먼저 빼야** 하고, 빼려면 **그 칩을 정말 갖고 있는지**
# 확인해야 합니다. 확인 없이 빼면 손에 없는 글자를 놓고도 손패가
# 줄어드는 이상한 일이 생깁니다. 그래서 세 가지가 한 덩어리입니다.
# ─────────────────────────────────────────────────────────────


def take_from_rack(rack: List[str], placed: List[tuple]) -> tuple:
    """손패에서 쓸 칩을 골라 냅니다. `(쓰고 남은 손패, 실제로 쓴 칩)`.

    없는 칩을 놓으려 하면 `SubmitError` 를 냅니다.

    **빈 타일 처리:** 프론트엔드는 빈 타일을 `S` 처럼 **정한 글자로**
    보냅니다(`?` 로 보내면 무슨 단어인지 알 수 없으니까요). 그래서 서버는
    "S 를 놓았다"만 보고 그게 진짜 S 였는지 빈 타일이었는지 알 수 없습니다.

    그래서 **진짜 글자를 먼저 쓰고, 없을 때만 빈 타일을 씁니다.**
    빈 타일은 아무 글자로나 쓸 수 있어서 아껴 두는 게 이득이고, 사람도
    그렇게 씁니다. 진짜 S 가 있는데 굳이 빈 타일을 S 로 쓰는 사람은 없습니다.

    ⚠️ 다만 이 방식으로는 **나중에 점수를 매길 때** 그 칸이 빈 타일이었는지
    (0점) 진짜 글자였는지 구분할 수 없습니다. 점수 기능을 만들 때
    프론트엔드가 "이건 빈 타일이다"를 함께 보내도록 계약을 늘려야 합니다.
    """
    remaining = list(rack)
    used = []

    for _row, _col, letter, is_blank in placed:
        if is_blank:
            # 프론트엔드가 **빈 타일이라고 알려준** 경우입니다. 이때는
            # 진짜 글자가 손에 있어도 빈 타일을 씁니다. 사용자가 그렇게
            # 정한 것이니 서버가 뒤집으면 안 됩니다.
            if BLANK not in remaining:
                raise SubmitError("손에 빈 타일이 없습니다")
            remaining.remove(BLANK)
            used.append(BLANK)
        elif letter in remaining:
            remaining.remove(letter)
            used.append(letter)
        elif BLANK in remaining:
            # 진짜 글자가 없으니 빈 타일을 그 글자로 쓴 것입니다.
            # (프론트엔드가 표시를 안 보냈지만 이것 말고는 방법이 없습니다)
            remaining.remove(BLANK)
            used.append(BLANK)
        else:
            raise SubmitError(f"손에 없는 칩입니다: {letter}")

    return remaining, used


def draw_tiles(bag: List[str], count: int) -> List[str]:
    """가방에서 `count` 개를 꺼냅니다. 모자라면 **있는 만큼만** 줍니다.

    모자란 것은 고장이 아닙니다. 게임 막바지에는 원래 가방이 바닥나고,
    그때부터는 손에 남은 것으로만 둡니다. 여기서 에러를 내면 게임이
    끝나갈 때마다 멈춰버립니다.

    가방은 나눠 줄 때 이미 섞여 있어서 다시 섞지 않습니다. 뒤에서부터
    꺼내는 것도 그때와 같은 이유입니다.
    """
    return [bag.pop() for _ in range(min(count, len(bag)))]


# ─────────────────────────────────────────────────────────────
# 점수 계산
#
# 세 가지를 더합니다.
#   ① 글자 점수  — 타일마다 정해진 점수 (E=1, Q=10 …)
#   ② 보너스 칸  — 글자 2배·3배, 단어 2배·3배
#   ③ 한 번에 7개를 다 쓰면 **+50점** (스크래블에서 "빙고"라고 부릅니다)
#
# 순서가 중요합니다. **글자 배수를 먼저 다 적용한 뒤에 단어 배수를 겁니다.**
# 반대로 하면 글자 2배 칸의 효과까지 단어 배수에 곱해지지 않아 점수가
# 작게 나옵니다.
#
# 보너스 칸은 **이번에 새로 놓은 자리에서만** 적용됩니다. 이미 놓여 있던
# 글자가 밟고 있는 칸은 그때 이미 썼습니다. 안 그러면 같은 2배 칸을
# 지나가는 단어마다 계속 우려먹게 됩니다.
#
# 빈 타일은 **0점**입니다. 아무 글자로나 쓸 수 있는 대신 점수를 포기하는
# 것이 빈 타일의 거래 조건입니다.
# ─────────────────────────────────────────────────────────────

# 한 번에 손패를 다 쓰면 주는 보너스.
BINGO_BONUS = 50


def score_word(word: dict, fresh: set, blanks: set) -> int:
    """단어 하나의 점수를 냅니다.

    `fresh`  = 이번에 새로 놓은 자리들 `{(row, col), ...}`
    `blanks` = **판에 놓인 빈 타일 자리 전부.** 이번에 놓은 것뿐 아니라
               예전에 놓인 것도 들어 있어야 합니다. 빈 타일은 한 번
               놓이면 계속 0점이고, 나중에 그 칸을 지나는 단어에서도
               0점이어야 하기 때문입니다.
    """
    total = 0
    word_multipliers = []

    for tile in word["tiles"]:
        spot = (tile["row"], tile["col"])

        # 빈 타일은 0점입니다.
        points = 0 if spot in blanks else TILE_POINTS.get(tile["letter"], 0)

        # 보너스 칸은 **이번에 새로 놓은 자리에서만** 걸립니다.
        if spot in fresh:
            square = BOARD_LAYOUT[tile["row"]][tile["col"]]
            bonus = PREMIUM_LEGEND.get(square)
            if bonus:
                if bonus["applies_to"] == "letter":
                    points *= bonus["multiplier"]
                else:
                    # 단어 배수는 글자를 다 더한 뒤에 겁니다.
                    word_multipliers.append(bonus["multiplier"])

        total += points

    for multiplier in word_multipliers:
        total *= multiplier

    return total


def score_move(
    words: List[dict], placed: List[tuple], used: List[str], board_blanks=None
) -> dict:
    """이번 수의 점수를 냅니다.

    `words` 는 이번에 새로 생긴 단어 전부입니다. **하나가 아닐 수 있고,
    각각 따로 점수가 붙습니다.** 가로로 놓으면서 세로 단어가 같이
    생겼다면 그 세로 단어들도 전부 점수에 들어갑니다.

    `used` 는 손패에서 실제로 꺼낸 칩입니다. `placed` 와 순서가 같아서,
    몇 번째 자리가 빈 타일이었는지 여기서 알 수 있습니다.
    """
    fresh = {(row, col) for row, col, *_ in placed}

    # 이번에 빈 타일로 놓은 자리. `used` 는 손패에서 실제로 꺼낸 칩이라
    # `placed` 와 순서가 같습니다.
    new_blanks = {
        (placed[i][0], placed[i][1])
        for i, tile in enumerate(used)
        if tile == BLANK
    }
    # 판에 이미 놓여 있던 빈 타일까지 합쳐야 합니다. 안 그러면 예전에
    # 놓인 빈 타일이 지금 만들어지는 단어에서 진짜 글자로 계산됩니다.
    blanks = new_blanks | set(board_blanks or ())

    scored = [
        {"word": w["word"], "score": score_word(w, fresh, blanks)} for w in words
    ]
    words_total = sum(w["score"] for w in scored)

    # 손패 7개를 한 번에 다 쓰면 보너스. 어려운 일이라 크게 줍니다.
    bingo = BINGO_BONUS if len(placed) == RACK_SIZE else 0

    return {
        "words": scored,
        "words_score": words_total,
        "bingo": bingo,
        "total": words_total + bingo,
        # 이번에 빈 타일로 놓은 자리. 호출한 쪽이 판에 기억해 둘 수 있게
        # 함께 돌려줍니다.
        "_new_blanks": sorted(new_blanks),
    }


# ─────────────────────────────────────────────────────────────
# 게임 끝내기
#
# 끝나는 길이 두 가지입니다.
#   ① 정상 종료 — **가방이 비고, 누군가 손패를 다 썼을 때.**
#      더 뽑을 것도 없고 낼 것도 없으면 게임이 계속될 수 없습니다.
#   ② 나가기(기권) — 한 사람이 그만두겠다고 누를 때.
#
# 어떻게 끝나든 **승패는 쌓아온 점수만으로** 가립니다.
#
# 손에 남은 칩으로 점수를 깎는 정산은 **하지 않습니다.** 원래 스크래블에는
# 있는 규칙이지만, 이 프로젝트에서는 빼기로 정했습니다. 점수판에 보이던
# 숫자가 마지막에 갑자기 달라지지 않아서, 보고 있던 대로 승패가 납니다.
#
# 나가기만 예외입니다. 점수와 상관없이 **남은 사람이 이깁니다.**
# 그만둔 사람을 이기게 하면 지고 있을 때 나가버리는 게 이득이 됩니다.
#
# ⚠️ 연결을 그냥 끊는 것과는 다릅니다. 탭을 닫으면 지금까지처럼
#    `host_left`/`guest_left`/`partner_left` 가 가고 방이 정리됩니다.
#    나가기는 **연결을 유지한 채** 결과를 보고 다시 할 수 있게 합니다.
# ─────────────────────────────────────────────────────────────


def winner_by_score(room: LiveRoom) -> Optional[bool]:
    """쌓아온 점수로 이긴 쪽을 가립니다. `True` 방장 · `False` 친구 · `None` 비김.

    **손에 남은 칩은 보지 않습니다.** 점수판에 보이던 숫자가 그대로
    결과가 되므로, 마지막에 순위가 갑자기 뒤집히는 일이 없습니다.

    닉네임이 아니라 자리로 돌려주는 이유는 차례와 같습니다 — 두 사람
    이름이 같으면 닉네임만으로는 누가 이겼는지 알 수 없습니다.
    """
    if room.host_score > room.guest_score:
        return True
    if room.guest_score > room.host_score:
        return False
    return None


def record_end(code: str, kind: str, winner: Optional[str], host_score: int, guest_score: int):
    """끝난 판을 DB 에 기록하고, **DB 가 찍은 시각**을 돌려줍니다."""
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE rooms SET ended_at = now(), end_kind = %s, winner = %s,"
                " host_score = %s, guest_score = %s, status = 'finished'"
                " WHERE code = %s RETURNING ended_at",
                (kind, winner, host_score, guest_score, code),
            )
            row = cur.fetchone()
            return row[0] if row else None


async def end_game(
    room: LiveRoom, kind: str, winner_is_host: Optional[bool], quitter: Optional[str] = None
) -> None:
    """게임을 끝내고 **양쪽 모두에게** 결과를 알립니다.

    `kind`           `"finished"`(정상 종료) 또는 `"resigned"`(나가기)
    `winner_is_host` `True` 방장 승 · `False` 친구 승 · `None` 비김

    이긴 사람을 **닉네임이 아니라 자리로** 받습니다. 두 사람 이름이 같으면
    닉네임만으로는 누가 이겼는지 알 수 없기 때문입니다. 차례를 자리로
    들고 있는 것과 같은 이유입니다.
    """
    room.finished = True

    if winner_is_host is None:
        winner = None
    else:
        winner = room.host_nickname if winner_is_host else room.guest_nickname

    try:
        ended_at = await run_in_threadpool(
            record_end, room.code, kind, winner, room.host_score, room.guest_score
        )
    except Exception:
        # 기록에 실패해도 게임은 끝난 것으로 봅니다. 두 사람 화면에서는
        # 이미 끝났는데 서버만 계속 진행 중이라고 여기면 더 이상합니다.
        ended_at = None

    payload = {
        "type": "game_over",
        "reason": kind,
        "winner": winner,
        "scores": {"host": room.host_score, "guest": room.guest_score},
        "board": room.board,
        "at": ended_at.isoformat() if ended_at else None,
    }
    if quitter is not None:
        payload["by"] = quitter

    # `you_won` 은 사람마다 다릅니다. 이름이 같을 수 있어서 닉네임
    # 비교로는 내가 이겼는지 알 수 없기 때문입니다. 비겼으면 양쪽 다 None.
    await send_quietly(
        room.host,
        {**payload, "you_won": None if winner_is_host is None else winner_is_host},
    )
    await send_quietly(
        room.guest,
        {**payload, "you_won": None if winner_is_host is None else not winner_is_host},
    )


# 이만큼 연속으로 넘어가면 게임을 끝냅니다.
#
# 낼 수 있는 단어가 없을 때 서로 넘기기만 하면 게임이 영영 안 끝납니다.
# 두 번으로 하면 한 번씩만 막혀도 끝나버려서 너무 이르고, 크게 잡으면
# 아무도 못 내는 판을 한참 붙들고 있게 됩니다.
MAX_PASSES = 3


async def pass_turn(websocket: WebSocket, room: LiveRoom, sender: str) -> None:
    """턴 넘기기. 낼 칩이 없을 때 상대에게 차례를 넘깁니다.

    **세 번 연속으로 넘어가면 게임이 끝납니다.** 그때는 남은 칩을 따지지
    않고 **그 시점의 점수 그대로** 승패를 가립니다. 아무도 못 내는 판에서
    남은 칩으로 점수를 깎는 건 벌칙이 될 뿐입니다.
    """
    if room.finished:
        await websocket.send_json({"type": "error", "message": "이미 끝난 게임입니다"})
        return

    if not room.started or room.turn_is_host is None:
        await websocket.send_json(
            {"type": "error", "message": "아직 게임이 시작되지 않았습니다"}
        )
        return

    # 넘기는 것도 **자기 차례에만** 할 수 있습니다. 아니면 상대 차례를
    # 마음대로 넘겨버릴 수 있습니다.
    if (websocket is room.host) is not room.turn_is_host:
        await websocket.send_json(
            {
                "type": "error",
                "message": f"지금은 {room.turn_nickname}님 차례입니다",
                "turn": room.turn_nickname,
                "your_turn": False,
            }
        )
        return

    room.passes += 1
    room.turn_is_host = not room.turn_is_host

    update = {
        "type": "turn_passed",
        "by": sender,
        "turn": room.turn_nickname,
        "passes": room.passes,
        # 몇 번 더 넘기면 끝나는지. 화면에 "2번 더 넘기면 끝납니다"처럼
        # 미리 알려줄 수 있어야 갑자기 끝나지 않습니다.
        "passes_until_end": MAX_PASSES - room.passes,
        "scores": {"host": room.host_score, "guest": room.guest_score},
    }
    await send_quietly(room.host, {**update, "your_turn": room.turn_is_host is True})
    await send_quietly(room.guest, {**update, "your_turn": room.turn_is_host is False})

    if room.passes >= MAX_PASSES:
        await end_game(room, "passed", winner_is_host=winner_by_score(room))


def take_named_tiles(rack: List[str], names: object) -> tuple:
    """바꿀 칩을 손패에서 **이름 그대로** 골라 냅니다. `(남은 손패, 골라낸 칩)`.

    `take_from_rack` 과 다릅니다. 저쪽은 "이 글자를 놓겠다"라서 없으면
    빈 타일로 대신할 수 있지만, 여기는 **"이 칩을 내놓겠다"** 라서 대신할
    것이 없습니다. 손에 있는 그대로여야 합니다.

    그래서 빈 타일(`?`)도 그대로 적어 보냅니다. 빈 타일도 바꿀 수 있습니다.
    """
    if not isinstance(names, list) or not names:
        raise SubmitError("바꿀 칩을 골라주세요")

    if len(names) > RACK_SIZE:
        raise SubmitError(f"한 번에 {RACK_SIZE}개까지만 바꿀 수 있습니다")

    remaining = list(rack)
    taken = []
    for name in names:
        if not isinstance(name, str) or len(name) != 1:
            raise SubmitError("칩은 한 글자씩 적어주세요")
        name = name.upper()
        if name not in remaining:
            raise SubmitError(f"손에 없는 칩입니다: {name}")
        remaining.remove(name)
        taken.append(name)

    return remaining, taken


async def exchange_tiles(
    websocket: WebSocket, room: LiveRoom, sender: str, data: dict
) -> None:
    """손패의 칩을 가방의 새 칩과 바꿉니다. **차례를 씁니다.**

    낼 단어가 없을 때 쓰는 수입니다. 넘기기는 다음 차례에도 똑같이 막혀
    있지만, 교환은 손패를 바꿔서 상황 자체를 바꿉니다. 대신 한 턴을
    통째로 버리는 값을 치릅니다.
    """
    if room.finished:
        await websocket.send_json({"type": "error", "message": "이미 끝난 게임입니다"})
        return

    if not room.started or room.turn_is_host is None:
        await websocket.send_json(
            {"type": "error", "message": "아직 게임이 시작되지 않았습니다"}
        )
        return

    if (websocket is room.host) is not room.turn_is_host:
        await websocket.send_json(
            {
                "type": "error",
                "message": f"지금은 {room.turn_nickname}님 차례입니다",
                "turn": room.turn_nickname,
                "your_turn": False,
            }
        )
        return

    # 가방이 얼마 안 남았으면 바꿀 수 없습니다.
    #
    # 막바지에 서로 교환만 반복하면 게임이 영영 안 끝납니다. 원래
    # 스크래블도 같은 이유로 막습니다.
    if len(room.bag) < RACK_SIZE:
        await websocket.send_json(
            {
                "type": "error",
                "message": f"가방에 칩이 {RACK_SIZE}개 미만이면 바꿀 수 없습니다 (남은 {len(room.bag)}개)",
            }
        )
        return

    is_host = websocket is room.host
    my_rack = room.host_rack if is_host else room.guest_rack

    try:
        rest, given = take_named_tiles(my_rack, data.get("tiles"))
    except SubmitError as e:
        await websocket.send_json({"type": "error", "message": str(e)})
        return

    # **먼저 뽑고, 그다음 돌려놓습니다.**
    #
    # 순서가 반대면 방금 내놓은 칩을 그대로 다시 받을 수 있습니다.
    # 그러면 바꾼 게 아니라 한 턴만 버린 셈이 됩니다.
    drawn = draw_tiles(room.bag, len(given))

    # 내놓은 칩을 가방에 도로 넣고 섞습니다. 안 넣으면 그 칩들이 게임에서
    # 영영 사라져서, 100개라는 구성이 무너지고 "가방이 비었다"는 계산도
    # 틀어집니다.
    room.bag.extend(given)
    _shuffler.shuffle(room.bag)

    new_rack = rest + drawn
    if is_host:
        room.host_rack = new_rack
    else:
        room.guest_rack = new_rack

    # 칩을 안 냈으니 **넘기기와 똑같이 셉니다.**
    #
    # "3번 연속 넘어가면 끝"이라는 규칙은 아무도 못 내는 판이 안 끝나는
    # 걸 막으려는 것입니다. 교환만 반복해도 똑같이 안 끝나므로 함께
    # 세어야 규칙이 제 몫을 합니다.
    room.passes += 1
    room.turn_is_host = not room.turn_is_host

    # 바꾼 사람에게만: 새 손패와 새로 뽑은 칩.
    await websocket.send_json(
        {
            "type": "exchanged",
            "count": len(given),
            "rack": new_rack,
            "drawn": drawn,
            "tiles_left": len(room.bag),
        }
    )

    # 양쪽에게: **몇 개를 바꿨는지만.** 무엇을 내놓고 무엇을 받았는지는
    # 알려주지 않습니다. 그걸 알면 상대 손패를 좁혀 나갈 수 있습니다.
    update = {
        "type": "tiles_exchanged",
        "by": sender,
        "count": len(given),
        "turn": room.turn_nickname,
        "passes": room.passes,
        "passes_until_end": MAX_PASSES - room.passes,
        "tiles_left": len(room.bag),
        "scores": {"host": room.host_score, "guest": room.guest_score},
    }
    await send_quietly(room.host, {**update, "your_turn": room.turn_is_host is True})
    await send_quietly(room.guest, {**update, "your_turn": room.turn_is_host is False})

    if room.passes >= MAX_PASSES:
        await end_game(room, "passed", winner_is_host=winner_by_score(room))


async def resign_game(websocket: WebSocket, room: LiveRoom, sender: str) -> None:
    """나가기 버튼. 게임을 끝내고 **상대가 이긴 것**으로 합니다.

    그만둔 사람을 이기게 하면 **지고 있을 때 나가버리는 게 이득**이
    되어 버립니다. 점수와 상관없이 남은 사람이 이깁니다.

    연결은 끊지 않습니다. 결과를 보고 다시 시작할 수 있어야 하기
    때문입니다. (탭을 닫는 것은 지금까지처럼 따로 처리됩니다)
    """
    if not room.started or room.finished:
        await websocket.send_json(
            {"type": "error", "message": "지금은 나갈 게임이 없습니다"}
        )
        return

    quit_is_host = websocket is room.host
    # 나간 사람의 **반대편**이 이깁니다.
    await end_game(room, "resigned", winner_is_host=not quit_is_host, quitter=sender)


async def check_word(websocket: WebSocket, room: LiveRoom, sender: str, data: dict) -> None:
    """제출을 받아 판에 놓습니다. 놓을 수 없으면 이유를 알려줍니다.

    성공하면 **양쪽 모두에게** 판이 바뀌었다고 알립니다. 판은 두 사람이
    함께 보는 것이라 한쪽만 알면 화면이 어긋납니다.

    실패하면 **보낸 사람에게만** 알립니다. 상대 화면에는 아무 변화가
    없고, "상대가 뭔가 시도했다가 실패했다"를 알려줄 이유도 없습니다.
    """
    # 아직 시작 안 한 게임에는 놓을 수 없습니다. 시작 전에 놓이면 그 뒤에
    # 칩을 나눠 줄 때 판에 이미 글자가 있는 이상한 상태가 됩니다.
    if room.finished:
        await websocket.send_json(
            {"type": "error", "message": "이미 끝난 게임입니다"}
        )
        return

    if not room.started or room.turn_is_host is None:
        await websocket.send_json(
            {"type": "error", "message": "아직 게임이 시작되지 않았습니다"}
        )
        return

    # **내 차례인가.**
    #
    # 판은 하나뿐입니다. 차례를 안 지키면 둘이 동시에 놓을 수 있고, 그러면
    # 먼저 도착한 쪽이 이기는 경주가 됩니다. 순서가 있는 게임에서 그건
    # 규칙이 없는 것과 같습니다.
    #
    # 닉네임이 아니라 **연결**로 판단합니다. 두 사람 이름이 같으면
    # 닉네임 비교로는 상대 차례에도 내가 놓을 수 있게 됩니다.
    if (websocket is room.host) is not room.turn_is_host:
        await websocket.send_json(
            {
                "type": "error",
                "message": f"지금은 {room.turn_nickname}님 차례입니다",
                "turn": room.turn_nickname,
                "your_turn": False,
            }
        )
        return

    # 놓는 사람이 방장인지 친구인지에 따라 손패가 다릅니다.
    is_host = websocket is room.host
    my_rack = room.host_rack if is_host else room.guest_rack

    try:
        placed = parse_tiles(data.get("tiles"))
        direction = check_placement(room.board, placed)
        # **손에 정말 있는 칩인가.** 자리가 맞아도 없는 칩은 못 놓습니다.
        # 자리 확인 다음, 사전 확인 앞에 둡니다. 없는 칩이면 그게 무슨
        # 단어인지 따져볼 필요조차 없기 때문입니다.
        rest_of_rack, used = take_from_rack(my_rack, placed)
    except SubmitError as e:
        await websocket.send_json({"type": "error", "message": str(e)})
        return

    # 판을 **베껴서** 그 위에 놓아 봅니다. 진짜 판에 바로 놓으면, 단어가
    # 틀렸을 때 되돌려야 하는데 그 되돌리기를 빠뜨리면 엉터리 글자가
    # 판에 남습니다. 베낀 판에서 확인하고 통과할 때만 진짜에 옮깁니다.
    trial = [line[:] for line in room.board]
    for row, col, letter, *_ in placed:
        trial[row][col] = letter

    words = words_formed(trial, placed, direction)

    if not words:
        # 한 글자를 아무 데도 안 붙게 놓은 경우입니다. 위 규칙들을
        # 통과했더라도 단어가 안 만들어지면 낼 수 없습니다.
        await websocket.send_json(
            {"type": "error", "message": f"단어가 만들어지지 않았습니다 ({MIN_WORD_LENGTH}글자 이상)"}
        )
        return

    checked = [{**w, "valid": is_word(w["word"])} for w in words]
    bad = [w["word"] for w in checked if not w["valid"]]

    if bad:
        # 하나라도 사전에 없으면 **아무것도 놓지 않습니다.** 일부만 놓으면
        # 판이 반쯤 바뀐 채로 남아서 되돌릴 수가 없습니다.
        await websocket.send_json(
            {
                "type": "word_checked",
                "valid": False,
                "placed": False,
                "direction": direction,
                "words": checked,
                "reason": "사전에 없는 단어입니다: " + ", ".join(bad),
            }
        )
        return

    # 전부 통과했습니다. 이제부터가 **실제로 바꾸는 부분**입니다.
    #
    # 여기까지 오는 동안 아무것도 안 바꿨다는 점이 중요합니다. 중간에
    # 거절되면 판도 손패도 가방도 그대로라, 되돌릴 것이 없습니다.
    room.board = trial

    # 점수를 냅니다. **판에 올린 뒤·보너스 칸을 쓰기 전**이라, 이번에 새로
    # 놓은 자리의 보너스가 그대로 적용됩니다.
    score = score_move(words, placed, used, board_blanks=room.blank_spots)

    # 이번에 빈 타일로 놓은 자리를 판에 기억해 둡니다. 안 해두면 다음
    # 수에서 이 칸이 진짜 글자로 계산됩니다.
    new_blank_spots = {tuple(spot) for spot in score.pop("_new_blanks")}
    room.blank_spots |= new_blank_spots
    if is_host:
        room.host_score += score["total"]
    else:
        room.guest_score += score["total"]

    # 쓴 칩을 손에서 빼고, **놓은 개수만큼** 가방에서 다시 뽑습니다.
    # 안 채우면 몇 수 만에 손이 비어 게임이 멈춥니다.
    drawn = draw_tiles(room.bag, len(used))
    new_rack = rest_of_rack + drawn
    if is_host:
        room.host_rack = new_rack
    else:
        room.guest_rack = new_rack

    # 누군가 실제로 놓았으니 "연속으로 넘긴 횟수"는 0으로 되돌립니다.
    # 연속이 아니면 셀 의미가 없습니다.
    room.passes = 0

    # 차례를 넘기는 건 **맨 마지막**입니다. 먼저 넘기면 중간에 문제가
    # 생겼을 때 아무도 안 놓았는데 차례만 넘어갑니다.
    room.turn_is_host = not room.turn_is_host

    await websocket.send_json(
        {
            "type": "word_checked",
            "valid": True,
            "placed": True,
            "direction": direction,
            "words": checked,
            # 새 손패는 **놓은 사람에게만** 갑니다. 상대에게 보내면
            # 내가 무슨 칩을 들었는지 그대로 알려주는 셈입니다.
            "rack": new_rack,
            "drawn": drawn,
            "tiles_left": len(room.bag),
            # 이번 수로 얻은 점수. 단어별 내역까지 함께 보내서 화면에
            # "CAT 10점 + 빙고 50점" 처럼 풀어 보여줄 수 있게 합니다.
            "score": score,
        }
    )

    # 판이 바뀐 것은 **두 사람 모두의 일**입니다.
    update = {
        "type": "board_updated",
        "by": sender,
        "direction": direction,
        "tiles": [
            {"row": r, "col": c, "letter": l, "blank": (r, c) in new_blank_spots}
            for r, c, l, _b in placed
        ],
        "words": [w["word"] for w in checked],
        "board": room.board,
        # 판에서 빈 타일로 놓인 자리들. 화면에서 그 칸을 다르게 그리고
        # (0점이니까) 점수를 설명할 때 씁니다.
        "blank_spots": [[r, c] for r, c in sorted(room.blank_spots)],
        # 이제 누구 차례인지. 방금 놓은 사람의 **상대**입니다.
        "turn": room.turn_nickname,
        # 가방에 남은 개수. 양쪽 다 알아도 되는 값입니다.
        "tiles_left": len(room.bag),
        # 이번 수로 얻은 점수와, 지금까지 쌓인 두 사람 점수.
        # 점수판은 **둘 다 보는 것**이라 양쪽에 같이 보냅니다.
        "score": score,
        "scores": {
            "host": room.host_score,
            "guest": room.guest_score,
        },
    }
    # `your_turn` 과 `partner_tile_count` 는 사람마다 다릅니다.
    # 이름이 같을 수 있어서 닉네임 비교로는 내 차례인지 알 수 없고,
    # "상대가 몇 장 들었는지"도 보는 사람에 따라 다른 값입니다.
    await send_quietly(
        room.host,
        {
            **update,
            "your_turn": room.turn_is_host is True,
            "partner_tile_count": len(room.guest_rack),
        },
    )
    await send_quietly(
        room.guest,
        {
            **update,
            "your_turn": room.turn_is_host is False,
            "partner_tile_count": len(room.host_rack),
        },
    )

    # 이 수로 게임이 끝났는가.
    #
    # **가방이 비고, 방금 놓은 사람이 손패를 다 썼을 때** 끝납니다.
    # 더 뽑을 것도 없고 낼 것도 없으면 게임이 이어질 수 없습니다.
    #
    # `board_updated` 를 먼저 보내고 나서 확인하는 이유: 마지막 수도
    # 판에 올라간 모습을 양쪽이 봐야 합니다. 결과부터 던지면 무엇으로
    # 끝났는지 못 보고 화면이 넘어갑니다.
    if not room.bag and not new_rack:
        # 승패는 **쌓아온 점수 그대로** 가립니다. 손에 남은 칩은
        # 점수에 반영하지 않습니다.
        await end_game(room, "finished", winner_is_host=winner_by_score(room))


def mark_room_started(code: str) -> datetime:
    """방을 "시작됨"으로 표시하고, **DB 가 찍은 시각**을 돌려줍니다.

    시각을 파이썬이 아니라 DB 에서 만드는 이유는 `insert_message` 와
    같습니다. 기록에 남는 시각과 양쪽 화면에 뜨는 시각이 한 글자도
    다르지 않게 하려는 것입니다.
    """
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE rooms SET started_at = now() WHERE code = %s"
                " RETURNING started_at",
                (code,),
            )
            return cur.fetchone()[0]


async def start_game(websocket: WebSocket, room: LiveRoom) -> None:
    """시작 요청을 처리하고 **양쪽 모두에게** 알립니다.

    **첫 시작은 방장만**, **다시 시작은 누구나** 할 수 있습니다.

    안 되는 경우에는 요청한 사람에게만 이유를 돌려주고, 상대에게는
    아무것도 보내지 않습니다. 실패는 요청한 사람의 사정이라, 상대
    화면에 알 수 없는 메시지가 뜨면 오히려 혼란스럽기 때문입니다.
    """
    # ① 끝난 게임이라면 **다시 하기**입니다.
    #
    # 판·손패·점수를 비우고 새로 시작합니다. 안 비우면 지난 판 글자
    # 위에서 시작하게 됩니다.
    #
    # `clear_game()` 이 `finished` 를 지워버리므로, 다시 하기였다는
    # 사실을 미리 적어 둡니다. 아래 ③ 에서 필요합니다.
    restarting = room.finished
    if restarting:
        room.clear_game()

    # ② 이미 시작한 게임인가
    #
    # 버튼을 두 번 눌렀거나, 끝난 뒤 **둘이 거의 동시에 다시 시작을
    # 누른** 경우입니다. 막지 않으면 진행 중인 게임이 처음으로
    # 되돌아갑니다.
    #
    # 이 검사를 ③(방장인가)보다 **먼저** 합니다. 순서가 반대면, 둘이
    # 동시에 눌렀을 때 늦은 쪽이 "방장만 시작할 수 있습니다"를 받습니다.
    # 다시 시작을 눌렀는데 방장 얘기가 나오면 무슨 말인지 알 수 없습니다.
    # 실제로 일어난 일은 "상대가 방금 시작했다"이므로 그렇게 답해야 합니다.
    #
    # ② 와 아래에서 실제로 시작 표시를 하는 지점 사이에는 기다리는
    # 곳(await)이 없습니다. 그래서 그 사이에 다른 요청이 끼어들 수 없고,
    # 두 번 시작되는 일도 없습니다.
    if room.started:
        await websocket.send_json(
            {"type": "error", "message": "이미 시작된 게임입니다"}
        )
        return

    # ③ 첫 시작인데 방장이 아닌가
    #
    # **첫 시작은 방장만** 할 수 있습니다. "언제 시작할지"를 정하는
    # 사람이 둘이면 아무도 정하지 못하기 때문입니다.
    #
    # **다시 시작은 누구나** 할 수 있습니다. 위 ① 에서 이미 판을
    # 비웠으므로 여기까지 오면 방장인지 따지지 않습니다.
    # 판이 이미 끝났으니 정할 것이 없고, 진 사람이 "다시 하자"고 못 하는
    # 것도 이상합니다. 무엇보다 **프론트엔드가 자기가 방장인지 알 방법이
    # 마땅치 않습니다** — 닉네임 비교는 두 사람 이름이 같으면 틀립니다.
    #
    # 닉네임이 아니라 **연결**을 비교합니다. 닉네임은 서로 같을 수
    # 있어서(둘 다 "수진"), 닉네임으로 판단하면 친구가 방장 이름을
    # 그대로 쓰는 것만으로 게임을 시작할 수 있게 됩니다.
    if not restarting and websocket is not room.host:
        await websocket.send_json(
            {"type": "error", "message": "방장만 게임을 시작할 수 있습니다"}
        )
        return

    # ③ 두 명이 다 모였는가
    #
    # 혼자 시작하면 상대가 들어왔을 때 이미 진행 중인 판에 끼어드는
    # 셈이 됩니다. 스크래블은 최소 두 명이 있어야 합니다.
    if room.guest is None or room.guest_nickname is None:
        await websocket.send_json(
            {"type": "error", "message": "아직 상대가 들어오지 않았습니다"}
        )
        return

    # 먼저 표시해 두고 그다음 DB 에 적습니다.
    #
    # 순서가 중요합니다. DB 를 먼저 다녀오면 그동안(await) 방장이 한 번
    # 더 누른 요청이 끼어들어 ② 를 통과해 버립니다. 메모리에 먼저 찍어
    # 두면 두 번째 요청은 반드시 ② 에서 막힙니다.
    room.started = True

    # 누가 먼저 둘지 정합니다. **방장이 아니라 무작위**입니다.
    # 스크래블에서 선공은 유리한 자리라, 방을 만들었다는 이유만으로
    # 매번 먼저 두게 하면 공평하지 않습니다.
    #
    # 닉네임 둘 중에서 고르지 않고 **자리(방장이냐 아니냐)를** 고릅니다.
    # 두 사람 이름이 같으면("수진" 대 "수진") 이름으로 고른 값은 누구를
    # 가리키는지 알 수 없게 됩니다.
    #
    # `random` 이 아니라 `secrets` 를 쓰는 것은 초대 코드와 같은 이유로,
    # 다음 값을 예측당하지 않기 위해서입니다.
    room.turn_is_host = secrets.choice([True, False])
    room.first_turn = room.turn_nickname

    # 칩을 섞어 각자 7개씩 나눠 줍니다.
    #
    # DB 에 적기 **전에** 나눠 두는 이유: 나누는 일은 메모리 안에서만
    # 일어나 실패할 구석이 없습니다. 반대로 DB 는 실패할 수 있어서, DB 를
    # 먼저 성공시켜 놓고 여기서 문제가 나면 "시작했다고 기록됐는데 칩은
    # 없는" 상태가 됩니다. 실패할 수 있는 일을 마지막에 두는 게 낫습니다.
    deal_tiles(room)

    try:
        started_at = await run_in_threadpool(mark_room_started, room.code)
    except Exception:
        # 기록에 실패했으면 시작하지 않은 것으로 되돌립니다. 그냥
        # 진행하면 화면에서는 게임 중인데 기록에는 시작한 적이 없는
        # 상태가 되어, 나중에 무슨 일이 있었는지 알 수 없게 됩니다.
        # 나눠 준 칩도 함께 물립니다.
        room.clear_game()
        await websocket.send_json(
            {"type": "error", "message": "게임을 시작하지 못했습니다. 잠시 후 다시 눌러 주세요"}
        )
        return

    # 여기부터는 **양쪽에 보내는 내용이 다릅니다.**
    #
    # 칩이 생기기 전까지는 똑같은 값을 보냈지만, 이제는 그러면 안 됩니다.
    # 한 번에 같은 걸 보내면 **상대의 칩이 내 화면에 그대로 도착합니다.**
    # 프론트엔드가 안 그리면 된다고 생각하기 쉬운데, 브라우저 개발자
    # 도구를 열면 오간 내용이 그대로 보입니다. 애초에 **보내지 않는**
    # 것만이 가리는 방법입니다.
    common = {
        "type": "game_started",
        "code": room.code,
        "host_nickname": room.host_nickname,
        "guest_nickname": room.guest_nickname,
        "first_turn": room.first_turn,
        # `first_turn` 은 "이 게임의 선공"이라 끝까지 안 바뀌고,
        # `turn` 은 "지금 차례"라 한 수마다 바뀝니다. 시작 시점에는 둘이
        # 같은 값이지만 뜻이 다릅니다.
        "turn": room.turn_nickname,
        "at": started_at.isoformat(),
        # 가방에 남은 개수는 양쪽 다 알아도 되는 값입니다. 실제 스크래블
        # 에서도 남은 타일 수는 서로 볼 수 있습니다. (무엇이 남았는지는 아님)
        "tiles_left": len(room.bag),
        # 시작 점수. 둘 다 0 이지만, 점수판을 그리는 자리를 처음부터
        # 서버가 준 값으로 채우게 하려고 함께 보냅니다.
        "scores": {"host": room.host_score, "guest": room.guest_score},
        # 시작 시점의 판. 지금은 반드시 비어 있지만 그래도 보냅니다.
        # 프론트엔드가 빈 판을 스스로 만들면 크기가 어긋날 수 있고,
        # 무엇보다 **판은 언제나 서버가 준 것을 그린다**는 규칙이 한 군데서
        # 깨지면 나머지도 흔들립니다.
        "board": room.board,
    }

    # `rack` 은 **받는 사람 자기 것**입니다. 상대 것은 개수만 보냅니다.
    # 프론트엔드가 상대 칩을 뒷면으로 몇 장 그릴지 알아야 하기 때문입니다.
    #
    # `your_turn` 도 사람마다 다릅니다. `turn` 에 닉네임이 있긴 하지만,
    # 두 사람 이름이 같으면 프론트엔드가 **내 차례인지 알 수 없습니다.**
    # 그래서 각자에게 참·거짓으로 따로 알려줍니다.
    await send_quietly(
        room.host,
        {
            **common,
            "rack": room.host_rack,
            "partner_tile_count": len(room.guest_rack),
            "your_turn": room.turn_is_host is True,
        },
    )
    await send_quietly(
        room.guest,
        {
            **common,
            "rack": room.guest_rack,
            "partner_tile_count": len(room.host_rack),
            "your_turn": room.turn_is_host is False,
        },
    )


async def chat_loop(websocket: WebSocket, sender_nickname: str, find_context) -> None:
    """연결이 끊길 때까지 **들어온 요청을 처리합니다.**

    지금 받는 요청은 두 가지입니다.
      `{"type":"message","text":"..."}`  대화 한 줄 보내기
      `{"type":"start"}`                 게임 시작 (방장만)

    방장 쪽과 친구 쪽이 이 함수 하나를 같이 씁니다. 1:1 이라 양쪽이
    하는 일이 완전히 똑같기 때문입니다. 두 벌로 나눠 적으면 나중에
    한쪽만 고쳐서 "방장은 되는데 친구는 안 되는" 사고가 납니다.
    (게임 시작처럼 **방장만 할 수 있는 일**도 여기서 함께 받고,
     방장인지 아닌지는 `start_game` 안에서 가립니다. 받는 창구를
     나누면 그 창구에 안 오는 쪽이 조용히 빠지기 쉽습니다.)

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

        if not isinstance(data, dict):
            await websocket.send_json(
                {
                    "type": "error",
                    "message": '{"type":"message","text":"..."} 형식으로 보내주세요',
                }
            )
            continue

        # ② 게임 시작 요청인가
        #
        # 대화보다 먼저 봅니다. 이 요청에는 `text` 가 없어서, 아래
        # 대화 처리로 흘려보내면 "빈 메시지는 보낼 수 없습니다"라는
        # 엉뚱한 답을 받게 됩니다.
        if data.get("type") == "start":
            context = find_context()
            if context is None:
                # 방에 아직 나 혼자입니다. 방장이든 아니든 할 수 있는
                # 일이 없으므로 같은 답을 줍니다.
                await websocket.send_json(
                    {"type": "error", "message": "아직 상대가 들어오지 않았습니다"}
                )
                continue

            room, _ = context
            await start_game(websocket, room)
            continue

        # ③ 단어 제출인가
        #
        # 게임 시작과 달리 **누구나** 보낼 수 있습니다. 지금은 사전에
        # 있는지 알려주기만 하고 판을 건드리지 않아서, 차례가 아닌
        # 사람이 미리 확인해 봐도 상대에게 아무 영향이 없습니다.
        # (차례를 지키게 하는 것은 판에 실제로 놓을 때 필요합니다)
        if data.get("type") == "submit":
            # 판에 놓으려면 **어느 방인지**를 알아야 합니다. 판은 방마다
            # 따로 있기 때문입니다. 상대가 아직 없으면 놓을 수 없습니다.
            context = find_context()
            if context is None:
                await websocket.send_json(
                    {"type": "error", "message": "아직 상대가 들어오지 않았습니다"}
                )
                continue
            await check_word(websocket, context[0], sender_nickname, data)
            continue

        # ④ 턴 넘기기 · 나가기인가
        #
        # 둘 다 방(그리고 상대)이 있어야 뜻이 있는 요청이라 한 묶음으로
        # 처리합니다.
        if data.get("type") in ("pass", "resign", "exchange"):
            context = find_context()
            if context is None:
                await websocket.send_json(
                    {"type": "error", "message": "아직 상대가 들어오지 않았습니다"}
                )
                continue

            if data["type"] == "pass":
                await pass_turn(websocket, context[0], sender_nickname)
            elif data["type"] == "exchange":
                await exchange_tiles(websocket, context[0], sender_nickname, data)
            else:
                await resign_game(websocket, context[0], sender_nickname)
            continue

        # ⑤ 우리가 아는 종류인가
        if data.get("type") != "message":
            await websocket.send_json(
                {
                    "type": "error",
                    "message": (
                        '{"type":"message","text":"..."} · {"type":"start"} · '
                        '{"type":"submit","tiles":[...]} · {"type":"pass"} · '
                        '{"type":"exchange","tiles":["Q"]} · {"type":"resign"} '
                        '중 하나로 보내주세요'
                    ),
                }
            )
            continue

        # ⑤ 내용이 규칙에 맞는가
        try:
            text = clean_chat_text(str(data.get("text", "")))
        except ValueError as e:
            await websocket.send_json({"type": "error", "message": str(e)})
            continue

        # ⑥ 건네줄 상대가 있는가
        context = find_context()
        if context is None:
            await websocket.send_json(
                {"type": "error", "message": "상대가 아직 들어오지 않았습니다"}
            )
            continue

        room, partner = context

        # ⑦ 먼저 저장하고, 그다음 건네줍니다.
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
@sentry.catch_ws
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
@sentry.catch_ws
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
@sentry.catch_ws
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

    # 이 방에서 **전에 오간 대화**를 되돌려 줍니다.
    #
    # 대화는 계속 DB 에 저장돼 왔지만 꺼내 볼 방법이 없어서, 다시 들어오면
    # 화면이 늘 비어 있었습니다. 저장만 하고 안 쓰는 기록이었습니다.
    #
    # **들어온 사람에게만** 보냅니다. 방장은 그 대화를 처음부터 보고
    # 있었으니 다시 보낼 이유가 없습니다.
    #
    # 대화가 없으면 빈 목록이 갑니다. 아예 안 보내지 않는 이유: 프론트가
    # "아직 안 온 건가, 없는 건가"를 기다리게 되기 때문입니다.
    history = await run_in_threadpool(load_messages, room.room_id)
    await websocket.send_json({"type": "history", "messages": history})

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

            # 게임 중이었다면 그 판은 여기서 끝난 것입니다. 상대가 없는
            # 스크래블은 이어갈 수 없기 때문입니다. 표시를 지워 두지
            # 않으면, 새 친구가 들어와도 방장이 "이미 시작된 게임입니다"만
            # 보게 되어 **영영 시작할 수 없는 방**이 됩니다.
            #
            # 나눠 줬던 칩도 함께 버립니다. 남겨 두면 다음 판에 지난 판의
            # 칩이 섞여 들어와서, 가방에 같은 타일이 두 번 생깁니다.
            room.clear_game()

            # 자리가 다시 비었으니 방장은 새 친구를 기다릴 수 있습니다.
            await run_in_threadpool(set_room_status, code, "waiting")
            await send_quietly(
                room.host, {"type": "guest_left", "nickname": guest_nickname}
            )


# ─────────────────────────────────────────────────────────────
# 게임 기초 데이터 API — 칩 구성과 보드 배열 내주기
#
# 값 자체는 `game_data.py` 에 있고, 여기서는 **프론트엔드가 가져갈 수
# 있게 내주기만** 합니다.
#
# 왜 API 로 내주는가:
#   프론트엔드도 보드를 그리려면 어느 칸이 "글자 2배"인지 알아야 합니다.
#   그런데 그 표를 프론트엔드가 **따로 적어 두면**, 규칙이 두 군데
#   존재하게 됩니다. 한쪽만 고치는 날 두 화면이 서로 다른 보드를 그리고,
#   그건 눈으로 찾기 아주 어렵습니다.
#   규칙의 원본은 백엔드 한 곳이고, 프론트엔드는 받아서 그리기만 합니다.
#
# 왜 웹소켓이 아니라 HTTP 인가:
#   이 값은 **바뀌지 않습니다.** 서버가 먼저 알려줄 일이 없으니 웹소켓을
#   쓸 이유가 없습니다. 프론트엔드가 필요할 때 한 번 물어보면 끝입니다.
#   반대로 "칩을 나눠줬다"는 소식은 상대 때문에 생기는 일이라 웹소켓입니다.
# ─────────────────────────────────────────────────────────────
class TileOut(BaseModel):
    """타일 한 종류."""

    letter: str = Field(
        ...,
        description='글자. `"?"` 는 **빈 타일**로, 아무 글자로나 쓸 수 있는 대신 0점입니다.',
        examples=["E"],
    )
    count: int = Field(..., description="가방에 들어 있는 개수", examples=[12])
    points: int = Field(..., description="이 글자 하나의 점수", examples=[1])


class PremiumOut(BaseModel):
    """특수 칸 한 종류가 무슨 뜻인지."""

    name: str = Field(..., description="사람이 읽는 이름", examples=["글자 2배"])
    multiplier: int = Field(..., description="몇 배인지", examples=[2])
    applies_to: str = Field(
        ...,
        description='`"letter"` 면 그 글자에만, `"word"` 면 단어 전체에 걸립니다',
        examples=["letter"],
    )


class GameSetupOut(BaseModel):
    """게임을 그리는 데 필요한 고정 값 한 묶음."""

    board_size: int = Field(..., description="보드 한 변의 칸 수", examples=[15])
    board: List[List[str]] = Field(
        ...,
        description=(
            "보드 배열. **위에서 아래로** 한 줄씩이고, `board[줄][칸]` 으로 찾습니다. "
            "둘 다 0 부터 셉니다. 빈 문자열은 보통 칸이고, 나머지는 `premium_legend` "
            "에 뜻이 적혀 있습니다."
        ),
    )
    premium_legend: Dict[str, PremiumOut] = Field(
        ..., description="특수 칸 기호가 각각 무슨 뜻인지"
    )
    center: List[int] = Field(
        ...,
        description="한가운데 시작 칸의 `[줄, 칸]`. **첫 단어는 반드시 여기를 지나야 합니다.**",
        examples=[[7, 7]],
    )
    tiles: List[TileOut] = Field(..., description="칩(타일) 구성")
    total_tiles: int = Field(
        ..., description="가방에 들어 있는 타일 전체 개수", examples=[100]
    )
    rack_size: int = Field(
        ..., description="한 사람이 손에 들고 있는 타일 수", examples=[7]
    )


@app.get("/api/game/setup", response_model=GameSetupOut, tags=["게임"])
def game_setup():
    """게임을 그리는 데 필요한 **고정 값**을 한 번에 돌려줍니다.

    칩(타일) 구성과 보드 배열입니다. **언제 불러도 항상 같은 값**이라
    프론트엔드는 시작할 때 한 번만 받아 두면 됩니다.

    ⚠️ 여기에 **"지금 이 게임의 상태"는 없습니다.** 누가 어떤 칩을 들고
    있는지, 보드에 무엇이 놓였는지는 방마다 다르고 매 순간 바뀌는 값이라
    이 API 가 아니라 웹소켓으로 오갑니다. 규칙과 상태를 한곳에 섞으면
    게임이 끝날 때마다 규칙을 다시 받아야 합니다.
    """
    return GameSetupOut(
        board_size=BOARD_SIZE,
        # 안쪽이 튜플이라 그대로 두면 JSON 으로 나갈 때 헷갈릴 수 있어
        # 목록으로 바꿔 줍니다.
        board=[list(row) for row in BOARD_LAYOUT],
        premium_legend={
            key: PremiumOut(**value) for key, value in PREMIUM_LEGEND.items()
        },
        center=[CENTER, CENTER],
        tiles=[
            TileOut(letter=letter, count=count, points=points)
            for letter, count, points in TILE_DISTRIBUTION
        ],
        total_tiles=TOTAL_TILES,
        rack_size=RACK_SIZE,
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
