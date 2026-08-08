# API 계약서 (스크래블) — 백엔드

> 최종 수정: 2026-08-08

프론트엔드와 백엔드는 **API라는 약속(계약)**으로만 연결됩니다.
이 문서는 사람이 읽는 계약서이고, 같은 내용을 기계가 읽는 버전이
FastAPI가 자동 생성하는 **`/openapi.json`** 입니다.

> 프론트엔드 저장소에도 **같은 내용의 `docs/api-contract.md`**가 있습니다.
> 계약을 바꿀 때는 **양쪽을 함께 고치고, 멘토(은우)가 일치를 확인**합니다.

## 서버 / 포트 (고정)

수진·엘리·은우 계정이 **같은 컴퓨터**에 있으므로 `localhost`로 서로 접속합니다.

| 구분 | 포트 | 실행자 | 주소 |
|------|------|--------|------|
| 프론트엔드 | **10000** | 수진 | http://localhost:10000 |
| 백엔드(FastAPI) | **11000** | 엘리 | http://localhost:11000 |
| **데이터베이스(PostgreSQL)** | **5432** | 은우 (Docker) | `localhost:5432` |
| 스와거 문서 | — | — | http://localhost:11000/docs |
| OpenAPI(기계용 계약서) | — | — | http://localhost:11000/openapi.json |

> ⚠️ **포트 10000·11000·5432 는 스크래블 프로젝트 전용으로 예약**합니다.
> 서버 주인이 다른 서비스를 쓸 때 이 세 포트는 피해 주세요. (충돌 방지)
>
> 참고: 테일스케일 주소(`http://100.115.173.118:포트`)로도 동일하게 접속됩니다.
> `index.html`은 현재 이 주소를 쓰고 있으며, 같은 컴퓨터라 둘 다 동작합니다.

## 엔드포인트

| 메서드 | 경로 | 응답 | 설명 |
|--------|------|------|------|
| GET | `/` | `{"message": "기본용 백엔드입니다"}` | 백엔드 리턴값 확인용 |
| GET | `/api/hello` | `{"message": "기본용 백엔드입니다", "from": "backend"}` | **프론트엔드가 호출하는 API** |
| POST | `/api/players` | 아래 참고 | **플레이어 닉네임 추가** |
| GET | `/api/players` | 아래 참고 | **플레이어 목록 조회** |
| GET | `/api/players/check-nickname` | 아래 참고 | **닉네임 중복 확인** |
| PUT | `/api/players/{id}` | 아래 참고 | **플레이어 닉네임 수정** |
| DELETE | `/api/players/{id}` | 아래 참고 | **플레이어 삭제** |

> 새 API를 만들면 **여기에 추가**하고 프론트엔드 담당(수진)에게 알려주세요.
>
> `POST /api/players` 와 `GET /api/players` 는 **주소가 같고 메서드만 다릅니다.**
> 같은 대상(players)에 추가하면 POST, 조회하면 GET — REST 규칙입니다.

### POST `/api/players` — 플레이어 닉네임 추가

새 플레이어를 `players` 테이블에 저장합니다.

**요청** (`Content-Type: application/json`)

```json
{ "nickname": "수진" }
```

| 필드 | 타입 | 필수 | 규칙 |
|------|------|------|------|
| `nickname` | string | ✅ | 앞뒤 공백은 백엔드가 제거함. 공백 제거 후 **1~20자** |

**성공 응답** — `201 Created`

```json
{
  "id": 4,
  "nickname": "수진",
  "created_at": "2026-07-30T14:13:37.353855"
}
```

| 필드 | 타입 | 설명 |
|------|------|------|
| `id` | number | DB가 자동으로 매긴 번호 |
| `nickname` | string | 공백이 정리된 최종 닉네임 |
| `created_at` | string | 생성 시각 (ISO 8601) |

**에러 응답** — `422 Unprocessable Entity`

값이 규칙에 안 맞으면 FastAPI 기본 형식으로 돌아옵니다.

```json
{
  "detail": [
    {
      "type": "value_error",
      "loc": ["body", "nickname"],
      "msg": "Value error, 닉네임은 비어 있을 수 없습니다"
    }
  ]
}
```

