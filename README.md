# scholarflow-ocr

A lightweight service that replaces GROBID's role in ScholarFlow. It converts a
PDF into structured **TEI XML** by calling Baidu **PaddleOCR-VL** (cloud document
parsing) and mapping the returned layout into the TEI subset that
`scholarflow-server` consumes.

It impersonates GROBID's HTTP contract (`POST /api/processFulltextDocument`,
multipart PDF in → TEI out), so the server integrates by repointing `GROBID_URL`
at this service — no change to the wire protocol. The only server-side code
change is making GROBID's hardcoded 2-minute client timeout configurable (async
OCR of a large PDF can exceed it); see `docs/server-integration.md`.

## Run

    cp .env.example .env      # fill in Baidu credentials
    docker compose up --build

Point the server at it: set `GROBID_URL=http://<host>:8070` in scholarflow-server.
See `docs/server-integration.md` for the one required server change.

## Develop

    python -m pip install -e '.[dev]'
    python -m pytest -v
