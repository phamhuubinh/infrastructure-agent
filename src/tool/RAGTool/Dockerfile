FROM python:3.12-slim

WORKDIR /srv

# System deps needed by common optional providers (uncomment as needed):
# - libgl1, libglib2.0-0: OpenCV (PaddleOCR dependency)
# RUN apt-get update && apt-get install -y --no-install-recommends \
#     libgl1 libglib2.0-0 \
#     && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app

EXPOSE 8080

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]
