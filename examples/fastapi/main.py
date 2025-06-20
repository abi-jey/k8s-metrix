from fastapi import FastAPI
from k8s_metrix import K8sMetrix
from k8s_metrix.integrations._fastapi import LifeSpanManager
from k8s_metrix.integrations._fastapi import configure
from fastapi import WebSocket
import logging
from contextlib import asynccontextmanager
from asyncio import sleep

from rich.logging import RichHandler

logging.basicConfig(level=logging.DEBUG, format="%(message)s", datefmt="[%X]", handlers=[RichHandler()])

# Initialize K8sMetrix in client mode to send metrics to the adapter
metrix = K8sMetrix()
lsm = LifeSpanManager(metrix)
app = FastAPI(docs_url="/", lifespan=lsm)
configure(app, metrix)


@asynccontextmanager
async def some_lifespan_function(app: FastAPI):
    """
    Example lifespan function that can be registered with the LifeSpanManager.
    This function will be called during the startup and shutdown of the FastAPI app.
    """
    logging.debug("Starting lifespan function")
    # Simulate some startup work
    await sleep(0.1)
    logging.debug("Lifespan function ready")
    yield
    logging.debug("Shutting down lifespan function")
    # Simulate some cleanup work
    await sleep(0.1)
    logging.debug("Lifespan function shutdown complete")

# Example of adding additional lifespan functions, this is done in order not to
#  override the existing ones from k8s_metrix. this way you can stack multiple lifespan functions.
lsm.register(some_lifespan_function)

@app.get("/api")
async def read_root():
    return {"Hello": "World"}

@app.get("/api/health")
async def health_check():
    return {"status": "healthy"}

WEBSOCKET_CONNECTIONS = 0
@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await ws.accept()    
    try:
        while True:
            global WEBSOCKET_CONNECTIONS
            WEBSOCKET_CONNECTIONS += 1
            # Record websocket connection
            await metrix.add_metric("websocket_connections", WEBSOCKET_CONNECTIONS)
            data = await ws.receive_text()
            await ws.send_text(f"Message text was: {data}")
    except Exception:
        raise


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="localhost", port=8000)