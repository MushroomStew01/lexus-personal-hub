FROM node:22-alpine AS maplibre-assets

WORKDIR /maplibre

# Pull the published MapLibre npm package during the image build and copy only
# the browser assets into the final image. This avoids the release dist.zip
# layout mismatch and keeps Node/npm out of the production image.
RUN npm init -y >/dev/null 2>&1 \
    && npm install --omit=dev --no-audit --no-fund maplibre-gl@6.3.0 \
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
