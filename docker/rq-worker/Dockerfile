FROM python:3.11.7-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN pip install --no-cache-dir rq==1.15.1 redis==5.0.1

WORKDIR /app

CMD ["rq", "worker", "--url", "redis://redis:6379/0", "default"]
