# 오케스트레이션, Agent, MCP, Gateway

[매뉴얼 인덱스](index.md) · [English](../en/orchestration.md)

단일 명령을 실행하는 것이 아니라 여러 연구 도구를 MagLab이 조율하게 하고
싶을 때 사용합니다.

## 터미널 실행 화면

실제 MagLab CLI에서 Anthropic Haiku로 실행한 one-shot orchestration 화면입니다.

![MagLab Haiku 오케스트레이션 터미널 캡처](../../assets/terminal/orchestration-haiku.png)

PI에서도 같은 작업을 대화형으로 운용할 수 있습니다. 시작 화면에는 skill conflict
없이 로드된 skill/extension이 보여야 합니다.

![PI 대화형 시작 터미널 캡처](../../assets/terminal/pi-agents.png)

PI 안에서는 `!` operator로 MagLab 명령을 실행합니다.

![PI Haiku 오케스트레이션 터미널 캡처](../../assets/terminal/pi-orchestration-haiku.png)

harness readiness와 handoff 흐름도 명시적인 CLI action으로 확인합니다.

![PI harness 오케스트레이션 터미널 캡처](../../assets/terminal/pi-orchestration-harness.png)

## Interactive와 one-shot 사용

```sh
maglab
maglab -p "Plan a reproducible SOT analysis workflow for Pt/CoFeB/MgO"
maglab doctor
maglab doctor --smoke
maglab workspace brief
maglab workspace tree --summary --type docs --max-depth 2
maglab workspace tree --changed
```

REPL은 자연어 표면입니다. deterministic tool, notebook, literature workflow,
analysis, authoring으로 작업을 라우팅하는 데 사용합니다.

설치 직후에는 `maglab doctor`를 먼저 실행하세요. 현재 workspace, `MAGLAB.md`,
configured backend, optional research extra, 외부 solver, simulation readiness를
비밀값 출력 없이 한 번에 점검합니다.
기본 doctor는 빠른 등록 상태 확인만 수행합니다. 실제 LLM sentinel prompt까지
보내 delegated CLI/API 출력이 순수 model content로 parse되는지 검증하려면
`maglab doctor --smoke`를 사용하세요.

프로젝트 질문을 하기 전에는 `workspace brief`로 현재 폴더를 먼저 요약하세요.
폴더가 크면 `workspace tree --type docs|code|data`, `--max-depth`,
`--changed`로 MagLab이나 모델이 볼 범위를 좁힐 수 있습니다.

## Credential과 configuration

```sh
maglab auth codex
maglab auth anthropic
maglab auth grok
maglab auth deepseek
maglab auth qwen
maglab auth kimi
maglab auth gemini
maglab auth openai
maglab auth list
maglab auth test anthropic
maglab auth status
maglab doctor --feature llm
maglab config
maglab cost
maglab theme list
maglab theme set mono
```

Codex는 먼저 공식 Codex CLI에서 인증합니다. 그 다음 `maglab auth codex`를
실행하거나 REPL 안에서 `/connect codex`를 사용하세요. MagLab은
`config.toml`에 backend 선택만 저장하고 Codex OAuth token은 공식 CLI에 남깁니다.

REPL에서는 `/help quick`이 첫 사용 경로를 보여주고, `/help all`이 전체 tree를
보여줍니다. `/help workspace`, `/help llm`, `/help sim`, `/help figure`처럼
영역별 help도 볼 수 있습니다.

직접 API provider는 provider 명령을 실행한 뒤 터미널 숨김 입력으로 key를
넣습니다. REPL에서는 `/connect anthropic`, `/connect grok`,
`/connect deepseek`, `/connect qwen`, `/connect kimi`, `/connect gemini`,
`/connect openai`를 사용할 수 있습니다. 각 provider는 별도의 MagLab runtime
profile을 로드하므로, 모델은 자신이 MagLab research orchestration agent로
동작한다는 전제와 provider별 planning/verification 지침을 함께 받습니다.

## 승인과 자율성

모델이 호출하는 모든 도구는 실행 전에 훅 계층을 통과합니다: deny 규칙, 물리
정합성 오라클, 자율성 게이트. 게이트는 각 도구가 선언한 힌트(read-only 여부,
파괴적 여부, 네트워크 사용 여부)로 등급을 매기고, 설정된 모드가 처리를
결정합니다:

