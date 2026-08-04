# Optional container image — local pip + uvicorn is the primary workflow (see README).
FROM python:3.11-slim

WORKDIR /srv

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY examples ./examples

# Hugging Face Spaces expects the app on 7860; PORT overrides it elsewhere.
EXPOSE 7860

CMD ["sh", "-c", "uvicorn app.api.main:app --host 0.0.0.0 --port ${PORT:-7860}"]
