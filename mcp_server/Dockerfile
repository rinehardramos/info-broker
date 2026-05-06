FROM python:3.11-slim
WORKDIR /app
COPY mcp_server/ ./mcp_server/
RUN pip install --no-cache-dir httpx "mcp[cli]>=1.0"
CMD ["python", "-m", "mcp_server"]