| 모드 | 묻지 않고 실행 | 승인을 묻는 대상 |
|---|---|---|
| `copilot` (기본) | 읽기 전용·오프라인 도구 | 쓰기 또는 네트워크 접근 |
| `semi-auto` | 위 + 읽기 전용 네트워크 도구 | 되돌릴 수 없는 작업 |
| `autonomous` | 위 + 되돌릴 수 없는 작업 | 파괴적 도구만 |

대화형 터미널에서는 승인이 필요한 작업이 stderr로 묻고 `y`를 기다립니다.
터미널이 없으면 — 파이프로 넘긴 `maglab -p`, CI, cron — 물어볼 상대가 없으므로
거부하고 그 이유를 모델에게 돌려줍니다(명령 자체가 죽지는 않습니다). 배치
실행에서 그게 곤란하면 모드를 명시적으로 올리십시오:

```sh
maglab config set autonomy.mode semi-auto
maglab config show
```

`literature_search`·`provenance_query`·`physics_compute` 같은 읽기 전용 도구는
승인을 묻지 않습니다. 손으로 관리하는 목록이 아니라 도구 자신이 선언한 힌트로
분류되기 때문입니다.

## 백엔드별 도구 동작

`api` 백엔드는 MagLab의 tool schema를 provider에 그대로 전달합니다. delegated
CLI 백엔드(`codex`·`claude`·`gemini`)는 커맨드라인으로 tool schema를 받지
않으므로, MagLab이 프롬프트에 도구를 서술하고 응답을 파싱해 tool call로
되돌립니다. 어느 쪽이든 호출은 동일한 registry와 동일한 훅을 통해 MagLab이
실행하므로, 숫자와 인용은 모델이 아니라 결정론적 도구에서 나옵니다 — delegated
CLI가 자체적으로 갖고 있는 shell·파일 도구가 아니라.

프로토콜을 따르지 않는 모델은 그냥 산문으로 답합니다. 깨지지는 않고, 도구가
뒷받침하지 않은 답을 받을 뿐입니다.

이 CLI들은 completion endpoint가 아니라 에이전트라 시작이 느립니다. `codex`는
답하기 전에 약 19k 토큰의 컨텍스트를 보내고 한 단어 답변에도 수 초가 걸립니다.
그래서 delegated CLI 타임아웃 기본값은 900초입니다. 긴 연구 턴이 그래도 넘치면
오류 메시지가 설정 이름을 알려줍니다:

```sh
maglab config set backend.delegated_cli.timeout 1800
```

## Subagent와 skill

```sh
maglab agents list
maglab agents show citation-auditor
maglab skill list
maglab harness doctor
maglab harness compile literature-review
maglab harness compile --write
maglab harness compile --check
maglab harness run literature-review --dry-run --output text
maglab harness run literature-review --topic "Find SOT papers" --execute-local --local-max-steps 2 --output text
maglab harness pi-tool --payload-json '{"workflow":"literature-review","input":"Find SOT papers"}' --output text
maglab run "Find SOT papers" --harness-workflow literature-review
maglab harness worker search-scout --task "Find SOT papers"
maglab harness worker search-scout --task "Find SOT papers" --json
```

Subagent는 `harness.manifest.json`에 선언되어 있습니다. local corpus checking,
search scouting, citation auditing, paper review, physics validation, result
analysis, experiment management, hypothesis generation, communications writing
같은 bounded role을 나타냅니다.

현재 실행 표면은 세 가지입니다.

- Legacy MagLab CLI/REPL mode: `maglab`, `maglab -p ...`, Ralph, 기존
  orchestrator는 MagLab의 기존 backend 계층으로 model call을 라우팅합니다.
- Deterministic command: `maglab physics ...`, `maglab lit ...`,
  `maglab analyze ...`, `maglab figure ...` 같은 명령은 구체적인 MagLab
  모듈을 실행합니다. 해당 기능이 별도로 요구하지 않으면 LLM key가 필요하지
  않습니다.
- Harness mode: `maglab harness ...`는 manifest를 검사 가능한 실행 계획으로
  바꿉니다. 계획 수립은 결정론적이고 오프라인이며 — provider를 호출하지 않습니다 —
  `--execute-local`은 그 계획을 MagLab 자체 subagent runner로 실행하므로 기존
  4계층 검증·훅·예산 회계가 모든 단계에 그대로 적용됩니다. live PI 실행은 환경
  게이트가 걸리며 절대 흉내내지 않습니다.

