FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . ./agent/
ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1
ENV HOST=0.0.0.0
EXPOSE 8000
CMD sh -c "uvicorn agent.main:app --host 0.0.0.0 --port ${PORT:-8000} --no-reload"
