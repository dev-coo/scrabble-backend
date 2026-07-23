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
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

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
