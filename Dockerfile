FROM mcr.microsoft.com/playwright/python:v1.55.0-jammy

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt \
    && playwright install chromium

COPY . .

CMD ["python", "-m", "websum_to_git.main", "--config", "/app/config.yaml"]
