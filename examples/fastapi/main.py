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

metrix = K8sMetrix(backend="fs")
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
def read_root():
    return {"Hello": "World"}

@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await ws.accept()
    while True:
        data = await ws.receive_text()
        await ws.send_text(f"Message text was: {data}")




if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="localhost", port=8000)