`maglab harness doctor`는 실행을 막는 것을 구체적으로 보고합니다: 선언된 agent로
해석되지 않는 workflow step, `agents/*.md`가 없는 agent, 설치되지 않은 skill,
등록되지 않은 MCP 서버, LLM backend 설정 여부. PI 관련 두 항목은 보고만 하고
차단하지 않습니다 — 로컬 실행에는 PI가 필요 없고, 애초에 base binary에는
`workflow` 툴이 없습니다(그건 pi-agents가 제공합니다).

`maglab harness compile literature-review`로 컴파일된 workflow를 보고,
`maglab harness compile --write`로 `.pi/workflows/`에 드리프트 산출물을 쓰며,
`maglab harness compile --check`로 routing table이 바뀌었을 때 실패시킵니다.
산출물에는 절대 경로·로컬 설치 상태·타임스탬프가 없어 머신 독립적이므로 CI에
걸어도 안전하고, 실제 manifest 변경에만 실패합니다.

`maglab harness run <workflow> --dry-run --output text`는 실행될 내용을 표로
보여주고, `--output json`(기본값)은 전체 계약을 냅니다: step별 `local_run_plan`,
PI `workflow` 툴용 topic 바인딩 `pi_agents_workflow_payload`, PI flow id와
provenance activity를 담는 `cross_links`. `ready`와 `blockers`는 항상 일치하며,
실행을 막지는 않고 품질만 떨어뜨리는 항목(예: 선언됐지만 미등록인 MCP 서버)은
`warnings`로 갑니다.

여기서 실행하려면 `--execute-local`을, 저렴한 live smoke에는
`--local-max-steps 2`를 씁니다. 이 옵션 이름은 실제 동작 그대로입니다 —
subagent runner가 step당 완성 1회를 발행하므로 step 내부의 turn이 아니라 step
수를 제한합니다. 각 step은 topic과 앞선 step 결과 요약을 함께 받으며, 검증에
실패한 step이 나오면 이후 작업이 그 위에 쌓이지 않도록 실행을 멈춥니다.

`maglab harness worker <agent> --task "..."`는 단일 subagent의 계획을 보여줍니다
— model alias, 해석된 model, tools, 발견된 skill, 등록된 MCP 서버. 기계용
출력은 `--json`입니다.

`--record-provenance --provenance-db .maglab/harness-provenance.sqlite`를 붙이면
아무것도 실행되기 전에 *준비된* run을 step당 entity 하나씩 W3C PROV activity로
기록하므로, 중단된 run도 무엇을 시도했는지 증거를 남깁니다.

`maglab harness run literature-review --topic "..." --pi-handoff`는 실제 PI CLI
handoff command와 prompt를 출력합니다. project-local
`.pi/npm/node_modules/.bin/pi`가 있으면 그 binary를 우선 사용하고, parent PI
process는 `--no-builtin-tools --tools workflow`로 `workflow` tool만 쓰도록
제한합니다. `--execute-pi`는 이 command를 명시적으로 실행하므로 provider-backed
smoke 또는 실제 run에서만 사용합니다. 이미 PI flow id가 있는 경우 `harness run`에 `--pi-flow-id`를
넘겨 dry-run record가 provenance cross-link 계약과 같은 형태가 되도록 할 수
있습니다. 준비된 run을 실제 W3C PROV activity로 남기려면
`--record-provenance --provenance-db .maglab/harness-provenance.sqlite`를 추가합니다.
이때 생성된 `provenance_activity_id`는 dry-run JSON에 다시 반영됩니다.
PI 또는 wrapper가 MagLab 쪽 workflow-tool 계약을 직접 받아야 할 때는
`maglab harness pi-tool --payload-json ... --output json|text`를 사용합니다.
harness 응답에는 PI flow id, 감지된 PI workflow/session id, MagLab provenance id를
한 곳에 묶은 `cross_links`가 포함됩니다. `maglab run "..."
--harness-workflow literature-review`는 root command migration 경로이고,
`--harness-workflow`가 없으면 `maglab run`은 legacy orchestrator fallback입니다.

MCP live tool을 연결하는 harness 실행은 run-scoped `McpRunSession` 계약을
사용합니다. 세션은 workflow/run 시작 시 열고 정상 종료 또는 예외 시
`close_all()`로 닫습니다. `.maglab/mcp.json`에서 disabled 서버는
discovery/doctor에서 설정만 검증되고 외부 MCP process를 시작하지 않습니다.

첫 migration 대상인 literature workflow는 기존 `lit search` entrypoint에서도
opt-in으로 harness plan을 볼 수 있습니다.

```sh
maglab lit search papers/sot --harness-plan --harness-plan --topic "SOT switching in CoFeB"
maglab lit search papers/sot --harness-plan --harness-json
```

