FROM python:3.11

RUN apt-get update -y && apt-get upgrade -y

WORKDIR /app
COPY main.py /app/main.py
RUN pip install fastapi uvicorn[standard]
ARG CACHEBUST=1
RUN echo "Cache bust: $CACHEBUST"
RUN pip install k8s-metrix --pre
RUN pip install rich 

EXPOSE 8000
ENTRYPOINT ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port 8000"]
