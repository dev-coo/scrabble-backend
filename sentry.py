# ─────────────────────────────────────────────────────────────
# 에러 추적 (Sentry)
#
# 서버에서 오류가 터지면 Sentry 로 보냅니다. 그러면 터미널 로그를
# 뒤지지 않아도 **무슨 오류가 몇 번, 어느 줄에서** 났는지 한곳에서
# 볼 수 있습니다.
#
# 왜 필요한가: 지금은 오류가 나면 서버를 띄운 터미널에만 찍힙니다.
# 터미널을 닫으면 사라지고, 프론트엔드 담당이 "안 돼요"라고 할 때
# 백엔드 담당이 그 자리에 없으면 무슨 일이 있었는지 알 방법이 없습니다.
#
# ⚠️ **DSN 이 없으면 아무것도 보내지 않습니다.**
#    켜려면 서버를 띄울 때 환경변수를 주세요.
#      SENTRY_DSN=https://...  .venv/bin/uvicorn main:app --port 11000
#
# DSN 을 코드에 적지 않는 이유는 DB 비밀번호와 같습니다. 저장소에
# 올라가면 **누구나 우리 프로젝트로 가짜 오류를 보낼 수 있습니다.**
#
# 확인:  .venv/bin/python sentry.py
# ─────────────────────────────────────────────────────────────
import functools
import os

import sentry_sdk
from starlette.websockets import WebSocketDisconnect


# 주소 뒤에 붙어 오는 값 중 **지우고 보낼 것**.
#
# 이 백엔드는 닉네임을 `?nickname=수진` 처럼 주소에 실어 받습니다.
# `send_default_pii=False` 로도 이건 안 지워집니다 — Sentry 는 주소를
# 개인정보로 보지 않기 때문입니다. 하지만 우리에게는 **사람 이름**입니다.
SCRUB_KEYS = ("nickname", "token", "password", "secret")

REDACTED = "[지움]"


def _scrub(event, _hint):
    """보내기 직전에 개인정보를 지웁니다.

    오류를 고치는 데는 "어느 주소에서 무슨 오류"면 충분합니다.
    **누가 그랬는지까지 바깥 서비스에 쌓을 이유는 없습니다.**

    지우는 것은 값뿐이고 **열쇠(nickname=)는 남깁니다.** 그래야 나중에
    "닉네임을 받는 통로에서 났구나"를 알 수 있습니다. 통째로 지우면
    무슨 요청이었는지도 함께 사라집니다.
    """
    request = event.get("request")
    if not isinstance(request, dict):
        return event

    query = request.get("query_string")
    if isinstance(query, str) and query:
        parts = []
        for pair in query.split("&"):
            key, sep, _value = pair.partition("=")
            if sep and key.lower() in SCRUB_KEYS:
                parts.append(f"{key}={REDACTED}")
            else:
                parts.append(pair)
        request["query_string"] = "&".join(parts)

    # 쿠키·인증 헤더도 같은 이유로 지웁니다. 지금은 안 쓰지만, 나중에
    # 로그인을 붙였을 때 여기를 다시 챙길 사람이 없을 수 있습니다.
    headers = request.get("headers")
    if isinstance(headers, dict):
        for name in list(headers):
            if name.lower() in ("cookie", "authorization"):
                headers[name] = REDACTED

    return event


