FROM python:3.12-alpine

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    IMPORTER_DATA_DIR=/data \
    IMPORTER_BASE_PATH=/importer

WORKDIR /app

COPY src/requirements.txt /app/src/requirements.txt
RUN pip install --no-cache-dir -r /app/src/requirements.txt

COPY . /app

VOLUME ["/data"]
EXPOSE 8080

CMD ["uvicorn", "src.spoolman_importer_web:app", "--host", "0.0.0.0", "--port", "8080"]
