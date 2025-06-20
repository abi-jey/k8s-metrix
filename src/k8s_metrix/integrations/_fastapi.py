from logging import getLogger
from k8s_metrix import K8sMetrix
from typing import AsyncGenerator, List, AsyncContextManager, Callable
from contextlib import AsyncExitStack
from contextlib import asynccontextmanager
from typing import Callable
from fastapi import Request
from fastapi import Response
logger = getLogger(__name__)


try:
    from fastapi import FastAPI
except Exception as e:
    logger.warning("FastAPI is not installed. Please install it to use this integration.")
    raise e

def _lifespan(k8s_metrix: K8sMetrix) -> Callable[[FastAPI], AsyncContextManager[None]]:
    """
    Configure FastAPI to expose metrics.

    Args:
        k8s_metrix (K8sMetrix): The K8sMetrix instance.
    """
    if not isinstance(k8s_metrix, K8sMetrix):
        raise TypeError("k8s_metrix must be an instance of K8sMetrix")

    logger.debug("[k8s-metrix|fastapi]: Configuring FastAPI to expose metrics.")


    @asynccontextmanager
    async def lifespan_context(app: FastAPI) -> AsyncGenerator[None, None]:
        """
        Wrapper function to expose metrics in FastAPI.
        
        Args:
            app (FastAPI): The FastAPI app instance.
        """
        logger.debug("[k8s-metrix|fastapi]: Starting lifespan context for K8sMetrix.")

        await k8s_metrix.start()
        logger.debug("[k8s-metrix|fastapi]: K8sMetrix started, exposing metrics endpoint.")
        @app.get("/metrics", tags=["x-metrix"])
        async def metrics():
            return k8s_metrix.expose_metrics()

        @app.get("/apis/custom.metrics.k8s.io/v1beta2", tags=["x-metrix"])
        async def custom_metrics():
            """
            Custom metrics endpoint for K8sMetrix.
            This endpoint is used to expose custom metrics in the Kubernetes API format.
            """
            return 

        logger.debug("[k8s-metrix|fastapi]: Metrics endpoint configured.")

        yield

    return lifespan_context

def configure(app: FastAPI, k8s_metrix: K8sMetrix) -> None:
    """
    Configure FastAPI with K8sMetrix.

    Args:
        app (FastAPI): The FastAPI app instance.
        k8s_metrix (K8sMetrix): The K8sMetrix instance.
    """
    if not isinstance(app, FastAPI):
        raise TypeError("app must be an instance of FastAPI")
    if not isinstance(k8s_metrix, K8sMetrix):
        raise TypeError("k8s_metrix must be an instance of K8sMetrix")

    async def middleware(request: Request, call_next: Callable) -> Response:
        """
        Middleware to handle requests and responses.
        """
        await k8s_metrix.add_metric("requests", 1, metric_type="counter")
        response = await call_next(request)
        return response
    
    app.middleware("http")(middleware)
    logger.debug("[k8s-metrix|fastapi]: Middleware configured to count requests.")


class LifeSpanManager:
    """
    FastAPI lifespan manager for K8sMetrix.
    """

    def __init__(self, *lifespan: Callable[[FastAPI], AsyncContextManager] | K8sMetrix):
        # Update type to make it more generic to accept our test lifespans
        self.lifespan_stack: List[Callable[[FastAPI], AsyncContextManager]] = []
        for item in lifespan:
            if isinstance(item, K8sMetrix):
                logger.debug("[k8s-metrix|fastapi]: K8sMetrix instance detected, wrapping in lifespan context.")
                self.lifespan_stack.append(_lifespan(k8s_metrix=item))
            else:
                logger.debug("[k8s-metrix|fastapi]: Registering lifespan function.")
                self.lifespan_stack.append(item)


    def register(self, lifespan: Callable[[FastAPI], AsyncContextManager]):
        """
        Register a lifespan function with the FastAPI app.
        
        Args:
            lifespan: A callable that returns an AsyncContextManager when called with the app
        """
        self.lifespan_stack.append(lifespan)

    @asynccontextmanager
    async def __call__(self, app: FastAPI):
        """
        Start all registered lifespans when the FastAPI app starts.
        
        This method:
        1. Advances all registered lifespans to their first yield point
        2. Yields control back to FastAPI to run the application
        3. After the yield (when application is shutting down), executes the 
           remainder of each lifespan in reverse order (LIFO)
        """
        started_lifespans: List[AsyncContextManager] = []
        async with AsyncExitStack() as stack:
            for lifespan in self.lifespan_stack:
                if not callable(lifespan):
                    raise TypeError("Lifespan must be a callable that returns an AsyncContextManager")
                ctx = lifespan(app)
                started_lifespans.append(ctx)
                logger.debug(f"[k8s-metrix|fastapi]: Starting lifespan: {lifespan.__name__}")
                await stack.enter_async_context(ctx)
            logger.debug("[k8s-metrix|fastapi]: All lifespans started, yielding control to FastAPI.")
            yield
            logger.debug("[k8s-metrix|fastapi]: FastAPI is shutting down.")
            for ctx in reversed(started_lifespans):
                try:
                    logger.debug(f"[k8s-metrix|fastapi]: Shutting down lifespan: {ctx.gen}")
                    await ctx.__aexit__(None, None, None)
                except Exception as e:
                    logger.error(f"[k8s-metrix|fastapi]: Error during lifespan shutdown: {e}")
                else:
                    logger.debug(f"[k8s-metrix|fastapi]: Lifespan {ctx.gen} shutdown complete.")


if __name__ == "__main__":
    import asyncio
    import logging
    import uvicorn
    from contextlib import asynccontextmanager
    
    # Configure logging
    logging.basicConfig(
        level=logging.DEBUG, 
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # Create two sample lifespan functions
    @asynccontextmanager
    async def lifespan_a(app: FastAPI) -> AsyncGenerator[None, None]:
        logger.debug("Lifespan A: Starting up")
        # Simulate some startup work
        await asyncio.sleep(0.5)
        logger.debug("Lifespan A: Ready")
        yield
        logger.debug("Lifespan A: Shutting down")
        # Simulate some cleanup work
        await asyncio.sleep(0.5)
        logger.debug("Lifespan A: Cleanup complete")
    
    @asynccontextmanager
    async def lifespan_b(app: FastAPI) -> AsyncGenerator[None, None]:
        logger.debug("Lifespan B: Starting up")
        # Simulate some startup work
        await asyncio.sleep(0.3)
        logger.debug("Lifespan B: Ready")
        yield
        logger.debug("Lifespan B: Shutting down")
        raise Exception("Simulated error during shutdown")
        # Simulate some cleanup work
        await asyncio.sleep(0.3)
        logger.debug("Lifespan B: Cleanup complete")
    
    # Create a LifeSpanManager instance
    lifespan_manager = LifeSpanManager()
    app = FastAPI(lifespan=lifespan_manager)
    
    
    # Register both lifespans
    lifespan_manager.register(lifespan_a)
    lifespan_manager.register(lifespan_b)
    
    
    # Add a test endpoint
    @app.get("/")
    async def root():
        return {"message": "Hello from K8sMetrix test app"}
    
    # Run the app with uvicorn for testing
    logger.info("Starting test FastAPI app with K8sMetrix LifeSpanManager")
    
    # Run the server directly
    uvicorn.run(app, host="127.0.0.1", port=8000, log_level="debug")

