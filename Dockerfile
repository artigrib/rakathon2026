# Plíce včas – web app + backend (FastAPI, Twilio). Runs anywhere: VPS, Azure, Render, Railway.
FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY engine engine
COPY backend backend
COPY web/app web/app
COPY submission/landing submission/landing
COPY submission/demo.mp4 submission/demo.mp4
COPY data data
ENV PORT=8000 STATE_FILE=/data/state.json TTS_CACHE=/data/audio
VOLUME /data
EXPOSE 8000
CMD ["sh", "-c", "uvicorn backend.app:app --host 0.0.0.0 --port ${PORT}"]
