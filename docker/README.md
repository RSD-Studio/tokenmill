# `docker/`

Compose files for the GPU-tier backends, and one honest sentence about them:
**none of these has been run.** The development sandbox this project is built in
has no GPU and its egress proxy denies the model host, so the images have never
been pulled and the services have never answered. The arguments follow each
project's own published serving instructions; treat them as a read starting
point rather than a tested configuration.

## What tokenmill does and does not do

tokenmill **never starts a container and never looks for one.** A service
backend is unavailable until you tell it where the service is:

```bash
docker compose -f docker/compose.heavy.yml --profile deepseek up
tokenmill convert page.png --backend deepseek_ocr \
    --extra deepseek_ocr_url=http://localhost:8000 --allow-network
```

That is deliberate. A converter that probed `localhost` on a range of ports
would be doing something nobody asked for, and on a shared machine it would
occasionally find somebody else's model. `--allow-network` is required even
though the address is loopback, because talking to a service is a network call
whichever interface it is on.

Every service sits behind a Compose profile, so `up` with no profile starts
nothing.

## The subprocess backends are not here

Marker, Surya, MinerU and olmOCR are Python packages with command-line entry
points, so they run from a virtual environment of their own rather than from a
container. `tokenmill doctor` prints the two commands each of them needs.

## Before you start one

- These images want an NVIDIA GPU. `tokenmill doctor` tells you whether this
  machine has a usable one, and distinguishes "no GPU" from "the driver is here
  and no device answered" — which is what a container started without `--gpus`
  looks like.
- The first `up` downloads model weights: tens of gigabytes, and several
  minutes before the health check passes. The `start_period` allows for it.
- `--trust-remote-code` is on for both services, and it means what it says: vLLM
  imports modelling code from the model repository. Both models need it to run
  at all. It is in the compose file rather than an adapter so that the person
  starting the container is the person making that decision.
