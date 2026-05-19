# 논문 작성과 커뮤니케이션

[매뉴얼 인덱스](index.md) · [English](../en/authoring-comms.md)

실제 결과, 그림, 인용, 노트가 준비된 뒤 사용하는 모듈입니다. MagLab은 과학
문장을 초안으로 만들 수 있지만, 모든 출력은 human review가 필요합니다.

## 설치

```sh
uv pip install -e ".[authoring]"
```

## Manuscript drafting

```sh
maglab write "ST-FMR fit gives xi_DL=0.12 with provenance IDs ..." --journal prl --dry-run
maglab write "Summary of verified PRB results, figures, citations, and provenance IDs ..." --journal prb --output-dir maglab_write/prb
```

Output directory에는 `HUMAN_REVIEW_REQUIRED.txt` marker가 포함됩니다. AI tool은
저자가 아니며, named researcher가 내용, 데이터, 인용에 대한 책임을 집니다.

`maglab write`는 현재 results summary를 텍스트 인자로 받습니다. 요약이 파일에
있다면 먼저 사람이 검토한 뒤 필요한 핵심 요약 문장을 인자로 넘기세요.

## Communications

```sh
maglab comms cover-letter --journal "Physical Review Letters" --title "Spin-orbit torque ..."
maglab comms revision --review decision_letter.txt --notes response_notes.md
maglab comms rebuttal --reviews conference_reviews.txt --notes rebuttal_notes.md
maglab comms abstract --conference "APS March Meeting" --char-limit 1750 --results results.md
maglab comms grant --agency NSF --mechanism NSF-DMR --aims aims.md
maglab comms email collaboration --recipient "Prof. X" --purpose "follow-up on SOT dataset"
```

## 발표 자료

```sh
maglab present slides "Main results and verified figures" --format beamer --n-slides 12
maglab present slides "Main results and verified figures" --format pptx
maglab present poster "Main results and verified figures" --size A0 --format svg
```

## 추천 입력 패키지

Authoring tool을 호출하기 전에 준비하면 좋은 것:

- Results summary.
- Figure path 또는 FigureSpec file.
- Evidence matrix 또는 BibTeX library.
- Fit output과 provenance ID.
- Target journal 또는 conference.
- 사람 연구자가 정한 constraint: tone, 피해야 할 claim, 필수 citation, word limit.

## 다음 단계

Authoring output은 review, edit, version control을 거쳐야 합니다.

```sh
git diff maglab_write/
maglab review maglab_write/prl/main.tex --journal prl
```
