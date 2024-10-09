# Stage 1: Builder
FROM python:3.13-slim AS builder

RUN apt-get update && \
    apt-get install -y gcc libffi-dev python3-dev musl-dev && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY . .

RUN pip install --no-cache-dir -r requirements.txt

# Stage 2: Final image
FROM python:3.13-slim

WORKDIR /app

COPY --from=builder /app /app

CMD ["python", "main.py"]
