FROM node:22-slim AS frontend
ARG VITE_CLERK_PUBLISHABLE_KEY
ENV VITE_CLERK_PUBLISHABLE_KEY=${VITE_CLERK_PUBLISHABLE_KEY}
WORKDIR /app/frontend
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM python:3.13-slim
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/backend
WORKDIR /app
COPY pyproject.toml ./
COPY backend/ ./backend/
COPY migrations/ ./migrations/
RUN pip install --no-cache-dir .
COPY --from=frontend /app/frontend/dist ./backend/sharehtml/static
CMD ["sh", "-c", "gunicorn --bind 0.0.0.0:${PORT:-5000} --workers 2 'sharehtml:create_app()'"]
