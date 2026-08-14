FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY pyproject.toml README.md LICENSE ./
COPY src ./src

RUN python -m pip install --no-cache-dir .

# Vendor MapLibre into the image so maps do not depend on the browser or
# running container being able to download a multi-megabyte CDN script.
# GitHub is already required for normal project deployment (`git pull`), and
# the official MapLibre release publishes a deterministic dist.zip asset.
RUN python - <<'PY'
from io import BytesIO
from pathlib import Path
from urllib.request import Request, urlopen
from zipfile import ZipFile

version = "6.3.0"
url = f"https://github.com/maplibre/maplibre-gl-js/releases/download/v{version}/dist.zip"
request = Request(url, headers={"User-Agent": "Lexus-Personal-Hub-Docker-Build/0.3"})
with urlopen(request, timeout=180) as response:
    payload = response.read()

vendor = Path("/app/vendor")
vendor.mkdir(parents=True, exist_ok=True)
with ZipFile(BytesIO(payload)) as archive:
    names = archive.namelist()
    for target in ("maplibre-gl.js", "maplibre-gl.css"):
        matches = [name for name in names if name.endswith("/" + target) or name == target]
        if not matches:
            raise RuntimeError(f"{target} missing from MapLibre dist.zip")
        vendor.joinpath(target).write_bytes(archive.read(matches[0]))

print("Vendored MapLibre assets:", *(p.name for p in vendor.iterdir()))
PY

EXPOSE 8000

CMD ["lexus-hub", "serve", "--host", "0.0.0.0"]
