FROM python:3.11-slim

RUN apt-get update -y && apt-get upgrade -y

WORKDIR /app
COPY main.py /app/main.py
RUN pip install fastapi uvicorn[standard]
RUN pip install k8s-metrix --pre
RUN pip install rich
ENV TLS_KEY_PATH="/etc/ssl/certs/k8s-metrix/tls.key"
ENV TLS_CERT_PATH="/etc/ssl/certs/k8s-metrix/tls.crt"

EXPOSE 8000
ENTRYPOINT ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port 8000 --ssl-keyfile $TLS_KEY_PATH --ssl-certfile $TLS_CERT_PATH"]
