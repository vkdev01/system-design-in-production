FROM python:3.12-slim
WORKDIR /app
RUN pip install --no-cache-dir "psycopg[binary]==3.2.3"
COPY . .
RUN useradd -u 10001 app && chown -R app /app
USER app
CMD ["python", "repair.py"]
