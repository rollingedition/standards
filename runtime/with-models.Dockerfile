# A book's runtime with its pinned model files (examples.py): the pins' image (PINS, from Dockerfile) and the models'
# own image (MODELS, from models.Dockerfile), whose whole tree, /opt/re/hf and its folders, is copied on with --link.
# A linked copy doesn't depend on the image below it, and copying the models' image's root makes nothing new: every
# folder and file comes with its own metadata, none with the build's time. So the layer is the same whatever the pins
# are, and a pin bump adds no model bytes.
ARG PINS
ARG MODELS
FROM ${MODELS} AS models
FROM ${PINS}
ARG CACHE=/opt/re/hf
COPY --link --from=models / /
ENV HF_HOME=${CACHE} HF_HUB_OFFLINE=1 HF_HUB_DISABLE_TELEMETRY=1
