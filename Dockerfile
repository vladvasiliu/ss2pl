ARG PY_VERSION="3.10.4"
ARG DEB_VERSION="bullseye"
ARG RUN_IMAGE=""

FROM python:${PY_VERSION}-${DEB_VERSION} as builder

ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1


SHELL ["/bin/bash", "-c", "-o", "pipefail"]
COPY    requirements.txt /
RUN     "pip install --no-cache-dir virtualenv && \
         virtualenv /venv && \
         source /venv/bin/activate && \
         pip install --no-cache-dir -r /requirements.txt"

COPY    ss2pl /venv/ss2pl/


FROM    python:${PY_VERSION}-slim-${DEB_VERSION}

LABEL org.opencontainers.image.title="SS2PL"
LABEL org.opencontainers.image.description="SiteShield 2 PrefixList"
LABEL org.opencontainers.image.vendor="Vlad Vasiliu"
LABEL org.opencontainers.image.source="https://github.com/vladvasiliu/ss2pl"
LABEL org.opencontainers.image.authors="Vlad Vasiliu"
LABEL org.opencontainers.image.url="https://github.com/vladvasiliu/ss2pl"
LABEL org.opencontainers.image.licenses="BSD-3-Clause"


COPY    --from=builder /venv /venv
WORKDIR /venv
CMD ["/venv/bin/python","-m","ss2pl"]
