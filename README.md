# Chainguard Container Security Demo (Python)

A Python app that fetches real-time stock prices for the top 10 US-listed companies by market cap. Used to demonstrate progressive container hardening — from a public Docker Hub image to a Chainguard image, and from public PyPI packages to Chainguard Libraries.

---

## The App

`app.py` fetches prices concurrently from Yahoo Finance and prints a formatted table.

**Dependencies** (`requirements.txt`):
- `aiohttp==3.13.5`
- `pillow==12.3.0`
- `mistralai==2.4.5`

---

## Prerequisites

- Docker
- [Grype](https://github.com/anchore/grype)

---

## Demo Steps

Each script pulls the base image, builds the app image, then pauses so you can review the build output. Press **Enter** at the prompt to run the Grype scan.

### Step 1 — Public Docker Hub image

```bash
./build-and-scan-public.sh
```

Builds `demo-chainguard-python:public` from `python:latest` (Docker Hub). Expect a large number of CVEs from the full Debian-based image and its bundled tooling.

### Step 2 — Chainguard image

```bash
./build-and-scan-cg.sh
```

Builds `demo-chainguard-python:cg` from `cgr.dev/chainguard/python:latest-dev` with packages installed from the public PyPI index. The minimal Chainguard base dramatically reduces the CVE count compared to Step 1.

### Step 3 — Chainguard image with Chainguard Libraries

```bash
./build-and-scan-cg-libs.sh
```

Builds `demo-chainguard-python:cg-libs` from `cgr.dev/chainguard/python:latest-dev` with packages pulled from the Chainguard pip registry. Packages are built, scanned, and signed by Chainguard before serving.

**Before running this step**, ensure you have:
1. Run `chainctl auth configure-pip --pull-token` to generate credentials.
2. A `.netrc` file with valid Chainguard Library credentials (used by `cg-libs.Dockerfile`).
3. A `pip.conf.cg` file pointing to `libraries.cgr.dev`.

---

## Dockerfiles

| Dockerfile | Base image | pip source | Image tag |
|---|---|---|---|
| `Dockerfile` | `python:latest` | pypi.org | `demo-chainguard-python:public` |
| `cg.Dockerfile` | `cgr.dev/chainguard/python:latest-dev` | pypi.org | `demo-chainguard-python:cg` |
| `cg-libs.Dockerfile` | `cgr.dev/chainguard/python:latest-dev` | `libraries.cgr.dev` | `demo-chainguard-python:cg-libs` |
