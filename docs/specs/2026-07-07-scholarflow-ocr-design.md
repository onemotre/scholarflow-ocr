# scholarflow-ocr — Design Spec

- **Status:** Draft for review
- **Date:** 2026-07-07
- **Author:** onemotre (with Claude)
- **Repo:** `scholarflow-ocr` (independent git module, sibling to `scholarflow-server`)
- **Branch:** `feat/ocr-parser`

## 1. Purpose

`scholarflow-ocr` replaces GROBID's role in ScholarFlow. GROBID works today but its
local PDF parsing is too resource-intensive for the target deployment (2 cores /
2 GB RAM). This service offloads OCR to Baidu **PaddleOCR-VL** (a cloud document-
parsing API) and programmatically converts the returned layout into the **TEI XML**
subset that `scholarflow-server` already consumes.

The service **impersonates GROBID's HTTP contract**, so the server integrates by
repointing `GROBID_URL` at this service — with one small, documented exception
(§11).

## 2. Goals / Non-goals

### Goals
- Drop-in replacement for the single GROBID endpoint the server calls
  (`POST /api/processFulltextDocument`).
- Produce TEI that reproduces every field the server's `parseTEI` extracts
  (§5), including `@coords` for page numbers and figure cropping.
- Run comfortably in a small container (2 cores / 2 GB): no local ML, no PDF
  rasterization.
- Deterministic, offline structuring logic (no LLM) — testable without network.

### Non-goals
- Not reproducing GROBID's full TEI output — only the subset the server reads.
- No LLM-assisted parsing in this version (reference/front-matter fidelity is
  heuristic; an LLM path may be added later behind the same contract).
- No changes to the server's data model, pipeline, or API surface (beyond the
  timeout config in §11).
- The service does **not** crop figures or store assets — the server continues to
  own cropping/MinIO using the `@coords` we emit.

## 3. Context & constraints

- **Consumer contract source of truth:** `scholarflow-server/internal/parser/grobid.go`
  (`parseTEI`). Any field it reads is in scope; anything it ignores is out of scope.
- **Server call shape:** multipart POST, form file field `input`, plus repeated
  `teiCoordinates` fields (`figure`, `head`, `p`, `s`). Response must be TEI XML
  with HTTP < 300.
- **Hardware:** 2 cores / 2 GB. The heavy OCR runs in Baidu's cloud; this service
  is I/O-bound (HTTP to Baidu) and does light XML/text work only.
- **PaddleOCR-VL API:** async — submit (base64 `file_data` or `file_url`) → receive
  `task_id` → poll → fetch parse result. Returns `pages[]` with `layouts[]`
  (typed elements: `title`, `text`, `table`, `image`, `formula`, `seal`),
  per-element `position [x,y,w,h]` + `polygon` + line-level `span_boxes`, per-page
  `meta` (pixel dimensions), and tables as markdown/cells.

## 4. Architecture

Single FastAPI service, one meaningful endpoint, layered into small modules.

```
HTTP (GROBID-compatible)
        │  POST /api/processFulltextDocument  (multipart PDF)
        ▼
   api layer  ── parses multipart, orchestrates, returns TEI
        │
        ├─ pdfmeta      : PDF page sizes in points (pypdf)
        ├─ ocr.client   : submit → poll → fetch PaddleOCR-VL result
        │                 (behind an interface; faked in tests)
        ├─ parse.*      : OCR JSON → internal Document model
        │     layout · frontmatter · sections · figures · references · coords
        └─ tei.render   : Document → TEI XML
```

### Request flow
1. Receive multipart PDF (`input`). Read raw bytes.
2. `pdfmeta`: extract per-page point dimensions (`W_pt`, `H_pt`) via pypdf
   (no rendering).
3. `ocr.client.parse(pdf_bytes)`: base64-submit to PaddleOCR-VL, poll `task_id`
   with backoff until complete or timeout, fetch the parse-result JSON.
4. `parse`: map `pages[].layouts[]` into the internal `Document` model, running
   front-matter, section, figure, and reference structuring; translate coords.
5. `tei.render`: emit TEI XML.
6. Return `200 application/xml`.

## 5. TEI output contract (exact)

The server reads only these paths; the renderer must populate them.

