# tokenmill, core tier plus the out-of-process document converters.
#
# **What this image is.** The `pip install tokenmill` experience with Pandoc and
# LibreOffice already present, so the two backends that need a system binary
# work without anyone installing anything. It is a CLI image: the entrypoint is
# `tokenmill`, and `docker run --rm -v "$PWD:/work" tokenmill convert doc.pdf`
# is the intended use.
#
# **What it is not.** Not a GPU image and not a model server. Nothing here
# downloads weights, and no heavy backend is installed — `heavy = []` is empty
# in `pyproject.toml` and stays that way. `docker/compose.heavy.yml` is where
# the GPU services live, and none of those has been run either; that file says
# so itself.
#
# **Licence note, and it is the reason for the two-stage build.** Pandoc is
# GPL-2.0-or-later and LibreOffice is MPL-2.0. tokenmill never imports either —
# they are executed as separate programs across a process boundary, which is
# what keeps this image's own Apache-2.0 licence intact. Shipping them *in* the
# image is distribution, so `docs/LICENSES.md` states what this artefact
# contains and under which terms. If that is not a distribution you want to
# make, build with `--target core`, which has neither.

# --------------------------------------------------------------------------
# Stage 1: build the wheel from this source tree, so the image contains the
# same artefact the release workflow publishes rather than a copy of `src/`.
# --------------------------------------------------------------------------
FROM python:3.12-slim-bookworm AS build

WORKDIR /src
RUN pip install --no-cache-dir "hatchling>=1.27"

# The build needs the version out of the package and the readme out of the root,
# so this is a full copy rather than a minimal one. `.dockerignore` keeps the
# fixtures, the results and the git history out.
COPY . .
RUN python -m hatchling build -t wheel && ls -la dist/

# --------------------------------------------------------------------------
# Stage 2 (`core`): Python dependencies only. No system binaries, nothing under
# a copyleft licence. This is the target to build if you want the lightest
# possible image or the cleanest possible licence position.
# --------------------------------------------------------------------------
FROM python:3.12-slim-bookworm AS core

LABEL org.opencontainers.image.title="tokenmill"
LABEL org.opencontainers.image.description="One interface over open-source document, web and repo converters, with honest before/after token accounting."
LABEL org.opencontainers.image.source="https://github.com/RSD-Studio/tokenmill"
LABEL org.opencontainers.image.licenses="Apache-2.0"

# tiktoken caches its downloaded vocabulary here. Set explicitly so a container
# started with a mounted cache reuses it instead of downloading on every run,
# and so the path is somewhere a non-root user can actually write.
ENV TIKTOKEN_CACHE_DIR=/home/mill/.cache/tiktoken \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN useradd --create-home --uid 10001 mill

COPY --from=build /src/dist/*.whl /tmp/
RUN pip install --no-cache-dir /tmp/*.whl && rm /tmp/*.whl

USER mill
WORKDIR /work
ENTRYPOINT ["tokenmill"]
CMD ["--help"]

# --------------------------------------------------------------------------
# Stage 3 (`full`, the default): adds Pandoc and LibreOffice.
# --------------------------------------------------------------------------
FROM core AS full

USER root

# `libreoffice-core` alone is not enough and this project has the scar to prove
# it: a container with only the core package reported `libreoffice` available
# and then converted nothing, because the format filters live in the writer,
# calc and impress packages. The probe now checks the component registry, and
# this line installs what the probe looks for.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        pandoc \
        libreoffice-writer \
        libreoffice-calc \
        libreoffice-impress \
    && rm -rf /var/lib/apt/lists/* \
    && pandoc --version | head -1 \
    && soffice --version

USER mill
WORKDIR /work
ENTRYPOINT ["tokenmill"]
CMD ["--help"]
