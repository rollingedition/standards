# The pinned runtime for a book's examples in CI and on Cloud Run.
# Built from the book's examples/.python-version and examples/requirements.txt; run with --network none.
# BASE and PACKAGES come from the standards' data/runtime-base.toml (examples.ContainerBackend): the Python image by
# digest, such as python:3.12.15-slim@sha256:..., and the Debian packages it adds, each at its version, such as
# libgomp1=14.2.0-19 (GNU OpenMP, which LightGBM and other OpenMP builds load). So the same pins build the same image.
ARG BASE
FROM ${BASE}
ARG PACKAGES
RUN apt-get update && apt-get install -y --no-install-recommends ${PACKAGES} && rm -rf /var/lib/apt/lists/*
# The standard library's bytecode, which the image ships none of, compiled once here, before the pins, so the layer is
# the same for every book on this base; pip compiles the packages' as it installs them. Examples run with -B, so no run
# writes any, and every run starts from the same files. The exclusions are CPython's own install's.
RUN python -m compileall -q -j 0 -x 'bad_coding|badsyntax|site-packages|lib2to3/tests/data' \
        "$(python -c 'import sysconfig; print(sysconfig.get_path("stdlib"))')"
COPY requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir --disable-pip-version-check -r /tmp/requirements.txt && rm /tmp/requirements.txt
RUN useradd --create-home reader
USER reader
WORKDIR /work
