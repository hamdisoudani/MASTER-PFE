FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . ./agent/
ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1
ENV UVICORN_HOST=0.0.0.0
CMD sh -c "exec uvicorn agent.main:app --host 0.0.0.0 --port ${PORT:-8000} --no-reload"
