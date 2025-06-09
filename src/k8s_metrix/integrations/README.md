# FastAPI Integration for K8s-Metrix

This module provides a FastAPI integration for the K8s-Metrix library. It includes tools for:

1. Exposing metrics via a FastAPI endpoint
2. Managing lifespan of K8s-Metrix and other services with FastAPI's application lifecycle

## Basic Usage

```python
from fastapi import FastAPI
from k8s_metrix import K8sMetrix
from k8s_metrix.integrations.fastapi import configure

app = FastAPI()
metrix = K8sMetrix(backend="fs")

# Configure metrics endpoint
configure(app, metrix)

# Start your FastAPI app normally
```

## Advanced Usage with Lifespan Management

For proper startup and shutdown of K8s-Metrix with your FastAPI application:

```python
from fastapi import FastAPI
from k8s_metrix import K8sMetrix
from k8s_metrix.integrations.fastapi import configure_with_lifespan

app = FastAPI()
metrix = K8sMetrix(backend="fs")

# Configure FastAPI with K8sMetrix and lifespan management
app = configure_with_lifespan(app, metrix, use_modern_lifespan=True)

# K8sMetrix will automatically start when FastAPI starts
# and properly shut down when FastAPI stops
```

## Custom Lifespan Management

For more control over the lifespan of multiple services:

```python
from fastapi import FastAPI
from k8s_metrix import K8sMetrix
from k8s_metrix.integrations.fastapi import LifeSpanManager, create_k8s_metrix_lifespan
from contextlib import AsyncExitStack

app = FastAPI()
metrix = K8sMetrix(backend="fs")

# Create lifespan manager
lifespan_manager = LifeSpanManager()

# Register K8sMetrix lifespan
create_k8s_metrix_lifespan(metrix, lifespan_manager)

# Configure metrics endpoint
@app.get("/metrics")
async def metrics():
    return metrix.expose_metrics()

# Register custom lifespans for other services
async def database_lifespan(app):
    # Initialize database connection
    print("Database connected")
    
    # Yield control back to FastAPI
    yield
    
    # Cleanup after application shuts down
    print("Database disconnected")

# Register the custom lifespan
lifespan_manager.register(database_lifespan)

# Set up lifespan using modern approach
@app.lifespan
async def lifespan(app):
    async with AsyncExitStack() as stack:
        await lifespan_manager._startup(app)
        yield
        await lifespan_manager._shutdown()
```

The `LifeSpanManager` class manages the startup and shutdown of all registered lifespans, ensuring they are processed in the correct order.
