# ─────────────────────────────────────────────────────────────
# 단어 사전 — "이게 진짜 단어인가?"를 판단하는 곳
#
# 스크래블은 아무 글자나 늘어놓는 게임이 아닙니다. 실제로 있는 단어여야
# 인정됩니다. 그 판단 기준이 이 파일입니다.
#
# 왜 백엔드가 판단하는가:
#   프론트엔드가 판단하면 **사용자가 고칠 수 있습니다.** 브라우저에서
#   도는 코드는 누구나 열어 볼 수 있고 바꿀 수도 있어서, "아무 단어나
#   통과"로 만들어 버리면 막을 방법이 없습니다.
#   점수가 걸린 판단은 반드시 서버에서 해야 합니다.
#
# 왜 사전 파일을 저장소에 넣었는가:
#   맥에는 `/usr/share/dict/words` 가 원래 들어 있어서 그걸 그냥 읽을
#   수도 있습니다. 하지만 그러면
#     ① 그 파일이 없는 컴퓨터에서는 서버가 안 돕니다
#     ② 어떤 단어를 인정했는지 저장소에 **기록이 남지 않습니다**
#   나중에 "왜 이 단어가 안 됐지?"를 따질 때 기록이 없으면 알 수 없습니다.
#   그래서 걸러낸 결과를 `data/words.txt` 로 넣어 두었습니다.
#
# 확인:  .venv/bin/python dictionary.py
# ─────────────────────────────────────────────────────────────
from pathlib import Path
from typing import FrozenSet

WORDS_FILE = Path(__file__).parent / "data" / "words.txt"

# 스크래블에서 한 글자는 단어로 치지 않습니다.
MIN_WORD_LENGTH = 2

# 보드 한 줄이 15칸이라 그보다 긴 단어는 놓을 자리가 없습니다.
MAX_WORD_LENGTH = 15


def _load_words() -> FrozenSet[str]:
    """사전 파일을 통째로 읽어 **한 덩어리**로 들고 있습니다.

    `frozenset` 으로 두는 이유:
      ① 찾는 게 빠릅니다. 20만 개를 처음부터 훑으면 제출할 때마다
         오래 걸리는데, 이 방식은 개수와 상관없이 한 번에 찾습니다.
      ② 나중에 실수로 단어를 더하거나 지울 수 없습니다. 사전은 게임
         도중에 바뀌면 안 되는 값입니다.

    서버가 켜질 때 **한 번만** 읽습니다. 제출할 때마다 파일을 열면
    그때마다 20만 줄을 다시 읽게 됩니다.
    """
    if not WORDS_FILE.exists():
        # 조용히 빈 사전으로 돌면 **모든 단어가 틀렸다고 나옵니다.**
        # 원인을 찾기 아주 어려운 고장이라, 아예 못 켜지게 막습니다.
        raise FileNotFoundError(
            f"사전 파일이 없습니다: {WORDS_FILE}\n"
            "저장소에 함께 들어 있어야 합니다. git 에서 받아왔는지 확인하세요."
        )

    with WORDS_FILE.open(encoding="utf-8") as f:
        return frozenset(line.strip() for line in f if line.strip())


WORDS: FrozenSet[str] = _load_words()
WORD_COUNT = len(WORDS)


def is_word(word: str) -> bool:
    """이게 사전에 있는 단어인가.

    대소문자는 가리지 않습니다. 사전은 전부 대문자로 저장돼 있고,
    타일도 대문자라 여기서 맞춰 줍니다. 프론트엔드가 소문자로 보냈다고
    틀렸다고 하는 건 불친절합니다.
    """
    return word.strip().upper() in WORDS


# 사전을 못 읽었으면 서버가 켜지면 안 됩니다. 위에서 파일이 없으면
# 이미 막았지만, 파일이 있는데 텅 비어 있는 경우도 마찬가지입니다.
assert WORD_COUNT > 0, "사전이 비어 있습니다"


if __name__ == "__main__":
    print(f"사전 {WORD_COUNT:,}개 단어 ({WORDS_FILE})")
    print(f"길이 제한: {MIN_WORD_LENGTH}~{MAX_WORD_LENGTH}자\n")
    for w in ("CAT", "QUIZ", "SCRABBLE", "cat", "ZZZZ", "ASDFGH"):
        print(f"  {w:10} → {'있음' if is_word(w) else '없음'}")
