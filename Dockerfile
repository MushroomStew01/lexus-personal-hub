FROM node:22-alpine AS maplibre-assets

WORKDIR /maplibre

# MapLibre GL JS 5.x still publishes the classic browser bundle used by the
# dashboard (dist/maplibre-gl.js + dist/maplibre-gl.css). MapLibre 6 is ESM-only,
# so pin the final 5.x release instead of expecting a removed UMD bundle.
RUN npm init -y >/dev/null 2>&1 \
    && npm install --omit=dev --no-audit --no-fund maplibre-gl@5.24.0 \
    && test -s node_modules/maplibre-gl/dist/maplibre-gl.js \
    && test -s node_modules/maplibre-gl/dist/maplibre-gl.css \
    && cp node_modules/maplibre-gl/dist/maplibre-gl.js /maplibre/maplibre-gl.js \
    && cp node_modules/maplibre-gl/dist/maplibre-gl.css /maplibre/maplibre-gl.css

FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY pyproject.toml README.md LICENSE ./
COPY src ./src

RUN python -m pip install --no-cache-dir .

RUN mkdir -p /app/vendor
COPY --from=maplibre-assets /maplibre/maplibre-gl.js /app/vendor/maplibre-gl.js
COPY --from=maplibre-assets /maplibre/maplibre-gl.css /app/vendor/maplibre-gl.css

# Fail the image build immediately if either browser asset is missing/empty.
RUN test -s /app/vendor/maplibre-gl.js \
    && test -s /app/vendor/maplibre-gl.css \
    && ls -lh /app/vendor/maplibre-gl.js /app/vendor/maplibre-gl.css

EXPOSE 8000

CMD ["lexus-hub", "serve", "--host", "0.0.0.0"]
