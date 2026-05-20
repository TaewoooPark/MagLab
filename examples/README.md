# examples/

MagLab usage examples — configuration files for each backend mode.

## Configuration examples

- `config-api.toml` — direct API backend (BYO key).
- `config-local.toml` — local Ollama backend (free, offline, lab-secure environment).
- `config-delegated.toml` — delegated CLI backend (official codex/claude/gemini subprocess).

Copy to `~/.config/maglab/config.toml` to use. **Do not put credentials in the config
file** — use the env var `MAGLAB_<PROVIDER>_API_KEY` or `maglab auth set`
(keyring). See PLAN.md §7.2 for details.

## Quick start

```sh
cp examples/config-api.toml ~/.config/maglab/config.toml
export MAGLAB_ANTHROPIC_API_KEY=...     # or: maglab auth set
maglab                                   # interactive REPL
```
