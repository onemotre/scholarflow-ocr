import uvicorn

from scholarflow_ocr.api import create_app
from scholarflow_ocr.config import load_config

app = create_app()


def main() -> None:
    cfg = load_config()
    uvicorn.run(app, host="0.0.0.0", port=cfg.http_port)


if __name__ == "__main__":
    main()
