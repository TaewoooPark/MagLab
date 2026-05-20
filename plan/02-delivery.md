# MagLab 설계 — 전달 · 인증 · CLI 디자인 · 메시징 게이트웨이

> `PLAN.md`의 **§7–§8** 상세. 전체 개요·색인은 [`../PLAN.md`](../PLAN.md).
> 본문의 `(§N)` 교차참조는 문서 전역 절 번호이며, 절↔파일 대응표는
> `../PLAN.md` 「문서 구성」 절에 있다.

---

## 7. 전달 · 인증 · CLI 디자인

### 7.1 독립 CLI 프로그램

- **이중 모드**: 인자 없이 실행 → 대화형 REPL(스트리밍·도구 호출 시각화·
  Ctrl+C 인터럽트); `maglab -p "..."` → 비대화형 단발(파이프·CI).
- 서브커맨드 트리 = 부록 A. 설정 = `~/.config/maglab/config.toml`(XDG, TOML).
- 장기 작업: 즉시 task ID 반환, `maglab task status <id>`, 세션은 `~/.local/
  share/maglab/sessions/`에 직렬화(재시작 후 재개).
- 부가로 `maglab mcp` = MCP 서버(외부 하네스 연동).

### 7.2 인증 — 3가지 LLM 백엔드 모드

`llm/backends/`가 세 모드를 추상화한다:

| 모드 | 메커니즘 | 자격증명 | 약관 |
|---|---|---|---|
| **직접 API (BYO 키)** | `api.py` — LiteLLM로 Anthropic·OpenAI·Google·OpenAI호환 엔드포인트 호출 | API 키 (`keyring` 저장) | 모든 provider 완전 준수, 메터드 과금 |
| **위임 CLI 백엔드** | `delegated_cli.py` — 공식 설치·인증한 `codex exec` / `claude` / `gemini`를 서브프로세스로 구동 | 그 공식 도구가 보유(예: Codex "Sign in with ChatGPT" 구독) | MagLab가 인증을 직접 안 함, 공식 도구 오케스트레이션 — Codex(ChatGPT) 구독 그대로 활용 |
| **로컬 모델** | `local.py` — Ollama 등 | 불필요 | 무료·오프라인, 랩 보안 환경 |

**위임 CLI 백엔드 근거.** `codex`는 Apache-2.0 오픈소스이며 `codex exec`는
비대화형 임베딩용. MagLab가 사용자의 공식 인증된 Codex를 서브프로세스 백엔드로
부르면 인증·토큰 갱신은 OpenAI 공식 도구가 담당하고 MagLab는 오케스트레이터에
머문다 — "구독으로 작동, API 과금 없음"을 깔끔히 달성. `claude`·`gemini`도 동일.

**정직성 주석.** Anthropic은 소비자 구독(Pro/Max) OAuth 토큰의 *제3자 프로그램
직접* 사용을 2026년 금지·서버차단했다. MagLab는 구독 OAuth를 직접 구현하지
않고, Claude 구독은 위임 백엔드(공식 `claude` CLI)로만 활용한다. API 키는 모두
정상 경로다. 자격증명은 `keyring` 우선, 헤드리스 폴백 `~/.config/maglab/
auth.json`(`0600`), env var(`MAGLAB_<PROVIDER>_API_KEY`) 최우선.

### 7.3 멀티 provider 추상화

`llm/base.py` 위에 LiteLLM(직접 API)을 둬 Anthropic/OpenAI/Google/Ollama를
하나의 인터페이스로. 모델 호출 경계만 추상화 → 오케스트레이션 로직은 provider
중립. **단계별 모델 라우팅** — 파이프라인 단계마다 다른 모델: 계획·심층 추론은
고성능 모델, 빌드·요약·압축은 저렴한 모델, figure 비전 critic은 비전 모델.
`config.toml`의 단계→모델 매핑으로 비용·품질을 동시에 최적화한다.

### 7.4 시각 아이덴티티 — 볼드 솔리드 블록 로고

MagLab의 로고는 굵은 솔리드 블록 워드마크다. 글자는 변형하지 않아 또렷하고
임팩트가 크며, **자성은 색으로** 표현한다.

