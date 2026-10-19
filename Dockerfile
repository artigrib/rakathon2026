# Jsem včas – web app + backend (FastAPI, Twilio). Runs anywhere: VPS, Azure, Render, Railway.
# One image for every case; env CASE picks cases/<id>/ (default screening = Plíce včas). See cases/README.md.
FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY engine engine
COPY backend backend
COPY cases cases
COPY web/app web/app
COPY submission/landing submission/landing
COPY submission/demo.mp4 submission/demo.mp4
COPY data data
# A case whose data file was not built before `docker build` (make data CASE=x) gets it built here; a failure only warns
# (screening needs the challenge data in data/, which is not public).
RUN for m in cases/*/case.json; do id=$(basename "$(dirname "$m")"); \
      f=$(python -c "import json,sys; print(json.load(open(sys.argv[1]))['data'])" "$m"); \
      [ -f "$f" ] || python -m cases.$id.build || echo "WARNING: no data file for case $id ($f)"; done
# STATE_FILE is per container; deploy/docker-compose.yml gives every case its own volume and file.
ENV CASE=screening PORT=8000 STATE_FILE=/data/state.json TTS_CACHE=/data/audio
VOLUME /data
EXPOSE 8000
CMD ["sh", "-c", "uvicorn backend.app:app --host 0.0.0.0 --port ${PORT}"]
