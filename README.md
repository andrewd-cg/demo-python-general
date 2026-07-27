# Chainguard Container Security Demo (Python)

A Flask app that analyzes images and demonstrates TLS inspection and AI captioning, used to show how to progressively harden a Python container from a public Docker Hub image to a Chainguard secure image, and from public PyPI packages to Chainguard's verified libraries.

---

## The App

A Flask image-analyzer with the following endpoints:
- `GET /` renders the Secure Image Analyzer UI — paste any `https://` image URL to inspect it
- `POST /analyze` fetches the image URL, extracts metadata (via Pillow), checks the TLS certificate of the host, and optionally generates an AI caption via Mistral
- `POST /token` issues a short-lived JWT for demo purposes
- `GET /health` returns health status

It uses these requirements (see [requirements.txt](requirements.txt)):
- `flask` — the web server
- `werkzeug` — WSGI utilities (pinned to match Flask)
- `requests` — fetches the remote image in `/analyze`
- `pillow` — reads image dimensions, frame count, and EXIF data
- `mistralai` — the Mistral AI client used for image captioning
- `pyjwt` — issues and verifies JWT tokens

Set `MISTRAL_API_KEY` (and optionally `MISTRAL_MODEL`, default `pixtral-12b-2409`) to enable captioning. Without a key the app still runs; the caption field in `/analyze` responses will be empty.

### Run locally

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python app.py
# open http://localhost:3000
```

---

## Summary

| Step | Base Image | pip Source | Shell |
|------|-----------|------------|-------|
| 1 | `python:3.13` (Docker Hub) | pypi.org | Yes |
| 2 | Chainguard `python:3.13-dev` | pypi.org | Yes |
| 3 | Chainguard `python:3.13-dev` | Chainguard Libraries (`libraries.cgr.dev`) | Yes |
| 4 | Chainguard `python:3.13-dev` | Chainguard Libraries + Remediated | Yes |

> The CVE and package counts below are representative — run `grype` against each image you build to see the real numbers for the current day's scan.

---

## Step 1: Build the starting Dockerfile (public Docker Hub)

The baseline [Dockerfile](Dockerfile) uses the official `python:3.13` image from Docker Hub.

```bash
docker build -t demo-app-py:dockerhub .
docker run --rm -p 3000:3000 demo-app-py:dockerhub
curl http://localhost:3000/health
```

> **Problem:** `python:3.13` (the full Debian-based image) contains hundreds of OS packages, a shell, package managers, and other tooling your app never uses. More packages means a larger attack surface and more CVEs.

### CVE Scan Results

```bash
grype demo-app-py:dockerhub
# Expect hundreds of packages and a large number of vulnerability matches
# across critical/high/medium severities.
```

> Tip: try `python:3.13-slim` too — it's smaller than the full image but still ships a shell, `apt`, and a stream of Debian CVEs.

---

## Step 2: Convert to Chainguard Python image

A single-stage swap of the base image. [Dockerfile.chainguard](Dockerfile.chainguard) uses `cgr.dev/andrewd.dev/python:3.13-dev`, a Chainguard image with only what's needed to build and run Python dependencies.

```dockerfile
# Before
FROM python:3.13

# After
FROM cgr.dev/andrewd.dev/python:3.13-dev
```

Note the Chainguard image runs as the `nonroot` user, so we install into a virtual environment:

```dockerfile
RUN python -m venv venv
ENV PATH="/app/venv/bin:$PATH"
```

```bash
docker build -f Dockerfile.chainguard -t demo-app-py:cg .
docker run --rm -p 3000:3000 demo-app-py:cg
curl http://localhost:3000/health
```

> **Result:** Dramatically fewer packages and CVEs. The Chainguard `python:3.13-dev` image ships only what's needed to build and run Python dependencies.

```bash
grype demo-app-py:cg
```

---

## Step 3: Use Chainguard Libraries

Even with a hardened base image, your app's PyPI dependencies can carry malware or supply chain compromises. Chainguard Libraries provides a curated, audited Python index. Packages are either built directly by Chainguard or sourced from a secure mirror with advanced malware scanning and cooldown periods. See [Dockerfile.chainguard-libs](Dockerfile.chainguard-libs).

Configure pip to pull packages from Chainguard's index:

```bash
chainctl auth configure-pip --pull-token
```

This produces credentials for `libraries.cgr.dev/python`. Put them in a `pip.conf` (see [pip.conf_example](pip.conf_example)):

```ini
[global]
index-url = https://<username>:<password>@libraries.cgr.dev/python/simple/
```

Then copy `pip.conf` into the image at build time:

```dockerfile
COPY pip.conf /etc/pip.conf
RUN pip install --no-cache-dir -r requirements.txt
```

```bash
docker build -f Dockerfile.chainguard-libs -t demo-app-py:cg-libs .
docker run --rm -p 3000:3000 demo-app-py:cg-libs
curl http://localhost:3000/health
```

> **Result:** `flask`, `requests`, `pillow`, `pyjwt`, and all their transitive dependencies are now sourced from Chainguard's verified index. Packages are built, scanned, signed, and free of known malware before they ever reach your build.

```bash
grype demo-app-py:cg-libs
```

### Library Verification

Verify which libraries were built directly by Chainguard. The remainder come from Chainguard's secure mirror where packages undergo advanced scanning by Chainguard Sentinel and mandatory cooldown periods before serving.

```bash
chainctl libraries verify demo-app-py:cg-libs
```

---

## Step 4: Use Chainguard Remediated packages

Chainguard Libraries also offers a `python-remediated` index that serves packages with CVE patches backported by Chainguard — fixes that haven't yet landed upstream. For example, `pyjwt==2.3.0+cgr.2` is the same PyJWT 2.3.0 release with additional security patches applied by Chainguard. See [Dockerfile.chainguard-remediated](Dockerfile.chainguard-remediated) and [requirements-remediated.txt](requirements-remediated.txt).

Configure pip with both indexes (see [pip.conf_example-remediated](pip.conf_example-remediated)):

```ini
[global]
index-url = https://<username>:<password>@libraries.cgr.dev/python/simple
extra-index-url = https://<username>:<password>@libraries.cgr.dev/python-remediated/simple
```

Pin the remediated version in your requirements:

```
pyjwt==2.3.0+cgr.2
```

```bash
docker build -f Dockerfile.chainguard-remediated -t demo-app-py:cg-remediated .
docker run --rm -p 3000:3000 demo-app-py:cg-remediated
curl http://localhost:3000/health
```

> **Result:** Known CVEs in transitive dependencies are patched at the package level, even before upstream maintainers have released a fix.

```bash
grype demo-app-py:cg-remediated
```

---

## Bonus: Multi-stage builds and Custom Assembly

The `old/` directory contains multi-stage Dockerfile examples that use a `-dev` builder stage and copy only the virtual environment into a minimal runtime image (no shell, no `pip` at runtime).

For adding OS-level packages (e.g. system libraries needed by Pillow) without a package manager in the final image, use Chainguard's [Custom Assembly](https://edu.chainguard.dev/chainguard/chainguard-images/features/ca-docs/custom-assembly/) feature to produce a distroless image with exactly the packages you need, kept up to date by Chainguard.

![Custom Assembly](custom_assembly.gif)
