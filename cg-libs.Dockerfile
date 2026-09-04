FROM cgr.dev/chainguard/python:latest-dev

WORKDIR /app

COPY pip.conf.cg /etc/pip.conf
COPY --chmod=600 --chown=nonroot:nonroot .netrc /home/nonroot/.netrc
ENV HOME=/home/nonroot
COPY requirements.txt .
RUN pip install --timeout 60 --no-cache-dir -r requirements.txt

COPY app.py .

ENTRYPOINT ["python", "app.py"]