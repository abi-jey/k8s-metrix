from fastapi import FastAPI
from k8s_metrix import K8sMetrix
from k8s_metrix.integrations._fastapi import LifeSpanManager
from k8s_metrix.integrations._fastapi import configure
from fastapi import WebSocket
import logging
from contextlib import asynccontextmanager
from asyncio import sleep
from logging import getLogger

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
    Endpoint to retrieve all metrics.
    """
    logger.debug("[metrix-server]: retrieving all metrics")
    keys = await metrix.all_metrics()
# {
#       "describedObject": {
#         "kind": "Service",
#         "namespace": "default",
#         "name": "my-service",
#         "apiVersion": "v1"
#       },
#       "metric": {
#         "name": "requests_per_second",
#         "selector": null
#       },
#       "timestamp": "2025-06-07T22:00:00Z",
#       "windowSeconds": 60,
#       "value": "145"
#     }
    per_service_items = [
        {
            "describedObject": {
                "kind": "Service",
                "namespace": "default",
                "name": key,
                "apiVersion": "v1"
            },
            "metric": {
                "name": key,
                "selector": None
            },
            "timestamp": timestamp
            "windowSeconds": 60,
            "value": "145"
        } for key in keys
    ]
    return {
        "kind": "MetricIdentifierList",
        "apiVersion": "custom.metrics.k8s.io/v1beta2",
        "items": [
            {"name": key} for key in keys
        ]
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="localhost", port=8000)