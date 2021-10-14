ARG PY_VERSION="3.9.7"
ARG BASE_IMAGE="python:${PY_VERSION}-bullseye"
ARG RUN_IMAGE="python:${PY_VERSION}-slim-bullseye"

FROM $BASE_IMAGE as builder

ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1


COPY    requirements.txt /
RUN     ["/bin/bash", "-c", "\
         pip install virtualenv && \
         virtualenv /venv && \
         source /venv/bin/activate && \
         pip install -r /requirements.txt"]

COPY    ss2pl /venv/ss2pl/


ARG BUILD_DATE
ARG GIT_HASH

FROM    $RUN_IMAGE

ARG     BUILD_DATE
ARG     GIT_HASH

LABEL org.opencontainers.image.created="$BUILD_DATE"
LABEL org.opencontainers.image.revision="$GIT_HASH"
LABEL org.opencontainers.image.title="SS2PL"
LABEL org.opencontainers.image.description="SiteShield 2 PrefixList"
LABEL org.opencontainers.image.vendor="Vlad Vasiliu"
LABEL org.opencontainers.image.source="https://github.com/vladvasiliu/ss2pl"
LABEL org.opencontainers.image.authors="Vlad Vasiliu"
LABEL org.opencontainers.image.url="https://github.com/vladvasiliu/ss2pl"


COPY    --from=builder /venv /venv
WORKDIR /venv
CMD ["/venv/bin/python","-m","ss2pl"]
