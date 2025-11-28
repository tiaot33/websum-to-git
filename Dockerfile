FROM mcr.microsoft.com/playwright/python:v1.55.0-jammy

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1
RUN apt-get update && apt-get install -y --no-install-recommends xvfb
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt \
    && playwright install chromium
COPY entrypoint.sh .
RUN chmod +x entrypoint.sh

COPY src ./
ENTRYPOINT ["/app/entrypoint.sh"]

# CMD ["python", "main.py", "--config", "/app/config.yaml"]
