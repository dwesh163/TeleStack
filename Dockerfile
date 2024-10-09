FROM python:3.13-slim

RUN apt-get update && \
    apt-get install -y gcc libffi-dev python3-dev musl-dev && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY . .

RUN pip install --no-cache-dir -r requirements.txt

CMD ["python", "main.py"]