| TEI path | Source in Document | Notes |
|---|---|---|
| `teiHeader/fileDesc/titleStmt/title` | `doc.title` | plain text |
| `teiHeader/profileDesc/abstract/p` | `doc.abstract` | one or more `<p>` |
| `.../sourceDesc/biblStruct/analytic/author/persName/{forename,surname}` | `doc.authors[]` | name split into forename/surname |
| `.../sourceDesc/biblStruct/idno[@type="DOI"]` | `doc.doi` | omit if unknown |
| `.../sourceDesc/biblStruct/monogr/imprint/date/@when` | `doc.year` | `YYYY` acceptable (server reads first 4 chars) |
| `text/body/div/head` (`@n`, `@coords`) | `section.number`, `section.coords` | `@n` carries outline number e.g. `2.1` |
| `text/body/div/p` (`@coords`) | `section.paragraphs[]` | one `<p>` per paragraph |
| `text/body/figure` (`@type`, `@coords`, `head`, `figDesc`) | `doc.figures[]` | `@type="table"` for tables; `head`=label, `figDesc`=caption |
| `text/back/div/listBibl/biblStruct` | `doc.references[]` | analytic/title, analytic/author/persName, monogr/title (venue), monogr/imprint/date/@when, idno[@type=DOI] |

**`@coords` format:** `"page,x,y,w,h"` (may be `;`-separated for multi-box; the
server unions them). Page is 1-based. When coordinates are unavailable for an
element, omit `@coords` (server degrades to `nil` page / skipped crop — existing
behavior).

## 6. Layout → Document mapping

PaddleOCR's typed layout removes the segmentation problem GROBID solved with ML.

- **`title`** blocks → candidate section heads (and the paper title on page 1).
- **`text`** blocks → paragraphs, attached to the current section.
- **`image`** → `figure` (`@type="figure"`).
- **`table`** → `figure` (`@type="table"`); caption from adjacent text / cells.
- **`formula`, `seal`** → ignored for TEI (not in the server contract).

Reading order follows PaddleOCR's per-page element order; sections accumulate
paragraphs until the next heading-level `title`.

### 6.1 Front-matter (`parse/frontmatter.py`)
On page 1, in order: the first prominent `title` block → paper title; blocks
between title and the `abstract` heading → author block(s), split on
commas/superscripts into names; the paragraph(s) under an "Abstract" heading →
abstract. DOI/year taken from any matching text on page 1 if present (else omitted).

