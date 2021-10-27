#!/bin/bash

BUILD_DATE="$(date --rfc-3339=seconds)"
GIT_HASH=$(git rev-parse --short HEAD)

docker build -t ss2pl --build-arg BUILD_DATE="$BUILD_DATE" --build-arg GIT_HASH="$GIT_HASH" "$(dirname "${0}")"
