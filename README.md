# Scrabble Backend

스크래블 프로젝트의 백엔드 저장소입니다.

## 프롬프트 로그 (협업용)

이 저장소는 **Claude에게 입력한 프롬프트가 자동으로 기록**됩니다.
- 파일: [`PROMPTS.md`](./PROMPTS.md)
- 기록 내용: `[타임스탬프] 작성자` + 입력한 질문/명령 (Claude의 응답은 기록되지 않음)
- 동작 방식: Claude Code의 `UserPromptSubmit` 훅 (`.claude/hooks/log-prompt.sh`)

### 시작하기 (각 사용자)

1. 저장소를 클론합니다.
2. 작성자 이름이 로그에 표시되도록 git 사용자명을 설정합니다.
   ```bash
   git config user.name "본인이름"
   ```
3. 이 폴더에서 `claude`를 실행합니다.
4. 처음 실행 시 Claude Code가 프로젝트 훅 실행 승인을 물어보면 허용합니다.
5. 이제부터 입력하는 모든 프롬프트가 `PROMPTS.md`에 자동 기록됩니다.

### 로그 공유

작업 중 또는 작업 후, `PROMPTS.md`를 커밋/푸시하면 서로의 프롬프트를 비교하며 논의할 수 있습니다.
```bash
git add PROMPTS.md
git commit -m "chore: update prompt log"
git push
```
