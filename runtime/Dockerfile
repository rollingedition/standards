# The pinned runtime for a book's examples in CI and on Cloud Run.
# Built from the book's examples/.python-version and examples/requirements.txt; run with --network none.
ARG PYTHON_VERSION
FROM python:${PYTHON_VERSION}-slim
# Two runtime libraries the slim image leaves out: GNU OpenMP, which LightGBM, XGBoost and other OpenMP builds load,
# and GNU atomics, which regopy's native library links against and its wheel doesn't bundle.
RUN apt-get update && apt-get install -y --no-install-recommends libgomp1 libatomic1 && rm -rf /var/lib/apt/lists/*
COPY requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir --disable-pip-version-check -r /tmp/requirements.txt && rm /tmp/requirements.txt
RUN useradd --create-home reader
USER reader
WORKDIR /work
