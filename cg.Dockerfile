FROM cgr.dev/chainguard/python:latest-dev

WORKDIR /app

COPY pip.conf /etc/pip.conf
COPY requirements.txt .
RUN pip install --timeout 60 --no-cache-dir -r requirements.txt

COPY app.py .

ENTRYPOINT ["python", "app.py"]