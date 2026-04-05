FROM python:3.12-alpine@sha256:7747d47f92cfca63a6e2b50275e23dba8407c30d8ae929a88ddd49a5d3f2d331

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY *.py .

CMD ["python", "pollen_alert.py"]
