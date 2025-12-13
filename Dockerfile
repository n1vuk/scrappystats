FROM python:3.11-slim

RUN apt-get update && \
    apt-get install -y --no-install-recommends cron supervisor && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app
ENV PYTHONPATH=/app

COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY app/ /app/
COPY supervisord.conf /app/supervisord.conf
COPY crontab /etc/cron.d/scrappystats-cron

RUN chmod 0644 /etc/cron.d/scrappystats-cron && \
    touch /var/log/cron.log && \
    mkdir -p /config

CMD ["/usr/bin/supervisord", "-c", "/app/supervisord.conf"]