def setup() -> bool:
    """Sentry 를 켭니다. DSN 이 없으면 켜지 않고 `False` 를 돌려줍니다.

    서버가 켜질 때 딱 한 번 부릅니다.
    """
    dsn = os.getenv("SENTRY_DSN", "").strip()
    if not dsn:
        # DSN 이 없다고 서버를 못 켜게 하면 안 됩니다. 에러 추적은
        # **있으면 좋은 것**이지 게임이 도는 데 필요한 것이 아닙니다.
        return False

    sentry_sdk.init(
        dsn=dsn,

        # 어느 환경에서 난 오류인지. 개발 중 오류와 실제 오류가 한
        # 덩어리로 섞이면 어느 쪽을 고쳐야 할지 알 수 없습니다.
        environment=os.getenv("SENTRY_ENV", "development"),

        # ⚠️ **개인정보를 함께 보내지 않습니다.**
        #
        # 켜면 요청에 들어 있던 값(닉네임, 주고받은 대화 등)까지 Sentry 로
        # 올라갑니다. 오류를 고치는 데는 "어느 줄에서 무슨 오류"면 대개
        # 충분하고, 사람들이 나눈 대화까지 바깥 서비스에 쌓을 이유는
        # 없습니다. 기본값도 False 지만, **일부러 그렇게 정했다는 것**이
        # 드러나도록 적어 둡니다.
        send_default_pii=False,

        # ⚠️ **오류가 난 지점의 변수값을 담지 않습니다.**
        #
        # Sentry 는 기본으로 그때 그 자리에 있던 변수를 전부 담아 보냅니다.
        # 고칠 때는 편하지만, 이 백엔드에서 그 변수들은 **닉네임·손패·
        # 주고받은 대화** 그 자체입니다. 실제로 확인해 보니 `send_default_pii`
        # 를 꺼도 변수값으로 닉네임이 그대로 올라갔습니다.
        #
        # 변수 이름으로 골라 지울 수는 없습니다. 실제로 담긴 이름이
        # `nickname` 만이 아니라 `n`, `args[0]`, `func` 처럼 제각각이라
        # 목록으로 막는 방식은 반드시 새는 곳이 생깁니다.
        #
        # 이걸 끄면 "어느 파일 몇 번째 줄, 어떤 함수에서 무슨 오류"까지는
        # 그대로 옵니다. 대개 그걸로 충분하고, 사람들의 대화를 바깥
        # 서비스에 쌓는 것보다 낫습니다.
        include_local_variables=False,

        # 위 설정만으로도 **주소 뒤에 붙은 값은 안 지워집니다.**
        # 이 백엔드는 닉네임을 `?nickname=수진` 으로 받기 때문에 그대로
        # 두면 사람 이름이 올라갑니다. 그래서 보내기 직전에 한 번 더 지웁니다.
        before_send=_scrub,

        # 속도 측정(어느 요청이 느린지)을 얼마나 표본으로 담을지.
        # 0 이면 안 담습니다. 오류만 보려는 것이라 기본을 0 으로 두고,
        # 필요할 때 환경변수로 올립니다. 1.0 으로 두면 모든 요청이
        # 올라가서 무료 사용량을 금방 씁니다.
        traces_sample_rate=float(os.getenv("SENTRY_TRACES", "0")),
    )
    return True


def catch_ws(handler):
    """웹소켓 통로에서 난 오류를 Sentry 로 보내는 덮개.

    **왜 따로 필요한가:** Sentry 가 FastAPI 에 끼워 넣는 부품은 HTTP 요청만
    지켜봅니다. `@app.websocket()` 안에서 터진 오류는 **그냥 조용히
    사라집니다.** 실제로 확인해 봤습니다 — HTTP 오류는 올라가는데
    웹소켓 오류는 하나도 안 올라갔습니다.

    이 백엔드는 방·채팅·게임이 전부 웹소켓입니다. 이게 없으면 정작 중요한
    곳의 오류를 하나도 못 보면서 **"Sentry 붙였으니 보고 있다"고 믿게**
    됩니다. 그건 아예 안 붙인 것보다 나쁩니다.

    잡은 뒤에는 **다시 던집니다.** 여기서 삼키면 FastAPI 가 뒷정리를
    못 하고, 무엇보다 원래 동작이 달라집니다. 이 덮개는 "지켜보기"만
    해야 하고 흐름을 바꾸면 안 됩니다.
    """

    @functools.wraps(handler)
    async def wrapped(*args, **kwargs):
        try:
            return await handler(*args, **kwargs)
        except WebSocketDisconnect:
            # 사용자가 창을 닫은 것입니다. **정상입니다.** 이걸 오류로
            # 올리면 Sentry 가 평범한 나가기로 가득 차서, 진짜 오류가
            # 그 사이에 묻힙니다.
            raise
        except Exception as e:
            sentry_sdk.capture_exception(e)
            raise

    return wrapped


if __name__ == "__main__":
    # 직접 실행하면 **일부러 오류를 하나 내서** 연결을 확인합니다.
    #
    # 실제로 보내 보지 않으면 "설정은 했는데 안 올라가는" 상태를
    # 알아챌 수 없습니다. 그건 정작 오류가 났을 때 알게 됩니다.
    if not setup():
        print("SENTRY_DSN 이 없어서 켜지지 않았습니다.")
        print("이렇게 실행해 보세요:")
        print("  SENTRY_DSN=https://...  .venv/bin/python sentry.py")
        raise SystemExit(1)

    print("Sentry 켜짐. 시험용 오류를 하나 보냅니다…")
    try:
        raise RuntimeError("스크래블 백엔드 연결 확인용 오류입니다 (무시하세요)")
    except RuntimeError as e:
        sentry_sdk.capture_exception(e)

    # 보내는 일은 뒤에서 도는데, 프로그램이 먼저 끝나면 못 보냅니다.
    sentry_sdk.flush(timeout=5)
    print("보냈습니다. Sentry 화면(Issues)에서 확인하세요.")
