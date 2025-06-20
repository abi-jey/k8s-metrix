from fastapi import FastAPI
from fastapi import HTTPException
from pydantic import BaseModel
from typing import List, Dict, Any, Optional, Tuple
from k8s_metrix import K8sMetrix
import logging
from contextlib import asynccontextmanager
from logging import getLogger
from fastapi.openapi.utils import get_openapi
from k8s_metrix.backends import FsBackend
from k8s_metrix.backends import BaseBackend
from rich.logging import RichHandler
import os
from datetime import datetime, timedelta, timezone
import asyncio

logging.basicConfig(level=logging.DEBUG, format="%(message)s", datefmt="[%X]", handlers=[RichHandler()])


logger = getLogger(__name__)
BACKEND = os.getenv("METRIX_BACKEND", "fs").lower()

backend: BaseBackend
if BACKEND == "fs":
    logger.debug("[metrix-server]: Using file system backend for storing metrics")
    backend = FsBackend(path="metrix_data")
else:
    logger.error(f"[metrix-server]: Unsupported backend '{BACKEND}'. Only 'fs' is supported.")
    raise ValueError(f"Unsupported backend '{BACKEND}'. Only 'fs' is supported.")

# Pydantic models for request validation
class MetricData(BaseModel):
    name: str
    value: int
    timestamp: str
    metric_type: str = "gauge"  # "counter" or "gauge"
    additional_info: Dict[str, Any] = {}


class MetricsPayload(BaseModel):
    pod_name: str
    pod_namespace: str
    service_name: str
    node_name: str
    metrics: List[MetricData]
    timestamp: str



