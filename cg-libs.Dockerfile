FROM cgr.dev/chainguard-private/python:3.14-dev

WORKDIR /app

ENV HOME=/home/nonroot
COPY requirements.txt .
RUN --mount=type=secret,id=pip_conf,target=/etc/pip.conf,mode=0644 \
    --mount=type=secret,id=netrc,target=/home/nonroot/.netrc,mode=0600,uid=65532 \
    pip install --timeout 60 --no-cache-dir -r requirements.txt -v

COPY app.py .

ENTRYPOINT ["python", "app.py"]