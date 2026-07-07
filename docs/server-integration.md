# Integrating scholarflow-ocr with scholarflow-server

scholarflow-ocr impersonates GROBID's `POST /api/processFulltextDocument`, so the
server integrates by pointing `GROBID_URL` at this service:

    GROBID_URL=http://<ocr-host>:8070

## Required server change: configurable GROBID timeout

`scholarflow-server/internal/parser/grobid.go` hardcodes a 2-minute client
timeout:

    client: &http.Client{Timeout: 2 * time.Minute}

PaddleOCR-VL async parsing of a large PDF can exceed this. Change it to read a
config value (default preserved), e.g. add `GROBIDTimeoutSeconds` to
`internal/config/config.go` (env `GROBID_TIMEOUT_SECONDS`, default `120`) and use
it in `NewGROBIDParser`. Raise it (e.g. 600) for this deployment.

This is the only server code change required.
