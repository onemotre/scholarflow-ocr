# scholarflow-ocr

A lightweight service that replaces GROBID's role in ScholarFlow. It converts a
PDF into structured **TEI XML** by calling Baidu **PaddleOCR-VL** (cloud document
parsing) and mapping the returned layout into the TEI subset that
`scholarflow-server` consumes.

It impersonates GROBID's HTTP contract (`POST /api/processFulltextDocument`,
multipart PDF in → TEI out), so the server integrates by repointing `GROBID_URL`
at this service — no server code change.

Design in progress. See `docs/specs/` once the design doc lands.
