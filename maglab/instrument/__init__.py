"""maglab instrument — instrument code generation, manual RAG, and safety validation package (§13).

P4 implementation:
- `scaffold.py`   — PyVISA backend skeleton generation
- `scpi.py`       — SCPI sequence generation and static validation
- `script.py`     — measurement script generation
- `safety.py`     — hardware safety envelope static validation
- `mock.py`       — virtual instrument (dry-run without hardware)
- `manual_search.py` — manual web search and download
- `manual_rag.py` — structure-aware chunking, embedding, and index
- `skillgen.py`   — automatic SKILL.md generation for instruments
- `templates/`    — Jinja2 templates

★ §13.2: Always confirm the instrument model name with the user — never guess.
★ §2.4 non-goal: No real-time instrument control — code generation and static validation only.
"""
