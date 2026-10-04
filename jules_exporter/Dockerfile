FROM python:3.11-alpine

WORKDIR /app

COPY exporter.py /app/
COPY run.sh /app/

RUN chmod +x /app/run.sh

CMD ["/app/run.sh"]
