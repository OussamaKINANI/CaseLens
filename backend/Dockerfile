# syntax=docker/dockerfile:1

FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN groupadd \
        --system \
        caselens \
    && useradd \
        --system \
        --gid caselens \
        --create-home \
        caselens

COPY backend/requirements.txt ./requirements.txt

RUN python -m pip install \
        --upgrade pip \
    && python -m pip install \
        --requirement requirements.txt

COPY backend/ ./

RUN chown \
        --recursive \
        caselens:caselens \
        /app

USER caselens

EXPOSE 8000

CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]