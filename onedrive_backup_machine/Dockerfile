ARG BUILD_FROM=ghcr.io/home-assistant/amd64-base-python:3.12-alpine3.20
FROM ${BUILD_FROM}

ENV LANG=C.UTF-8 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY rootfs/app/ /app/

RUN pip3 install --no-cache-dir -r /app/requirements.txt \
    && chmod a+x /app/run.sh

CMD ["/app/run.sh"]
