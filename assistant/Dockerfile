# Phone assistant demo (asistent.jsemvcas.cz): its own small image, nothing shared with the case containers.
FROM python:3.12-slim
WORKDIR /app
COPY assistant/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY assistant assistant
RUN useradd -m -u 10001 app && mkdir /data && chown app /data
USER app
ENV ASSISTANT_DB=/data/assistant.db PORT=8000
VOLUME /data
EXPOSE 8000
CMD ["sh", "-c", "uvicorn assistant.app:app --host 0.0.0.0 --port ${PORT}"]
