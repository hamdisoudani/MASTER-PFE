# graph-viz sidecar — serves /graphs/* PNG + Mermaid + JSON for the
# LangGraph graphs defined under ../agent. Build context MUST be the repo
# root so we can COPY both ./agent and ./graph-viz.
FROM python:3.11-slim
WORKDIR /app

RUN apt-get update \
 && apt-get install -y --no-install-recommends curl \
 && rm -rf /var/lib/apt/lists/*

COPY graph-viz/requirements.txt /app/graph-viz/requirements.txt
RUN pip install --no-cache-dir -r /app/graph-viz/requirements.txt

COPY agent /app/agent
COPY graph-viz /app/graph-viz

ENV PYTHONUNBUFFERED=1 \
    PORT=8088 \
    AGENT_SRC=/app/agent
EXPOSE 8088

HEALTHCHECK --interval=20s --timeout=5s --retries=5 --start-period=20s \
  CMD curl -fsS http://localhost:${PORT:-8088}/healthz || exit 1

CMD ["sh", "-c", "exec uvicorn app:app --app-dir /app/graph-viz --host 0.0.0.0 --port ${PORT:-8088} --proxy-headers"]
