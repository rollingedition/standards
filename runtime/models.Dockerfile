# A book's pinned model files as an image of their own (examples.py, models.py), for a book with examples/models.toml.
# Keyed by the models alone, never the pins: a book's new pins reuse this image, and with-models.Dockerfile copies its
# one layer onto the pins' image, the same blob each time, so a registry keeps the files once.
# They're fetched once, on the pinned Python image (BASE, from data/runtime-base.toml), each file's SHA-256 checked, and
# then read offline: the examples run with --network none, and the Hugging Face libraries find the pinned commit in
# HF_HOME (with-models.Dockerfile sets it).
ARG BASE
FROM ${BASE} AS fetch
ARG BASE_URL
ARG CACHE=/opt/re/hf
COPY models.json fetch_models.py /tmp/models/
RUN python /tmp/models/fetch_models.py /tmp/models/models.json "${CACHE}" "${BASE_URL}" \
    && chmod -R a+rX "${CACHE}"

FROM scratch
ARG CACHE=/opt/re/hf
COPY --from=fetch ${CACHE} ${CACHE}
