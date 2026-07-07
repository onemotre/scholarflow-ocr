from fastapi import FastAPI, Response


def create_app() -> FastAPI:
    app = FastAPI(title="scholarflow-ocr")

    @app.get("/health")
    def health() -> dict:
        return {"status": "ok"}

    @app.get("/api/isalive")
    def isalive() -> Response:
        # GROBID returns the literal `true`; mirror it.
        return Response(content="true", media_type="text/plain")

    return app
