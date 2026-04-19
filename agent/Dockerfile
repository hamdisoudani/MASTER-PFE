FROM python:3.11-slim
WORKDIR /app

RUN apt-get update \
 && apt-get install -y --no-install-recommends curl \
 && rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY . ./agent/
COPY langgraph.json ./langgraph.json

ENV PORT=2024
ENV PYTHONUNBUFFERED=1
EXPOSE 2024

ENTRYPOINT []
CMD ["sh", "-c", "exec langgraph dev --host 0.0.0.0 --port ${PORT:-2024} --no-browser --allow-blocking"]