이 경로는 folder에서 local keyword를 추출한 뒤 `literature-review` PI payload를
준비합니다. legacy 직접 OpenAlex connector는 호출하지 않고
`evidence_matrix.json`도 쓰지 않습니다. 현재 direct evidence-matrix 동작이 필요하면
기존처럼 `maglab lit search`를 그대로 사용합니다.

`.pi/workflows` 아래 파일은 `harness.manifest.json` 대비 drift를 검사하기 위한
정적 생성 artifact입니다. topic/input이 묶인 live PI 실행 payload가 아니므로,
구체적인 PI handoff에는 dry-run의 `pi_agents_workflow_payload`를 사용합니다.

Live PI 실행은 environment-gated입니다. 별도로 PI를 설치/설정하고,
PI 본체와 `workflow` 툴을 제공하는 pi-agents 확장이
필요합니다. provider-backed bridge가 설정되기 전에는 실제 작업에는 deterministic
command나 legacy CLI/REPL을 사용하고, harness dry-run 또는 `--pi-handoff` 출력은
workflow 검증과 PI handoff 점검으로 취급하세요.
PI/pi-agents는 PI package 안내에 따라 별도로 설치한 뒤 `maglab harness doctor`로
확인합니다. project-local `.pi/npm/node_modules/.bin/pi`가 있으면 MagLab은 그
binary를 우선 사용합니다. LiteLLM은 `LITELLM_CONFIG_PATH`로 proxy config를
지정하거나 `ANTHROPIC_API_KEY` 같은 직접 provider credential을 제공하세요.
`LITELLM_CONFIG_PATH`가 설정되면 live `maglab harness worker ... --execute`는
planning과 execution 모두에서 그 파일을 사용합니다. 번들
`configs/litellm.example.yaml`은 live readiness로 취급하지 않습니다. 실제 config로
복사하거나 직접 provider credential을 제공해야 `harness doctor`가 통과하며,
readiness가 incomplete여도 dry-run과 PI handoff 점검은 계속 사용할 수 있습니다.

Workspace skill은 `.maglab/skills/<skill-name>/` 아래에 두며, user-global
skill과 번들 skill보다 먼저 발견됩니다. 현재 로컬 helper 계층은 deterministic
offline 동작만 제공합니다.

- `maglab skill create <name> --description "..."`
  명령은 load 가능한 `SKILL.md` package와 `references/`, `scripts/`,
  `evals/` 디렉터리를 만듭니다.
- `maglab skill install <path>`는 기존 로컬 skill package의 frontmatter를
  검증한 뒤 `.maglab/skills`로 복사합니다.
- 두 helper 모두 idempotent입니다. 같은 skill이 이미 있으면 local edit를
  덮어쓰지 않고 skip합니다.

REPL에서도 같은 표면을 `/skill create`, `/skill install`, `/skill list`로
사용할 수 있습니다. Instrument 전용 skill은 `maglab instr skillgen`을
사용하세요.

## Ralph loop

Ralph는 autonomous research-loop engine입니다. 무제한 자동 결론 생성이 아니라
bounded exploration에 사용하세요.

```sh
maglab ralph start "Optimize SOT measurement plan for Pt/CoFeB/MgO" --max-iter 10
maglab ralph status
maglab ralph cancel
```

## Hypotheses

```sh
maglab hypotheses "orbital Hall torque in light-metal/ferromagnet bilayers" --n 8 --json-out hypotheses.json
```

생성된 hypothesis는 ranked suggestion입니다. physical check, literature check,
experiment가 필요합니다.

## MCP

MagLab은 MCP로 tool을 노출하거나 외부 MCP server를 등록할 수 있습니다.

```sh
maglab mcp serve
maglab mcp list
maglab mcp add arxiv "npx -y @modelcontextprotocol/server-arxiv" --trust-level trusted
maglab mcp enable arxiv
maglab mcp disable arxiv
```

## Gateway bot

Gateway는 Slack, Telegram, Discord에서 lab이 MagLab과 상호작용하게 합니다.

```sh
maglab gateway setup
maglab gateway start
maglab gateway status
maglab gateway stop
maglab gateway install
```

Credential을 private하게 유지하고 allowed user/channel을 제한하세요.

## 실무 패턴

처음에는 개별 deterministic command로 workflow를 만듭니다. 단계가 명확해지면
같은 단계를 REPL, Ralph, subagent workflow로 묶어 반복 실행합니다.
