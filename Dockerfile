FROM python:3.12-slim

WORKDIR /app
COPY pyproject.toml ./
COPY src ./src
RUN pip install --no-cache-dir .

ENV HTTP_PORT=8070
EXPOSE 8070
CMD ["python", "-m", "scholarflow_ocr.main"]
