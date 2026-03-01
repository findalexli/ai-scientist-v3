# Multi-stage: build React frontend, then run Python backend
FROM node:22-slim AS frontend

WORKDIR /app/viewer/frontend
COPY viewer/frontend/package.json viewer/frontend/package-lock.json ./
RUN npm ci --legacy-peer-deps
COPY viewer/frontend/ ./
RUN npx react-router build

# Runtime
FROM python:3.12-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
COPY --from=frontend /app/viewer/frontend/build/client /app/viewer/frontend/build/client

WORKDIR /app/viewer
EXPOSE 8080
ENTRYPOINT ["python3", "app.py", "--port", "8080", "--source", "gitlab"]
