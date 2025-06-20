# K8sMetrix Client Usage

This document explains how to use K8sMetrix as a client to record metrics and send them to the metrix-adapter.

## Overview

K8sMetrix can operate in two modes:

1. **Client Mode** (`as_client=True`): Records metrics in an async queue and sends them to the adapter via HTTP
2. **Server Mode** (`as_client=False`): Uses a backend (filesystem, Redis) to store metrics directly

## Client Mode Architecture

```
[Your Application] -> [K8sMetrix Client] -> [Async Queue] -> [HTTP Client] -> [Metrix Adapter] -> [Backend Storage]
```

## Environment Variables

When running as a client in Kubernetes, the following environment variables should be set on your pod:

- `HOSTNAME`: Pod name (usually set automatically by Kubernetes)
- `POD_NAMESPACE`: Kubernetes namespace of the pod
- `SERVICE_NAME`: Name of the service (set manually)
- `NODE_NAME`: Kubernetes node name

Example pod specification:
```yaml
apiVersion: v1
kind: Pod
metadata:
  name: my-app
  namespace: default
spec:
  containers:
  - name: my-app
    image: my-app:latest
    env:
    - name: POD_NAMESPACE
      valueFrom:
        fieldRef:
          fieldPath: metadata.namespace
    - name: NODE_NAME
      valueFrom:
        fieldRef:
          fieldPath: spec.nodeName
    - name: SERVICE_NAME
      value: "my-service"
```

## Usage Example

### Basic Client Usage

```python
import asyncio
from k8s_metrix import K8sMetrix

async def main():
    # Initialize client
    client = K8sMetrix(
        as_client=True,
        adapter_url="http://metrix-adapter.metrix-system.svc.cluster.local:8000"
    )
    
    # Start the client (starts the daemon loop)
    await client.start()
    
    # Record metrics
    await client.add_metric("cpu_usage_percent", 75)
    await client.add_metric("memory_usage_mb", 1024)
    await client.add_metric("request_count", 42, {"endpoint": "/api/health"})
    
    # Metrics are automatically sent to the adapter every 5 seconds
    
    # Keep running...
    await asyncio.sleep(30)
    
    # Cleanup
    await client.stop()

if __name__ == "__main__":
    asyncio.run(main())
```

### Integration with FastAPI

```python
from fastapi import FastAPI
from k8s_metrix import K8sMetrix
from contextlib import asynccontextmanager

# Initialize K8sMetrix client
metrix_client = K8sMetrix(as_client=True)

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Start the metrics client
    await metrix_client.start()
    yield
    # Stop the metrics client
    await metrix_client.stop()

app = FastAPI(lifespan=lifespan)

@app.get("/api/users")
async def get_users():
    # Record a metric for this endpoint
    await metrix_client.add_metric("api_users_requests", 1)
    
    # Your business logic here
    return {"users": []}

@app.middleware("http")
async def metrics_middleware(request, call_next):
    import time
    
    start_time = time.time()
    response = await call_next(request)
    process_time = int((time.time() - start_time) * 1000)  # Convert to milliseconds
    
    # Record response time metric
    await metrix_client.add_metric(
        "response_time_ms", 
        process_time,
        {"endpoint": str(request.url.path), "method": request.method}
    )
    
    return response
```

## Configuration

### Client Configuration

```python
client = K8sMetrix(
    as_client=True,                                    # Enable client mode
    adapter_url="http://localhost:8000",               # Adapter endpoint URL
    discovery=True                                     # Enable service discovery (optional)
)
```

### Adapter Configuration

The adapter runs as a separate service and provides:

- `POST /metrics`: Endpoint to receive metrics from clients
- `GET /apis/custom.metrics.k8s.io/v1beta2`: Kubernetes custom metrics API
- `GET /health`: Health check endpoint

## Starting the Adapter

```python
# examples/start_adapter.py
python examples/start_adapter.py
```

Or using uvicorn directly:
```bash
uvicorn k8s_metrix.adapter.main:app --host 0.0.0.0 --port 8000
```

## Metrics Storage Format

Metrics are stored with the following structure:

```
pod/{namespace}/{pod_name}/{metric_name}
```

For example:
- `pod/default/my-app-123/cpu_usage_percent`
- `pod/production/web-server-456/request_count`

## Dependencies

The client mode requires the following additional dependency:

```toml
[dependencies]
aiohttp = ">=3.8.0"
```

## Error Handling

The client handles errors gracefully:

- Network failures: Metrics are queued and retry is attempted on the next cycle
- Adapter unavailable: Metrics accumulate in the queue until the adapter is available
- Queue overflow: Older metrics may be lost if the queue grows too large

## Performance Considerations

- Metrics are sent in batches every 5 seconds to reduce HTTP overhead
- The async queue prevents blocking your application when recording metrics
- HTTP connections are reused via aiohttp ClientSession

## Deployment in Kubernetes

1. Deploy the adapter as a service in your cluster
2. Configure your application pods with the required environment variables
3. Set the adapter URL to point to the adapter service
4. Use the K8sMetrix client in your applications

Example deployment structure:
```
metrix-system/
├── metrix-adapter (Deployment + Service)
└── your-apps/ (using K8sMetrix client)
```