@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Example lifespan function that can be registered with the LifeSpanManager.
    This function will be called during the startup and shutdown of the FastAPI app.
    """
    logger.debug("[metrix-server]: starting lifespan function")
    await backend.init_backend()
    yield
    logger.debug("[metrix-server]: shutting down lifespan function")


app = FastAPI(docs_url="/", lifespan=lifespan)


@app.post("/metrics")
async def receive_metrics(payload: MetricsPayload):
    """
    Endpoint to receive metrics from K8sMetrix clients.
    
    Args:
        payload: The metrics payload containing pod info and metrics data
    """
    try:
        logger.debug(f"[metrix-server]: Received {len(payload.metrics)} metrics from pod "
                    f"{payload.pod_name} in namespace {payload.pod_namespace}")  # fmt: skip
        
        for metric in payload.metrics:
            await process_metric(metric, payload)
        
        return {"status": "success", "processed_metrics": len(payload.metrics)}
        
    except Exception as e:
        logger.error(f"[metrix-server]: Error processing metrics: {e}")
        raise HTTPException(status_code=500, detail=f"Error processing metrics: {str(e)}")


@app.get("/apis/custom.metrics.k8s.io/v1beta2")
async def get_all_metrics():
    """
    Endpoint to retrieve all metrics in Kubernetes custom metrics API format.
    """
    logger.debug("[metrix-server]: retrieving all metrics")
    keys = await backend.list_all_metrics()

    resources = []
    for key in keys:
        parts = key.split("/")
        
        if len(parts) >= 4:
            # Parse the metric key: resource_type/namespace/resource_name/metric_name
            resource_type = parts[0]  # service, pod, or no_resource_type
            metric_name = parts[3]
            
            if resource_type == "service":
                k8s_resource = "services"
            elif resource_type == "pod":
                k8s_resource = "pods"
            else:
                k8s_resource = "pods"

            resource_entry = {
                "name": f"{k8s_resource}/{metric_name}",
                "singularName": "",
                "namespaced": True,
                "kind": "MetricValueList",
                "verbs": ["get"]
            }
            if not any(r["name"] == resource_entry["name"] for r in resources):
                resources.append(resource_entry)

    logger.debug(f"[metrix-server]: Found {len(resources)} unique metrics")
    return {
        "kind": "APIResourceList",
        "apiVersion": "v1",
        "groupVersion": "custom.metrics.k8s.io/v1beta2",
        "resources": resources
    }

@app.get("/apis/custom.metrics.k8s.io/v1beta2/namespaces/{namespace}/{resource_type}/{resource_name}/{metric_name}")
async def get_metric_value(namespace: str, resource_type: str, resource_name: str, metric_name: str):
    """
    Endpoint to retrieve a specific metric value for a given resource.
    
    Args:
        resource_type: Type of the resource (e.g., pods, services)
        namespace: Namespace of the resource
        resource_name: Name of the resource
        metric_name: Name of the metric to retrieve
    """
    logger.debug(f"[metrix-server]: Retrieving metric '{metric_name}' for {resource_type} "
                 f"{resource_name} in namespace {namespace}")
    if resource_type == "pods":
        values = await backend.retrieve(
            name=metric_name,
            pod=resource_name,
            namespace=namespace
        )
    elif resource_type == "services":
        values = await backend.retrieve(
            name=metric_name,
            service=resource_name,
            namespace=namespace
        )
    else:
        raise HTTPException(status_code=400, detail=f"Unsupported resource type '{resource_type}'")
    if not values:
        raise HTTPException(status_code=404, detail=f"Metric '{metric_name}' not found for {resource_type} "
                                                    f"{resource_name} in namespace {namespace}")
    
    # Build items list - one item per pod for pods, single item for services
    items = []
    
    if resource_type == "pods":
        # Loop through each pod and create an item for each
        for key, records in values.items():
            if records:
                # Key is just the pod name from fs backend
                pod_name = key  # Just the pod name, not a full path
                pod_namespace = namespace  # Use the namespace from the request
                
                # Calculate per-second rate for this specific pod if needed
                latest_value = 0
                latest_timestamp = datetime.now().replace(microsecond=0).isoformat() + 'Z'
                
                if metric_name.endswith("_per_second"):
                    # Calculate rate for this individual pod
                    pod_values = {key: records}  # Single pod data
                    calculated_values = await calculate_per_second_rate(pod_values, metric_name, pod_namespace, pod_name)
                    
                    # Get the calculated value
                    for calc_key, calc_records in calculated_values.items():
                        if calc_records:
                            latest_record = calc_records[0]  # Should be single calculated value
                            latest_value = latest_record[1]
                            latest_timestamp = latest_record[0].replace(microsecond=0).isoformat() + 'Z'
                            break
                else:
                    # Get latest record for this pod (non-rate metric)
                    latest_record = max(records, key=lambda x: x[0])
                    latest_value = latest_record[1]
                    latest_timestamp = latest_record[0].replace(microsecond=0).isoformat() + 'Z'
                
                items.append({
                    "describedObject": {
                        "kind": "Pod",
                        "namespace": pod_namespace,
                        "name": pod_name,
                        "apiVersion": "v1"
                    },
                    "metric": {
                        "name": metric_name
                    },
                    "timestamp": latest_timestamp,
                    "windowSeconds": 60,
                    "value": str(latest_value)
                })
    else:
        # For services, keep the original single-item behavior
        latest_value = 0
        latest_timestamp = datetime.now().replace(microsecond=0).isoformat() + 'Z'
        for key, records in values.items():
            if records:
                latest_record = max(records, key=lambda x: x[0])
                latest_value = latest_record[1]
                latest_timestamp = latest_record[0].replace(microsecond=0).isoformat() + 'Z'
                break
        
        items.append({
            "describedObject": {
                "kind": resource_type.capitalize(),
                "namespace": namespace,
                "name": resource_name,
                "apiVersion": "v1"
            },
            "metric": {
                "name": metric_name
            },
            "timestamp": latest_timestamp,
            "windowSeconds": 60,
            "value": str(latest_value)
        })

    return {
        "kind": "MetricValueList",
        "apiVersion": "custom.metrics.k8s.io/v1beta2",
        "metadata": {},
        "items": items
    }


@app.get("/openapi/v2")
async def openapi():
    """
    Custom OpenAPI schema endpoint.
    """
    openapi_schema = get_openapi(
        title="K8s Metrix API",
        version="1.0.0",
        description="API for K8s Metrix",
        routes=app.routes,
    )
    return openapi_schema

@app.get("/apis")
async def get_apis():
    """
    Endpoint to retrieve all APIs.
    """
    return {
        "kind": "APIResourceList",
        "apiVersion": "v1",
        "groupVersion": "custom.metrics.k8s.io/v1beta2",
        "resources": [
            {
                "name": "metrics",
                "singularName": "",
                "namespaced": True,
                "kind": "MetricValueList",
                "verbs": ["get"]
            }
        ]
    }

@app.get("/health")
async def health_check():
    """
    Health check endpoint.
    """
    return {"status": "healthy", "service": "k8s-metrix-adapter"}

async def process_metric(metric: MetricData, payload: MetricsPayload):
    """
    Process a single metric based on its type.
    
    Args:
        metric: The metric data to process
        payload: The full payload containing pod/service information
    """
    metric_key = f"pod/{payload.pod_namespace}/{payload.pod_name}/{metric.name}"
    
    if metric.metric_type == "counter":
        # Handle counter metrics - calculate rate and save as _per_second
        await process_counter_metric(metric, payload, metric_key)
    else:
        # Handle gauge metrics - store as-is
        await process_gauge_metric(metric, payload, metric_key)


async def process_counter_metric(metric: MetricData, payload: MetricsPayload, metric_key: str):
    """
    Process counter metrics by saving them with _per_second suffix.
    The actual rate calculation will be done on fetch.
    """
    # Save the raw counter value with _per_second suffix
    per_second_name = f"{metric.name}_per_second"
    await backend.record(
        name=per_second_name,
        value=metric.value,
        service=payload.service_name,
        pod=payload.pod_name,
        namespace=payload.pod_namespace
    )
    
    logger.debug(f"[metrix-server]: Stored counter metric {per_second_name} = {metric.value}")


async def process_gauge_metric(metric: MetricData, payload: MetricsPayload, metric_key: str):
    """
    Process gauge metrics by storing them as-is.
    """
    await backend.record(
        name=metric.name,
        value=metric.value,
        service=payload.service_name,
        pod=payload.pod_name,
        namespace=payload.pod_namespace
    )
    
    logger.debug(f"[metrix-server]: Stored gauge metric {metric_key} = {metric.value}")

async def calculate_per_second_rate(values: Dict[str, List[Tuple[datetime, int]]], metric_name: str, 
                                    namespace: str, resource_name: str) -> Dict[str, List[Tuple[datetime, int]]]:
    """
    Calculate the average per-second rate for counter metrics over the past 60 seconds.
    
    Args:
        values: Raw metric values from backend
        metric_name: Name of the metric
        namespace: Namespace of the resource
        resource_name: Name of the resource
        
    Returns:
        Dictionary with calculated rate values
    """
    # Get all tuples from all pods for this metric
    all_records = []
    for pod_key, records in values.items():
        all_records.extend(records)  # records is List[Tuple[datetime, int]]
    
    if not all_records:
        current_time = datetime.now()
        logger.debug(f"[metrix-server]: No records found for {resource_name}/{metric_name}, returning 0/sec")
        return {f"pod/{namespace}/{resource_name}/{metric_name}": [(current_time, 0)]}
    
    # Get records from last 60 seconds
    current_time = datetime.now()
    cutoff_time = current_time - timedelta(seconds=60)
    
    # Filter records from last 60 seconds
    recent_records = [
        record for record in all_records 
        if record[0] >= cutoff_time  # record[0] is datetime
    ]
    
    if len(recent_records) >= 2:
        total  = [record[1] for record in recent_records]  # Get all values

        
        # Average per second = total increments / 60
        avg_rate = sum(total) / 60
        
        logger.debug(f"[metrix-server]: Calculated rate for {resource_name}/{metric_name}: "
                    f"{avg_rate:.2f}/sec (total: {total}, "
                    f"records: {len(recent_records)}, timespan: 60s)")  # fmt: skip
        
        return {f"pod/{namespace}/{resource_name}/{metric_name}": [(current_time, int(avg_rate))]}
    else:
        # Not enough data, return 0
        current_time = datetime.now()
        logger.debug(f"[metrix-server]: Not enough data for {resource_name}/{metric_name}: "
                    f"{len(recent_records)} records, returning 0/sec")  # fmt: skip
        return {f"pod/{namespace}/{resource_name}/{metric_name}": [(current_time, 0)]}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)