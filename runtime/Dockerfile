# The pinned runtime for a book's examples in CI and on Cloud Run.
# Built from the book's examples/.python-version and examples/requirements.txt; run with --network none.
ARG PYTHON_VERSION
FROM python:${PYTHON_VERSION}-slim
# The GNU OpenMP runtime, which the slim image leaves out and LightGBM, XGBoost and other OpenMP builds load.
RUN apt-get update && apt-get install -y --no-install-recommends libgomp1 && rm -rf /var/lib/apt/lists/*
COPY requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir --disable-pip-version-check -r /tmp/requirements.txt && rm /tmp/requirements.txt
RUN useradd --create-home reader
USER reader
WORKDIR /work
