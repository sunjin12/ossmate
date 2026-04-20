# Ossmate — 포트폴리오 요약

**한 줄 소개**: Claude Code의 12개 확장 표면을 모두 결합해 OSS 메인테이너의 반복 업무를 자동화한 오픈소스 CLI + 플러그인.

- **저장소**: [github.com/sunjin12/ossmate](https://github.com/sunjin12/ossmate)
- **배포**: PyPI (`ossmate`, `ossmate-mcp`), Claude Code 플러그인 마켓플레이스
- **규모**: Python 3.11+, 176개 테스트(pytest, ~5s), 3-OS × 3-Python CI 매트릭스, 10개 phase 태그
- **기간**: Phase 0 → v0.1.0 까지 단계적 자체 빌드, v0.1.x 패치(PR #1~#4)까지 self-dogfooding 중
- **1인 프로젝트** (기획·설계·구현·배포·유지보수 전 과정)

---

## 1. 어떤 문제를 해결하려 했는가

### 1차 문제 — OSS 메인테이너의 반복 업무

솔로 메인테이너는 본업(기능 개발, 리뷰) 외에 **반복적이고 집중력을 갉아먹는 운영 업무**에 시간을 뺏긴다:

| 업무 | Ossmate 없을 때의 마찰 |
|---|---|
| PR 트리아지 | PR 하나당 diff·커밋·CI 읽고 scope/risk/mergeability 판단을 매번 수동 |
| 이슈 분류 | 받은 이슈를 bug/feature/docs/duplicate 등으로 라벨링하는 반복 |
| 릴리스 노트 작성 | 직전 태그 이후 커밋을 긁어 Keep-a-Changelog 포맷으로 재가공 |
| 의존성 감사 | lockfile 파싱 + OSV advisory 조회 스크립트를 매번 재구성 |
| Stale 이슈 정리 | "60일 넘게 대기 중인 이슈"를 찾아 nudge/close 결정 |
| 컨트리뷰터 온보딩 | 첫 기여자에게 보낼 환영 메시지를 매번 수동 작성 |

이 업무들은 **패턴은 반복되지만 개별 판단이 필요**해서 완전 자동화도, 완전 수동도 비효율적이다. LLM이 보조하기에 적합한 지점.

### 2차 문제 — Claude Code 확장 표면 학습

Claude Code는 12개의 확장 지점(Skills, Subagents, Hooks, MCP, Plugin, Agent SDK, Scheduled triggers, Status line, Output styles, Memory, Settings, Keybindings)을 제공하지만, **이들을 단일 제품 안에서 통합해 운영한 사례가 부족**했다. 각 표면이 실제 도메인 문제에 어떤 가치를 더하는지 체감하려면 직접 만들어보는 것이 가장 빠르다고 판단.

→ **Ossmate는 "실용 도구"와 "Claude Code 레퍼런스 구현체" 두 목적을 동시에 충족하도록 설계**했다.

---

## 2. 어떻게 구현했는가

### 설계 원칙: 10단계, 각 단계는 독립 시연 가능

| Phase | 성과물 |
|---|---|
| 0 | Skeleton (pyproject × 2, CLAUDE.md, settings.json) |
| 1 | Output style + status line — **즉각적 시각 피드백** |
| 2 | 첫 Skill `/triage-issue` — Bash-only, MCP 전 단계 |
| 3 | 5개 Hook (PreToolUse guard 포함) |
| 4 | MCP 서버 — 11 tools + 3 resource templates |
| 5 | 6개 Subagent (haiku/sonnet/opus 티어링) + 나머지 Skill 리팩터 |
| 6 | Plugin 패키징 + 자체 marketplace.json |
| 7 | 독립 CLI (`.claude/commands/*.md` 본문을 CLI가 재로딩 → 1회 작성으로 slash+subcommand 동시 지원) |
| 8 | Scheduled triggers (daily digest, weekly stale sweep, Friday release radar) |
| 9 | CI/CD 3-OS × 3-Python 매트릭스 + OIDC PyPI 발행 → v0.1.0 cut |

각 phase는 `phase-N` 태그로 마킹되어 `git checkout phase-5`로 당시 스냅샷을 볼 수 있다. **어느 phase에서 멈춰도 독립 데모가 가능**하게 설계 — 스코프가 터지는 것을 방지.

### 아키텍처

```
User ─┬─ /slash commands ──► Claude Code ──► Skills ──► Subagents ──► MCP ──► GitHub API
      └─ ossmate CLI ─────► Agent SDK ────────────────────────────┘          OSV.dev
                                                                              Local repo
```

**같은 MCP 서버가 Plugin과 CLI 양쪽을 백엔드로 지원** → 도구(gh 호출, OSV 조회, lockfile 파싱)를 1회 구현하면 모든 진입점에서 재사용.

### 표면별 선택 근거

12개 표면 각각이 "없을 때 어떤 마찰이 생기는지"로 정당화 ([README.md:111-130](../README.md#L111-L130) 표). 데모용 끼워 맞추기가 아니라 실제 사용 시나리오에서의 역할을 기준으로 함:

- **Subagents 모델 티어링** — bulk 이슈 분류는 Haiku, 보안 리뷰는 Opus, PR 트리아지는 Sonnet. 단일 모델 사용 대비 비용/속도 최적화.
- **Hooks PreToolUse guard** — `git push origin main`, `gh pr merge`, `gh release create` 등 파괴적 명령을 사전 차단. 나중에 내가 PR을 머지하려 했을 때 이 훅이 나를 막아서 self-dogfooding이 증명됨.
- **MCP vs 인라인 스크립트** — gh/OSV/lockfile 로직을 MCP에 두면 Claude Code/CLI/다른 AI 클라이언트 모두에서 재사용 가능.
- **Plugin vs CLI** — Plugin은 Claude Code 사용자에게 즉시 설치 가능, CLI는 CI/원격 shell/non-Claude-Code 환경용. 공통 skill body를 공유해 이중 유지보수 회피.

---

## 3. 구현 과정의 문제와 결정

### 3.1 "모든 표면을 쓸 것인가" 스코프 결정

초기에 고민: Skills + MCP 2개만으로도 실용 도구는 완성된다. 12개 표면 전부를 쓰는 건 과한가?

**결정**: 모든 표면 사용. 단, 각 표면을 "쓰기 위해 쓰는" 게 아니라 **특정 마찰을 제거하는 역할로만 배치**. Keybindings는 가장 가치가 낮다는 것을 명시 (README 표에서 "가장 낮은 가치" 레이블). 정당화되지 않는 표면은 쓰지 않는 편이 낫다는 기준을 세움.

**왜**: 포트폴리오 가치(레퍼런스 구현체) + 학습 가치(각 표면의 실제 제약을 체감) + 코드 재사용 설계(MCP를 공유하면 표면 추가가 오히려 쉬워짐).

### 3.2 Plugin과 Standalone CLI의 중복 문제

둘 다 지원하면 slash command 본문과 CLI prompt 본문이 이중화된다. 유지보수 악몽.

**결정**: `.claude/commands/*.md`를 단일 소스로 두고, CLI가 파일 시스템에서 직접 markdown body를 로드해 `ClaudeAgentOptions`로 넘김. → skill 1회 작성으로 slash + subcommand 동시 지원. `test_no_orphan_subcommands`가 불일치를 막음.

**영향**: Phase 7에서 `doctor`를 추가할 때 CLI 전용(slash 커맨드 없음)이라는 예외가 생겼고, `cli_only_allowlist = {"version", "doctor"}`로 명시적 화이트리스트 처리.

### 3.3 Windows cp949 locale 지원

`doctor` 구현 중 `subprocess.run(text=True)`가 cp949 locale에서 `UnicodeDecodeError` 발생. macOS/Linux CI에서는 안 보이는 문제.

**결정**: 모든 subprocess 호출에 `encoding="utf-8", errors="replace"` 명시. Hook 스크립트에는 별도 메모리에 "Windows 환경 제약" 저장해 반복 학습 회피.

### 3.4 CI가 3개 커밋 동안 Red였지만 알아채지 못함

`phase-9` 머지 후 `test_referenced_hook_scripts_exist`가 Linux/macOS에서 실패하고 있었으나, 로컬 Windows에서는 pathlib가 backslash를 흡수해 통과. 알림 파이프라인 부재로 3 커밋 동안 모르고 진행. `doctor` PR에서야 발견.

**결정**:
1. 즉시 수정: 정규식 `[^\"]+` → `[^\"\\]+` (trailing backslash 제외)
2. 같은 PR에 pre-existing lint 에러(24건) 일괄 정리 — 한 번의 green bar 복원
3. 메모리에 "CI 알림 파이프라인 필요" 기록 → 다음 v0.1.x 후보로 큐잉

**배운 점**: 멀티 OS 매트릭스만 있으면 안 되고, **실패를 알려주는 채널**이 필요. (다음 반복에서 Slack webhook or badge monitoring 예정)

### 3.5 자신의 PreToolUse Hook에 막힘 (self-dogfooding)

PR #3 머지 시 `gh pr merge`를 시도했으나 내가 Phase 3에서 만든 PreToolUse guard가 `gh pr merge is denied. Merge through the GitHub UI after maintainer review.`로 차단.

**결정**: 우회하지 않음. 사용자가 GitHub UI로 직접 머지. → **이 프로젝트의 보안 정책이 실제로 작동한다는 증거**. CHANGELOG와 포트폴리오에 이 일화를 남김.

### 3.6 `ossmate doctor` 스코프 (평가 후 선택)

Phase 9 회고에서 "온보딩 마찰"이 중간 심각도 약점으로 식별. 후보 3개:

| 후보 | 범위 | 리스크 |
|---|---|---|
| Eval suite | 크다 (2~3일) | 스코프 터짐 |
| Hygiene bundle (템플릿 등) | 작다 (30분) | 임팩트 약함 |
| **`ossmate doctor`** (선택) | 중간 (2~3시간) | 적절 |

**결정 근거**: 가장 흔한 실패 케이스(gh 미설치, 디렉터리 오류, MCP 불량)의 80%를 1개 명령으로 자가 진단. 신규 의존성 0개 (기존 `rich` 재사용). 6개 check × ≥5개 테스트로 스코프 고정. → PR #3으로 merge.

### 3.7 Dead link 청소 (PR #4)

`docs/architecture.md` 링크가 README에 있었으나 파일이 존재하지 않음(사용자가 발견). 그 외 2개 phase 문서 링크도 메모리 경로(`memory/project_phases.md`)로 잘못 연결.

**결정**: 파일을 새로 만드는 대신 표를 인라인화(README 12-surface 정당화). phase 설명만 실제 공개 문서 가치가 있으므로 `docs/project_phases.md`로 materialize. 부수적으로 `.claude/CLAUDE.md`의 "docs는 공개 explainer만 허용" 규칙을 완화해 docs/ 사용 경로를 열어둠.

**배운 점**: 공개 저장소의 dead link는 recruiter 신뢰도에 직접적 영향 → 작은 docs 청소가 기술 구현만큼 중요.

---

## 4. 자체 평가

### 잘한 점

- **스코프 통제**: 10 phase 계획 → 실제로 10 phase에서 v0.1.0 cut. 중간에 추가 ambition 없이 릴리스. `[Unreleased]` 규약으로 v0.1.x 반복 빌드.
- **self-dogfooding**: 자기 repo에서 Ossmate가 돌아감. 훅이 나를 막고, scheduled trigger가 이 저장소에 daily digest를 돌리고, CHANGELOG는 Ossmate가 생성. 메타적 일관성.
- **테스트 밀도**: 176 hermetic 테스트, ~5s. 신규 기능마다 ≥5개 추가 규칙. pre-existing 버그까지 같은 PR에서 치워 CI가 항상 green.
- **멀티 플랫폼**: Windows에서 개발, Linux/macOS CI에서 검증. cp949 · path separator · hook 실행 규약 모두 명시적으로 해결.
- **OIDC 배포**: PyPI 토큰 시크릿 0개. 태그 push로 릴리스, 워크플로우가 tag vs pyproject 버전 불일치를 거부.
- **Dogfood 설계 결정이 증명됨**: PreToolUse hook이 내 자신의 `gh pr merge`를 실제로 막았다는 경험 — 보안 정책이 살아있음을 확인.

### 약한 점

- **CI 알림 갭**: 3 커밋 동안 main이 red였으나 알아채지 못함. Badge/Slack/email 파이프라인 없음. 다음 반복의 최우선 후보.
- **온보딩 마찰**: `doctor`로 80% 완화했으나, 여전히 `pipx` + `gh auth` + MCP 설치까지 수 단계. 신규 사용자에게는 많다.
- **실제 사용자 0명** (나 제외): Phase 9까지는 빌드 사이클, v0.1.x 이후에야 공개. 현재로선 adoption 데이터가 없어 실제 가치 측정 한계.
- **Keybindings 표면**: 12 표면 중 가장 약한 고리. 솔직하게 "가장 낮은 가치"로 레이블링했지만, 포함 여부를 다시 고민할 만함.
- **Node.js 20 deprecation** 등 actions 버전 관리: dependabot 미설정 상태로 메인테이너 주기가 오면 수동 감시 필요.

### 이 프로젝트에서 배운 것

1. **도구를 만드는 것보다 "어떤 마찰을 없애는지" 명확히 하는 게 먼저**. 12개 표면 각각을 친숙해지기 위해 쓰는 게 아니라, 특정 마찰의 해소자로만 배치한 것이 전체 응집도를 결정함.
2. **공통 데이터 소스(MCP)에 투자**. Plugin과 CLI를 둘 다 지원한 대신
3. **자기 도구로 자기를 관리하면(self-dogfood) 버그가 자발적으로 드러남**. Hook이 나를 막을 때, 정책이 설계대로 작동하는지 확인할 수 있었음.
4. **"독립 시연 가능한 phase"**라는 스코프 원칙이 기술/인지 부채를 막는다.
5. **Windows 개발 + Linux CI**는 공짜가 아니다. 로컬에서 안 보이는 실패를 잡으려면 매트릭스와 알림 파이프라인을 같이 갖춰야 함 (후자는 아직 미흡).
6. **구현하려는 것에 대한 이해가 중요** 하네스 프로그래밍을 위해 클로드 코드가 추천한 OSS support 프로젝트를 수행했는데 OSS 관리에 대한 배경지식이 부족하다보니까 개발이 어려웠다. 외주를 진행했다는 느낌으로 프로젝트를 수행했다. 다음에 프로젝트를 한다면 개발하려는 분야의 도메인 지식을 먼저 쌓고 개발 시작할 것


### 다음 v0.1.x 로드맵 후보

- CI 실패 알림 파이프라인 (Slack webhook / email / badge audit)
- Dependabot + Node.js 20 → 최신 actions 버전 상향
- PR/Issue 템플릿 (`.github/` 아래)
- 실제 사용자 피드백 수집 후 `doctor` 체크 확장 (git-lfs, Node 버전, 플러그인 마켓 동기화)
- Eval suite — skill 출력 품질 회귀 감지

---

## 관련 문서

- [README](../README.md) — 빠른 시작, 표면별 가치
- [docs/project_phases.md](project_phases.md) — 10개 phase 상세 계획
- [CHANGELOG](../CHANGELOG.md) — 버전별 변경 이력 (Ossmate 자체가 생성)
- [CONTRIBUTING](../CONTRIBUTING.md) — 개발 환경 / 커밋 규약
