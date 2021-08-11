ARG PY_VERSION="3.9.6"
ARG BASE_IMAGE="python:${PY_VERSION}-buster"
ARG RUN_IMAGE="python:${PY_VERSION}-slim-buster"

FROM $BASE_IMAGE as builder

ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1


COPY    requirements.txt /
RUN     ["/bin/bash", "-c", "\
         pip install virtualenv && \
         virtualenv /venv && \
         source /venv/bin/activate && \
         pip install -r /requirements.txt"]

COPY    ss2sg /venv/ss2sg/


ARG BUILD_DATE
ARG GIT_HASH

FROM    $RUN_IMAGE

ARG     BUILD_DATE
ARG     GIT_HASH

LABEL org.opencontainers.image.created="$BUILD_DATE"
LABEL org.opencontainers.image.revision="$GIT_HASH"
LABEL org.opencontainers.image.title="SS2SG"
LABEL org.opencontainers.image.description="SiteShield 2 SecurityGroup"
LABEL org.opencontainers.image.vendor="Vlad Vasiliu"
LABEL org.opencontainers.image.source="https://github.com/vladvasiliu/ss2sg"
LABEL org.opencontainers.image.authors="Vlad Vasiliu"
LABEL org.opencontainers.image.url="https://github.com/vladvasiliu/ss2sg"


COPY    --from=builder /venv /venv
WORKDIR /venv
CMD ["/venv/bin/python","-m","ss2sg"]