```
███╗   ███╗ █████╗  ██████╗ ██╗      █████╗ ██████╗
████╗ ████║██╔══██╗██╔════╝ ██║     ██╔══██╗██╔══██╗
██╔████╔██║███████║██║  ███╗██║     ███████║██████╔╝
██║╚██╔╝██║██╔══██║██║   ██║██║     ██╔══██║██╔══██╗
██║ ╚═╝ ██║██║  ██║╚██████╔╝███████╗██║  ██║██████╔╝
╚═╝     ╚═╝╚═╝  ╚═╝ ╚═════╝ ╚══════╝╚═╝  ╚═╝╚═════╝
```

- **색 = 물리 규약.** 워드마크에 **자화 그라데이션**을 적용한다 — 왼쪽
  스핀-업 파랑(`#38bdf8`)에서 오른쪽 스핀-다운 빨강(`#f43f5e`)으로. 자화
  방향의 표준 물리 색 규약(MOKE·미세자기 컬러맵)이자 자화 반전 서사다.
- **구현** (`ui/banner.py`): `pyfiglet` `ansi_shadow` 글꼴이 블록 글자꼴
  생성 → `rich-gradient`가 파랑→빨강 적용. 시작 시 즉시 렌더(무거운 import 전).
- **반응형 3단계**: 폭 ≥100 풀 `ansi_shadow` / ≥60 중형(`slant`) / <60 단축
  워드마크. `shutil.get_terminal_size()`로 선택. 유니코드 미지원 터미널은
  ASCII 폴백 글꼴.
- **모티프 확장.** 자성 모티프가 UI 전반에 — 구분선(Rule)은 `↑↑↑↑│↓↓↓↓` 스핀
  격자, "생각 중" 스피너는 스핀 **세차(precession)** 애니메이션(`↑↗→↘↓↙←↖`
  순환 = Larmor 세차), 프롬프트 글리프는 `⇡`.

### 7.5 화면 구성 & 시작 화면

구성: 헤더(배너, 시작 시 1회 출력) / 스크롤 대화 본문 / 상태 바 / 입력 프롬프트.

```
███╗   ███╗ █████╗  ██████╗ ██╗      █████╗ ██████╗
████╗ ████║██╔══██╗██╔════╝ ██║     ██╔══██╗██╔══██╗
██╔████╔██║███████║██║  ███╗██║     ███████║██████╔╝
██║╚██╔╝██║██╔══██║██║   ██║██║     ██╔══██║██╔══██╗
██║ ╚═╝ ██║██║  ██║╚██████╔╝███████╗██║  ██║██████╔╝
╚═╝     ╚═╝╚═╝  ╚═╝ ╚═════╝ ╚══════╝╚═╝  ╚═╝╚═════╝
        magnetism · spintronics research copilot

╭─ session ────────────────────────────────────────╮
│  backend   claude-opus-4 · API                     │
│  cwd       ~/research/MnPtSb                        │
│  skills    14 loaded          gateway   off         │
╰─────────────────────────────────────────────────────╯
↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑│↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓

  ⇡ 무엇을 도와드릴까요?   ( /help · /theme · /skill )
```

시작 시퀀스(`ui/banner.py`): 배너 즉시 렌더 → 테마 감지 → 세션 정보 패널
(backend·cwd·skills·gateway) → 스핀 격자 Rule → 프롬프트 루프. 업데이트 확인은
백그라운드 스레드(시작 비차단).

### 7.6 렌더링 패턴 (`ui/render.py`)

`rich` 전면 사용 — `Console`·`Panel`(ROUNDED)·`Markdown`·`Syntax`·`Tree`·
`Rule`·`Table`.

- **스트리밍 응답** — `rich.live.Live`(screen=False, ~12 fps)로 `Panel(Markdown)`
  을 토큰 배치마다 갱신.
- **도구 호출** — `Panel`+`Tree`, 상태 아이콘 `⟳`(실행)/`✓`(성공)/`✗`(실패),
  테두리 색이 상태에 연동, 기본 접힘(`/verbose`로 펼침).
- **DataPoint 배지** — 모든 수치 옆에 출처 라벨을 색 배지로: `[SIM]`(시안)·
  `[MEAS]`(초록)·`[FIT]`(보라)·`[PRED]`(노랑)·`[LIT]`(회색).
