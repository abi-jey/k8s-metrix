from fastapi import FastAPI
from k8s_metrix import K8sMetrix
from k8s_metrix.integrations._fastapi import LifeSpanManager
from k8s_metrix.integrations._fastapi import configure
from fastapi import WebSocket
import logging
from contextlib import asynccontextmanager
from asyncio import sleep
from logging import getLogger
from fastapi.openapi.utils import get_openapi

from rich.logging import RichHandler

logging.basicConfig(level=logging.DEBUG, format="%(message)s", datefmt="[%X]", handlers=[RichHandler()])

logger = getLogger(__name__)


metrix = K8sMetrix(backend="fs")

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Example lifespan function that can be registered with the LifeSpanManager.
    This function will be called during the startup and shutdown of the FastAPI app.
    """
    logger.debug("[metrix-server]: starting lifespan function")
    await metrix.start()
    yield
    logger.debug("[metrix-server]: shutting down lifespan function")


app = FastAPI(docs_url="/", lifespan=lifespan)

@app.get("/apis/custom.metrics.k8s.io/v1beta2")
async def get_all_metrics():
    """
    Endpoint to retrieve all metrics in Kubernetes custom metrics API format.
    """
    logger.debug("[metrix-server]: retrieving all metrics")
    keys = await metrix.all_metrics()

    resources = []
    for key in keys:
        parts = key.split("/")
        
        if len(parts) >= 4:
            # Parse the metric key: resource_type/namespace/resource_name/metric_name
            resource_type = parts[0]  # service, pod, or no_resource_type
            namespace = parts[1]
            resource_name = parts[2]
            metric_name = parts[3]
            
            # Map our resource types to Kubernetes resource types
            if resource_type == "service":
                k8s_resource = "services"
            elif resource_type == "pod":
                k8s_resource = "pods"
            elif resource_type == "no_resource_type":
                # For metrics without specific resource type, default to pods
                k8s_resource = "pods"
            else:
                # Fallback for unknown resource types
                k8s_resource = "pods"
            
            # Skip if this is the fallback "no_*" structure and use a generic name
            if resource_type == "no_resource_type":
                resource_entry = {
                    "name": f"pods/{metric_name}",
                    "singularName": "",
                    "namespaced": True,
                    "kind": "MetricValueList",
                    "verbs": ["get"]
                }
            else:
                resource_entry = {
                    "name": f"{k8s_resource}/{metric_name}",
                    "singularName": "",
                    "namespaced": True,
                    "kind": "MetricValueList",
                    "verbs": ["get"]
                }
            
            # Avoid duplicates by checking if this resource name already exists
            if not any(r["name"] == resource_entry["name"] for r in resources):
                resources.append(resource_entry)
    
    return {
        "kind": "APIResourceList",
        "apiVersion": "v1",
        "groupVersion": "custom.metrics.k8s.io/v1beta2",
        "resources": resources
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
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="localhost", port=8000)