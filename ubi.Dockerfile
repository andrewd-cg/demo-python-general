FROM registry.access.redhat.com/ubi8/python-312

WORKDIR /app

COPY requirements.txt .
RUN pip install --timeout 60 --no-cache-dir -r requirements.txt

COPY app.py .

ENTRYPOINT ["python", "app.py"]
