# 오케스트레이션, Agent, MCP, Gateway

[매뉴얼 인덱스](index.md) · [English](../en/orchestration.md)

단일 명령을 실행하는 것이 아니라 여러 연구 도구를 MagLab이 조율하게 하고
싶을 때 사용합니다.

## Interactive와 one-shot 사용

```sh
maglab
maglab -p "Plan a reproducible SOT analysis workflow for Pt/CoFeB/MgO"
```

REPL은 자연어 표면입니다. deterministic tool, notebook, literature workflow,
analysis, authoring으로 작업을 라우팅하는 데 사용합니다.

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
maglab config
maglab cost
maglab theme list
maglab theme set mono
```

Codex는 먼저 공식 Codex CLI에서 인증합니다. 그 다음 `maglab auth codex`를
실행하거나 REPL 안에서 `/connect codex`를 사용하세요. MagLab은
`config.toml`에 backend 선택만 저장하고 Codex OAuth token은 공식 CLI에 남깁니다.

직접 API provider는 provider 명령을 실행한 뒤 터미널 숨김 입력으로 key를
넣습니다. REPL에서는 `/connect anthropic`, `/connect grok`,
`/connect deepseek`, `/connect qwen`, `/connect kimi`, `/connect gemini`,
`/connect openai`를 사용할 수 있습니다. 각 provider는 별도의 MagLab runtime
profile을 로드하므로, 모델은 자신이 MagLab research orchestration agent로
동작한다는 전제와 provider별 planning/verification 지침을 함께 받습니다.

## Subagent와 skill

```sh
maglab agents list
maglab agents show citation-auditor
maglab skill list
```

Subagent는 `harness.manifest.json`에 선언되어 있습니다. local corpus checking,
search scouting, citation auditing, paper review, physics validation, result
analysis, experiment management, hypothesis generation, communications writing
같은 bounded role을 나타냅니다.

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
