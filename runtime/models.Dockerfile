# Pinned model files on top of a book's runtime image (examples.py, models.py), for a book with examples/models.toml.
# They're fetched once, while the image is built, each file's SHA-256 checked, and then read offline: the examples run
# with --network none, and the Hugging Face libraries find the pinned commit in HF_HOME.
ARG BASE
FROM ${BASE}
ARG BASE_URL
ARG CACHE=/opt/re/hf
USER root
COPY models.json fetch_models.py /tmp/models/
RUN python /tmp/models/fetch_models.py /tmp/models/models.json "${CACHE}" "${BASE_URL}" \
    && chmod -R a+rX "${CACHE}" && rm -rf /tmp/models
ENV HF_HOME=${CACHE} HF_HUB_OFFLINE=1 HF_HUB_DISABLE_TELEMETRY=1
USER reader
