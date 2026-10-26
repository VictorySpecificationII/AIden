# MinIO server and mc client built from source at pinned releases.
# Upstream stopped publishing public images (minio/minio and minio/mc are gone
# from Docker Hub; quay.io requires auth), so we build the versions we pin.
#
# Targets:
#   minio - server, RELEASE.2025-04-22T22-12-26Z (last version before the licence/feature changes, don't bump)
#   mc    - client, RELEASE.2025-04-16T18-13-26Z (last mc release before the server pin)

ARG MINIO_RELEASE=RELEASE.2025-04-22T22-12-26Z
ARG MC_RELEASE=RELEASE.2025-04-16T18-13-26Z

FROM golang:1.24.2-alpine AS build-base
RUN apk add --no-cache git
ENV CGO_ENABLED=0
WORKDIR /src

# RELEASE.2025-04-22T22-12-26Z -> 2025-04-22T22:12:26Z, the version string gen-ldflags.go expects
FROM build-base AS build-minio
ARG MINIO_RELEASE
RUN git clone --depth 1 --branch "${MINIO_RELEASE}" https://github.com/minio/minio.git . && \
    VERSION=$(echo "${MINIO_RELEASE}" | sed -E 's/RELEASE\.([0-9-]+)T([0-9]+)-([0-9]+)-([0-9]+)Z/\1T\2:\3:\4Z/') && \
    go build -tags kqueue -trimpath -ldflags "$(go run buildscripts/gen-ldflags.go "${VERSION}")" -o /out/minio

FROM build-base AS build-mc
ARG MC_RELEASE
RUN git clone --depth 1 --branch "${MC_RELEASE}" https://github.com/minio/mc.git . && \
    VERSION=$(echo "${MC_RELEASE}" | sed -E 's/RELEASE\.([0-9-]+)T([0-9]+)-([0-9]+)-([0-9]+)Z/\1T\2:\3:\4Z/') && \
    go build -tags kqueue -trimpath -ldflags "$(go run buildscripts/gen-ldflags.go "${VERSION}")" -o /out/mc

# curl is needed by the compose healthcheck
FROM alpine:3.21 AS minio
RUN apk add --no-cache ca-certificates curl
COPY --from=build-minio /out/minio /usr/bin/minio
EXPOSE 9000 9001
ENTRYPOINT ["/usr/bin/minio"]

FROM alpine:3.21 AS mc
RUN apk add --no-cache ca-certificates
COPY --from=build-mc /out/mc /usr/bin/mc
ENTRYPOINT ["/usr/bin/mc"]