### 6.2 Sections & numbering (`parse/sections.py`)
A `title` block starting with a numeric pattern (`^\d+(\.\d+)*`) sets `head/@n`
to that number and strips it from the heading text (mirrors GROBID's `@n`). Body
`text` blocks between headings become that section's paragraphs. Heading-only
sections (parent headings) are retained so the outline hierarchy stays complete.

### 6.3 Figures (`parse/figures.py`)
Each `image`/`table` becomes a figure with: label (nearest "Figure N"/"Table N"
caption text, else `Figure {i}`), caption (`figDesc`), page + bbox `@coords`
(translated, §7).

### 6.4 References (`parse/references.py`) — heuristic, no LLM
1. **Locate** the bibliography: a `title` block matching
   `^(references|bibliography)`, then everything after it (until end / appendix).
2. **Split entries:** by leading markers `[\d+]` or `^\d+\.`; fallback to
   coord-based hanging-indent detection (a new entry starts at the left margin).
3. **Extract fields per entry (best-effort):**
   - `year`: `\(?(19|20)\d{2}\)?`
   - `doi`: `10\.\d{4,9}/\S+`
   - `authors`: leading `Surname, I.`-style run before the year/title
   - `title`: segment after authors up to the venue cue
   - `venue`: trailing journal/conference segment
4. **Always** set `raw_text` = the full entry, so nothing is lost when
   field-splitting is imperfect (the server persists `raw_text`).

## 7. Coordinate translation (`parse/coords.py`)

PaddleOCR positions are pixels at its render resolution; the server expects PDF
points (as GROBID emits). Per page:

- `W_px, H_px` = page pixel dims from PaddleOCR `meta`.
- `W_pt, H_pt` = page point dims from pypdf (MediaBox).
- Scale: `sx = W_pt / W_px`, `sy = H_pt / H_px`.
- Both coordinate systems use a top-left origin with y increasing downward, so:
  `coords = f"{page},{x*sx:.2f},{y*sy:.2f},{w*sx:.2f},{h*sy:.2f}"`.

A **golden test** validates that the emitted `@coords`, fed to a reproduction of
the server's `parseBox`/cropper expectations, yields the correct page and a
sane crop rectangle. If PaddleOCR's origin/units differ from this assumption in
practice, the transform is the single place to fix.

## 8. Internal Document model (`parse/document.py`)

Frozen dataclasses:
- `Document(title, abstract, doi, year, authors[], sections[], figures[], references[])`
- `Author(forename, surname)`
- `Section(number, heading, paragraphs[Paragraph], coords)`
- `Paragraph(text, coords)`
- `Figure(kind, label, caption, coords)`
- `Reference(order, title, authors[str], venue, year, doi, raw_text)`
- `Coords(page, x, y, w, h)` with a `.tei()` serializer.

This model is parser-agnostic: if the OCR backend is ever swapped again, only
`ocr.client` + `parse.layout` change; `tei.render` and the contract stay put.

## 9. Configuration (`config.py`, env)

| Env | Default | Purpose |
|---|---|---|
| `BAIDU_OCR_API_KEY` | (required) | PaddleOCR-VL credential |
| `BAIDU_OCR_SECRET_KEY` | (required) | PaddleOCR-VL credential |
| `BAIDU_OCR_ENDPOINT` | Baidu default | API base URL |
| `OCR_POLL_TIMEOUT_SECONDS` | 300 | max wait for a task to finish |
| `OCR_POLL_INTERVAL_SECONDS` | 3 | poll backoff base |
| `HTTP_PORT` | 8070 | GROBID's default port, so `GROBID_URL` barely changes |
| `MAX_UPLOAD_BYTES` | 33554432 | reject oversized PDFs early |

Secrets are read from env only; never hardcoded. Startup fails fast if required
creds are missing.

## 10. Error handling

- OCR submit/poll failure or timeout → **HTTP 5xx**. The server's asynq parse
  task then fails and retries per existing retry policy.
- Malformed/empty PDF → **HTTP 400**.
- Missing coordinates for some elements → still emit TEI, omitting `@coords` on
  those elements (server degrades to nil page / skipped crop — existing behavior).
- Structuring never hard-fails on low confidence: emit best-effort TEI; a paper
  with a title and at least one section is a success.
- Errors are logged with context; no secrets in logs or error bodies.

## 11. Integration with scholarflow-server (the one server change)

The server's GROBID client timeout is **hardcoded to 2 minutes**
(`grobid.go:28`). PaddleOCR async parsing of a large PDF can exceed that.

**Decision (assumption for this spec):** make that timeout configurable in the
server (e.g. `GROBID_TIMEOUT_SECONDS`, default kept, raised for this deployment).
This is a contained edit — one struct field + one env var — and is the *only*
server change beyond setting `GROBID_URL`. Tracked as a follow-up task in the
server repo, not implemented here.

If a fully self-contained OCR service is required instead (no server edit at
all), the alternative is making the server's parse path truly async — a larger
change, explicitly out of scope for this version.

## 12. Deployment

- `Dockerfile`: `python:3.12-slim`, install deps, run `uvicorn`. Target image
  < 200 MB, runtime RSS well under 512 MB.
- `docker-compose.yml`: single `ocr` service publishing `HTTP_PORT` (8070),
  reading creds from env. Independent of the server's compose network (matches
  the module-decoupling pattern used by `scholarflow-web`).
- Runbook in README: build, run, and how to point the server at it
  (`GROBID_URL=http://<host>:8070`).

## 13. Testing

- **Unit (network mocked):**
  - `parse/layout` — layout JSON → Document mapping.
  - `parse/coords` — pixel→point math (exact values).
  - `parse/references` — table-driven over representative entry strings.
  - `parse/frontmatter` — title/author/abstract detection.
  - `tei/render` — golden TEI files.
- **Contract test:** feed rendered TEI through a Python reproduction of the
  server's `parseTEI` field expectations, asserting the server would extract the
  intended title/authors/sections/figures/references/coords. This is the guard
  that keeps us drop-in compatible.
- **Fixture flow:** sample PaddleOCR-VL response JSON → expected TEI (golden),
  so the whole map→render path is covered without hitting Baidu.
- OCR client has real vs. fake implementations behind one interface (mirrors the
  server's adapter/testing philosophy).

## 14. Open decisions

1. **Server timeout change (§11):** assumed *yes, make it configurable*. Confirm.
2. **Port (§9):** assumed **8070** (GROBID default). Confirm or override.
3. **PaddleOCR-VL exact field names:** the mapping in §6 is at the documented
   level; precise JSON keys will be confirmed against a live response during
   implementation and encoded in `ocr/models.py`.
```