- **thinking** — `dim` 스타일 `Panel`(box.MINIMAL), 기본 접힘.
- **diff** — `Syntax`("diff"). **오류/경고** — rose/amber `Panel`. **진행** —
  `Progress`(스피너+바+ETA). **스피너** — 모델 생성 중 스핀 세차 애니메이션.

### 7.7 입력 프롬프트 (`ui/prompt.py`)

`prompt_toolkit.PromptSession` — `FileHistory`(`~/.maglab/history`),
`FuzzyCompleter`(슬래시 커맨드 `NestedCompleter`), `AutoSuggestFromHistory`,
동적 `bottom_toolbar`(backend·토큰·상태), 멀티라인(Meta+Enter), Ctrl+R 이력
검색. 프롬프트 글리프 `⇡`. 슬래시 커맨드는 플로팅 `Panel` 오버레이.

### 7.8 테마 시스템 (`ui/theme.py`)

- 테마 = YAML(`themes/*.yaml`, `~/.maglab/themes/`). 자동 감지 3계층:
  `MAGLAB_THEME` env → `COLORFGBG` → OSC 11 터미널 배경 프로브.
- **번들 테마**: `domain`(기본 — 자화 그라데이션 파랑→빨강), `mono`(고대비
  흑백), `moke`(MOKE 영감 — 흑백+단일 강조), `light`. `/theme <name>` 전환.
- 기본 팔레트(dark): 강조=필드 블루 `#38bdf8`, 스핀다운/오류=로즈 `#f43f5e`,
  성공=에메랄드 `#10b981`, 경고=앰버 `#f59e0b`, dim=슬레이트 `#64748b`.

### 7.9 접근성 & 반응형

- env: `NO_COLOR`·`TERM=dumb`·`MAGLAB_SCREEN_READER`·`MAGLAB_NO_ANIMATION` —
  ASCII 아트·Live·스피너 억제, 평문 출력.
- 비-TTY: Rich가 색·애니메이션 자동 제거. 구조화 출력은 `--json`.
- 폭 반응형: 배너 3단, Rich 렌더러블 자동 reflow. 색에만 의존 금지(아이콘+라벨).
- 스택: `rich` + `prompt_toolkit` + `pyfiglet` + `rich-gradient`. Textual은
  phase 1 미사용.

---

## 8. 메시징 게이트웨이 — Slack · Telegram · Discord

> hermes-agent(NousResearch) 방식: CLI와 병행하는 **게이트웨이 데몬**이 메시징
> 플랫폼 연결을 유지.

`maglab gateway start`로 데몬 기동(`gateway install`로 systemd/launchd). 어댑터
패턴 — `gateway/adapters/{slack,telegram,discord}.py`가 각자 `verify_request`·
`parse_message → UnifiedMessage`·`send_reply` 구현, `runner.py`가 라우팅·세션.

| 플랫폼 | 라이브러리 | 연결 |
|---|---|---|
| Slack | `slack-bolt` | Socket Mode (공개 IP 불필요) |
| Telegram | `python-telegram-bot` | long-polling / webhook |
| Discord | `discord.py` | Gateway, 슬래시 커맨드 |

통합 패턴 — **선제 알림**(시뮬 완료·Ralph 마일스톤·리뷰 완료·figure 산출을
채팅 푸시, figure 첨부), **원격 명령**(채팅→CLI 공유 커맨드 레지스트리),
**세션 상태**(`~/.maglab/gateway.db` SQLite), **휴먼게이트**(Tier 2/3 승인을
인라인 버튼으로, `asyncio.Event`로 코루틴 일시정지·재개), **보안**
(`allowed_users`/`channels` 허용목록, 서명 검증, 자격증명 `0600`, PII 해시).

---

## 관련 모듈

- [`01-harness.md`](01-harness.md) — 하네스·서브에이전트·스킬·MCP가 CLI·게이트웨이의 코어; MCP 통합 §5.18
- [`11-appendices.md`](11-appendices.md) — 부록 A(CLI 명령어 트리)
- [`../PLAN.md`](../PLAN.md) — 개요·아키텍처·로드맵