| 상황 | 상태 코드 | `msg` |
|------|-----------|-------|
| `nickname` 필드 자체가 없음 | 422 | `Field required` |
| 빈 문자열이거나 공백만 있음 | 422 | `닉네임은 비어 있을 수 없습니다` |
| 20자 초과 | 422 | `닉네임은 20자 이하여야 합니다` |

> ⚠️ **닉네임 중복은 아직 막지 않습니다.** 같은 닉네임을 여러 번 보내면
> 서로 다른 `id`로 각각 저장됩니다. 중복 금지가 필요하면 DB 테이블에
> 제약을 거는 **별도 작업**으로 진행하세요.
>
> 저장하기 전에 미리 물어보려면
> [`GET /api/players/check-nickname`](#get-apiplayerscheck-nickname--닉네임-중복-확인) 을 쓰세요.

**호출 예시**

```bash
curl -X POST http://localhost:11000/api/players \
  -H "Content-Type: application/json" \
  -d '{"nickname":"수진"}'
```

### GET `/api/players` — 플레이어 목록 조회

저장된 플레이어를 **전부** 돌려줍니다. `id` 오름차순(먼저 만든 순서)입니다.

**요청** — 보낼 값 없음. 그냥 호출하면 됩니다.

**성공 응답** — `200 OK`

배열(리스트)로 돌아옵니다. 각 항목의 모양은 `POST` 응답과 동일합니다.

```json
[
  { "id": 1, "nickname": "수진", "created_at": "2026-07-29T13:05:21.860148" },
  { "id": 2, "nickname": "엘리", "created_at": "2026-07-29T13:05:21.860148" },
  { "id": 3, "nickname": "은우", "created_at": "2026-07-29T13:05:21.860148" }
]
```

> 플레이어가 한 명도 없으면 **에러가 아니라 빈 배열 `[]`** 이 돌아옵니다.
> 프론트엔드는 이때 "아직 플레이어가 없습니다" 같은 안내를 띄우면 됩니다.

**호출 예시**

```bash
curl http://localhost:11000/api/players
```

### GET `/api/players/check-nickname` — 닉네임 중복 확인

닉네임이 **이미 쓰이고 있는지**만 알려줍니다. 아무것도 저장하지 않습니다.

**요청** — 주소 뒤에 물음표를 붙여 보냅니다. (쿼리 파라미터)

```
GET /api/players/check-nickname?nickname=수진
```

| 파라미터 | 타입 | 필수 | 규칙 |
|----------|------|------|------|
| `nickname` | string | ✅ | **POST와 완전히 동일** (앞뒤 공백 제거 후 1~20자) |

**성공 응답** — `200 OK`

```json
{ "nickname": "수진", "exists": true }
```

| 필드 | 타입 | 설명 |
|------|------|------|
| `nickname` | string | 공백이 정리된 최종 닉네임 |
| `exists` | boolean | `true` = 이미 사용 중 / `false` = **쓸 수 있음** |

> 📌 **없는 닉네임이어도 404 가 아니라 200 입니다.** "그런 닉네임 없다"가
> 이 API 가 듣고 싶어 하는 정답 중 하나이기 때문입니다.
> 프론트엔드는 `exists === false` 일 때 "사용 가능한 닉네임입니다"를 띄우면 됩니다.
>
> 비교는 **대소문자·글자를 그대로** 맞춰 봅니다. 앞뒤 공백만 백엔드가 정리합니다.
> (`"  수진  "` 과 `"수진"` 은 같은 닉네임으로 봅니다.)

**에러 응답** — `422 Unprocessable Entity`

`loc` 이 `["query", "nickname"]` 인 것만 다르고, 나머지는 POST 와 같은 형식입니다.

| 상황 | 상태 코드 | `msg` |
|------|-----------|-------|
| `?nickname=` 자체가 없음 | 422 | `Field required` |
| 빈 문자열이거나 공백만 있음 | 422 | `닉네임은 비어 있을 수 없습니다` |
| 20자 초과 | 422 | `닉네임은 20자 이하여야 합니다` |

> ⚠️ **이 API 만으로 중복이 완전히 막히지는 않습니다.**
> 확인한 순간과 저장(`POST`)하는 순간 사이에 다른 사람이 같은 닉네임을
> 먼저 저장할 수 있습니다. 확실히 막으려면 DB 테이블에 "같은 닉네임 금지"
> 제약을 거는 **별도 작업**이 필요합니다. (현재 `players` 에는 없음)

**호출 예시**

```bash
curl "http://localhost:11000/api/players/check-nickname?nickname=수진"
```

### PUT `/api/players/{id}` — 플레이어 닉네임 수정

기존 플레이어의 닉네임을 바꿉니다.

**주소가 앞의 두 API와 다릅니다.** 끝에 `{id}` 가 붙습니다 — "누구를" 바꿀지
지정해야 하기 때문입니다. `GET /api/players` 로 받은 목록의 `id` 를 그대로 넣으세요.

| 자리 | 타입 | 설명 |
|------|------|------|
| `{id}` (주소) | number | 바꿀 플레이어의 `id`. 예: `/api/players/3` |

**요청** (`Content-Type: application/json`)

```json
{ "nickname": "새닉네임" }
```

| 필드 | 타입 | 필수 | 규칙 |
|------|------|------|------|
| `nickname` | string | ✅ | **POST와 완전히 동일** (공백 제거 후 1~20자) |

**성공 응답** — `200 OK`

바뀐 뒤의 최종 상태가 돌아옵니다. `created_at` 은 **처음 만든 시각 그대로**입니다.

```json
{
  "id": 3,
  "nickname": "새닉네임",
  "created_at": "2026-07-29T13:05:21.860148"
}
```

**에러 응답**

| 상황 | 상태 코드 | 응답 |
|------|-----------|------|
| 없는 `id` | **404** | `{"detail": "id 99999 인 플레이어가 없습니다"}` |
| `id` 가 숫자가 아님 (`/api/players/abc`) | 422 | `detail` 배열, `loc: ["path","player_id"]` |
| 빈 닉네임 / 20자 초과 / 필드 없음 | 422 | POST와 동일한 형식 |

> 📌 **404 와 422 의 `detail` 모양이 다릅니다.**
> 404는 `detail` 이 **문자열 하나**, 422는 **배열**입니다.
> 프론트엔드에서 에러 메시지를 꺼낼 때 이 차이를 처리해야 합니다.

**호출 예시**

```bash
curl -X PUT http://localhost:11000/api/players/3 \
  -H "Content-Type: application/json" \
  -d '{"nickname":"새닉네임"}'
```

### DELETE `/api/players/{id}` — 플레이어 삭제

플레이어를 삭제합니다.

| 자리 | 타입 | 설명 |
|------|------|------|
| `{id}` (주소) | number | 삭제할 플레이어의 `id`. 예: `/api/players/3` |

**요청** — **보낼 값 없음.** 주소에 `id` 만 넣으면 됩니다. (PUT과 다른 점)

**성공 응답** — `200 OK`

**삭제된 사람의 정보**가 돌아옵니다. 프론트엔드에서 "OO 님을 삭제했습니다"
처럼 이름을 띄우는 데 쓰세요. 지우고 나면 다시 물어볼 방법이 없으니
이때 받아두는 게 좋습니다.

```json
{
  "id": 3,
  "nickname": "은우",
  "created_at": "2026-07-29T13:05:21.860148"
}
```

**에러 응답**

| 상황 | 상태 코드 | 응답 |
|------|-----------|------|
| 없는 `id` (또는 **이미 지워진 `id`**) | **404** | `{"detail": "id 3 인 플레이어가 없습니다"}` |
| `id` 가 숫자가 아님 | 422 | `detail` 배열, `loc: ["path","player_id"]` |

> 📌 **삭제 버튼을 두 번 누르면 두 번째는 404 입니다.**
> "이미 없어졌으니 성공으로 치자"는 방식도 있지만, 이 프로젝트는
> **없으면 없다고 정확히 알려주는 쪽**을 택했습니다. PUT과 규칙이 같습니다.
>
> 프론트엔드 팁: 삭제 성공 후 `GET /api/players` 로 목록을 다시 받아
> 화면을 갱신하면 이런 상황이 잘 생기지 않습니다.

**호출 예시**

```bash
curl -X DELETE http://localhost:11000/api/players/3
```

## 데이터베이스 (백엔드 전용)

**프론트엔드는 DB에 직접 접근하지 않습니다.** 항상 백엔드 API를 거칩니다.
그래서 이 절은 백엔드 저장소에만 있고, 프론트엔드 저장소에는 없습니다.

| 항목 | 값 |
|------|-----|
| 종류 | PostgreSQL 16 (Docker 컨테이너 `scrabble-db`) |
| Host / Port | `localhost` / `5432` |
| Database | `scrabble` |
| Username / Password | `scrabble` / `scrabble` |

### 현재 테이블

**`players`**

| 컬럼 | 타입 | 설명 |
|------|------|------|
| `id` | SERIAL PRIMARY KEY | 자동 증가 번호 |
| `nickname` | TEXT NOT NULL | 닉네임 |
| `created_at` | TIMESTAMP | 생성 시각 (기본값 `now()`) |

**`rooms`**

| 컬럼 | 타입 | 설명 |
|------|------|------|
| `id` | SERIAL PRIMARY KEY | 자동 증가 번호 |
| `code` | TEXT NOT NULL UNIQUE | 초대 코드 (대문자·숫자 4자리) |
| `host_nickname` | TEXT NOT NULL | 방을 만든 사람 |
| `name` | TEXT NOT NULL | 방 이름 (1~30자) |
| `max_players` | INTEGER NOT NULL | 정원 (2~4, 기본 4) |
| `status` | TEXT NOT NULL | `waiting` / `playing` / `finished` (기본 `waiting`) |
| `created_at` | TIMESTAMP | 생성 시각 (기본값 `now()`) |

> "누가 이 방에 들어와 있는가"는 이 테이블에 없습니다. 한 방에 여러 명이
> 들어오는데 한 칸에 여러 명을 넣을 수 없어서, 방 입장 기능을 만들 때
> 별도 테이블로 다룹니다. (`host_nickname` 은 한 명뿐이라 여기 있습니다)

**`messages`** — 오간 대화 한 줄 한 줄

| 컬럼 | 타입 | 설명 |
|------|------|------|
| `id` | SERIAL PRIMARY KEY | 자동 증가 번호 |
| `room_id` | INTEGER NOT NULL → `rooms.id` | 어느 방의 대화인지. 방이 지워지면 함께 지워짐 |
| `sender` | TEXT NOT NULL | 보낸 사람 닉네임 (1~20자) |
| `text` | TEXT NOT NULL | 내용 (1~500자) |
| `created_at` | TIMESTAMP | 저장된 시각. **웹소켓으로 보내는 `at` 과 같은 값** |

> 방 **코드**가 아니라 `room_id` 로 이어 붙인 이유: 코드는 사람이 읽는
> 값이라 규칙이 바뀔 수 있지만(6자리 → 4자리처럼), `id` 는 DB가 매기는
> 번호라 절대 바뀌지 않습니다.
>
> ⚠️ 대화를 **꺼내 보는 API는 아직 없습니다.** 저장만 됩니다.

접속·조회 방법은 [`README.md`](../README.md#데이터베이스) 참고.

## 작업 방식

- 프론트엔드 담당은 **`/openapi.json`** 또는 **`/docs`(스와거)** 를 기준으로 호출을 맞춥니다.
  (Claude에게 "이 openapi.json 스펙에 맞춰서 호출해 줘"라고 하면 됩니다.)
- 백엔드가 API를 바꾸면 `/openapi.json` 과 `/docs` 가 **자동으로 갱신**되므로
  항상 최신 계약을 참조할 수 있습니다.
- **웹소켓(WebSocket)은 이 문서에 없습니다.** 스와거가 자동 문서화해 주지 않으므로
  별도로 손수 만든 세트를 씁니다 — 화면 **<http://localhost:11000/ws-docs>**,
  명세 [`docs/asyncapi.yaml`](./asyncapi.yaml), 설명 [`docs/ws-contract.md`](./ws-contract.md).
  현재 상태: 연결 확인용 통로 하나까지.
