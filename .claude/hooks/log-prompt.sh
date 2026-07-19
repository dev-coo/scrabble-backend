#!/usr/bin/env bash
#
# UserPromptSubmit hook
# 사용자가 Claude에 입력한 프롬프트를 PROMPTS.md에 기록한다.
# - 기록 대상: 사용자의 질문/명령만 (Claude의 응답은 절대 기록하지 않음)
# - 형식: 타임스탬프 + 작성자 + 프롬프트 본문(Markdown)
#
# 주의: 이 훅은 stdout으로 아무것도 출력하지 않는다.
#       (UserPromptSubmit 훅의 stdout은 프롬프트에 주입되므로)
#       로그 기록 실패가 사용자의 작업을 막지 않도록 항상 exit 0.

input=$(cat)

# --- 훅 JSON에서 필드 추출 (jq 우선, 없으면 python3) ---
read_field() {
  local key="$1"
  if command -v jq >/dev/null 2>&1; then
    printf '%s' "$input" | jq -r --arg k "$key" '.[$k] // empty' 2>/dev/null
  elif command -v python3 >/dev/null 2>&1; then
    printf '%s' "$input" | python3 -c "import sys,json
try:
    print(json.load(sys.stdin).get('$key',''))
except Exception:
    pass" 2>/dev/null
  fi
}

prompt=$(read_field prompt)
cwd=$(read_field cwd)

# 빈 프롬프트면 기록하지 않음
[ -z "$prompt" ] && exit 0

# --- 작성자: git user.name, 없으면 시스템 계정명 ---
author=$(git config user.name 2>/dev/null)
[ -z "$author" ] && author="${USER:-unknown}"

ts=$(date '+%Y-%m-%d %H:%M:%S')

# --- 로그 파일은 저장소 루트에 위치 ---
root="${CLAUDE_PROJECT_DIR:-$cwd}"
root="${root:-.}"
log="$root/PROMPTS.md"

# 헤더는 최초 1회만 생성
if [ ! -f "$log" ]; then
  {
    printf '# Prompt Log\n\n'
    printf '사용자가 Claude에게 입력한 프롬프트 기록입니다. (질문/명령만, 응답 제외)\n'
  } > "$log"
fi

# 프롬프트 각 줄을 Markdown 인용문(blockquote)으로 변환
quoted=$(printf '%s\n' "$prompt" | sed 's/^/> /')

{
  printf '\n### [%s] %s\n\n' "$ts" "$author"
  printf '%s\n' "$quoted"
} >> "$log"

exit 0
