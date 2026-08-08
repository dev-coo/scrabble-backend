# Scrabble Backend

스크래블 프로젝트의 백엔드 저장소입니다. (FastAPI + PostgreSQL)

3티어 중 **로직 + 데이터** 티어입니다. 화면은 그리지 않고, 프론트엔드가
호출할 API를 제공하며 DB에 데이터를 저장·조회합니다.

## 셋업 (처음 한 번)

```bash
# 1. 저장소를 클론한 폴더에서
python3.12 -m venv .venv
.venv/bin/pip install -r requirements.txt

# 2. 커밋 작성자 이름 설정 (프롬프트 로그·커밋에 표시됨)
git config user.name "본인이름"
```

> ⚠️ **`python3` 대신 `python3.12`를 쓰세요.**
> 이 컴퓨터의 기본 `python3`은 3.14인데, 3.14에서는 가상환경 생성이 실패합니다.
> (`ensurepip` 오류) 확인된 동작 버전은 **3.12** 입니다.

## 실행

```bash
.venv/bin/uvicorn main:app --host 0.0.0.0 --port 11000
```

| 용도 | 주소 |
|------|------|
| 백엔드 루트 | http://localhost:11000/ |
| 프론트엔드가 호출하는 API | http://localhost:11000/api/hello |
| **스와거 문서** | http://localhost:11000/docs |
| OpenAPI (기계용 계약서) | http://localhost:11000/openapi.json |

FastAPI는 코드를 짜면 **스와거 문서 화면을 자동으로 만들어 줍니다.**
`/docs`에 들어가면 API를 눈으로 보고 직접 눌러볼 수 있습니다.

## 데이터베이스

PostgreSQL이 Docker 컨테이너로 떠 있습니다. **이미 실행 중이라 따로 설치할 게 없습니다.**

| 항목 | 값 |
|------|-----|
| Host | `localhost` |
| Port | `5432` |
| Database | `scrabble` |
| Username | `scrabble` |
| Password | `scrabble` |

### 연결 확인

```bash
.venv/bin/python db.py
```

지금 DB에 어떤 테이블이 있고 몇 행인지 출력합니다.

### 테이블 만들기 (처음 한 번)

테이블 정의는 [`schema.sql`](./schema.sql)에 적혀 있습니다. 아래 명령으로 적용합니다.

```bash
.venv/bin/python apply_schema.py
```

여러 번 실행해도 안전합니다. 이미 있는 테이블은 건너뛰고, **데이터는 지워지지 않습니다.**

| 테이블 | 저장하는 것 |
|--------|-------------|
| `players` | 게임에 참여하는 사람 (닉네임) |
| `rooms` | 게임 시작 전 사람들이 모이는 방 (이름·정원·상태) |

> **DB를 바꿀 때는 DBeaver에서 직접 고치지 말고 `schema.sql`을 고치세요.**
> DBeaver에서 고치면 내 컴퓨터의 DB만 바뀌고 저장소에는 아무 기록이 남지 않아서,
> 다른 사람은 그 변경을 알 수도 재현할 수도 없습니다.

### DBeaver로 보기

DBeaver를 열고 **PostgreSQL**을 선택한 뒤 위 접속 정보를 그대로 입력하면
같은 데이터를 화면으로 볼 수 있습니다. (첫 연결 시 드라이버 다운로드 창이 뜹니다)

### 코드에서 쓰기

```python
from db import get_connection

with get_connection() as conn:
    with conn.cursor() as cur:
        cur.execute("SELECT id, nickname FROM players")
        rows = cur.fetchall()
```

## 프롬프트 로그 (협업용)

이 저장소는 **Claude에게 입력한 프롬프트가 자동으로 기록**됩니다.

- 파일: [`PROMPTS.md`](./PROMPTS.md)
- 기록 내용: `[타임스탬프] 작성자` + 입력한 질문/명령 (Claude의 응답은 기록되지 않음)
- 동작 방식: Claude Code의 `UserPromptSubmit` 훅 (`.claude/hooks/log-prompt.sh`)

작업 중 또는 작업 후 `PROMPTS.md`를 커밋/푸시하면 서로의 프롬프트를 비교하며
회고할 수 있습니다.

## 관련 문서

- [`CLAUDE.md`](./CLAUDE.md) — Claude가 지킬 작업 규칙
- [`docs/COLLABORATION.md`](./docs/COLLABORATION.md) — 사람이 읽는 협업 가이드
- [`docs/api-contract.md`](./docs/api-contract.md) — 프론트엔드와의 API 계약
- [`docs/ws-contract.md`](./docs/ws-contract.md) — 웹소켓 설명 (사람이 읽는 문서)
- [`docs/asyncapi.yaml`](./docs/asyncapi.yaml) — 웹소켓 명세 원본 (기계가 읽는 계약서)
  - 눈으로 보는 화면: <http://localhost:11000/ws-docs> ← 스와거의 웹소켓 버전
