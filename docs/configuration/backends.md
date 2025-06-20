# Backend Configuration

k8s-metrix supports multiple storage backends for metric data. This page covers the available backends and 
their configuration options.

## Available Backends

### Filesystem Backend

The filesystem backend stores metrics in a structured directory format on the local filesystem.

**Status**: ✅ **Available**

#### Configuration

```python
from k8s_metrix import K8sMetrix

# Use filesystem backend (default)
metrix = K8sMetrix(backend="fs")
```

#### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `METRIX_BACKEND` | Backend type | `"fs"` |

#### Storage Structure

```
metrix_data/
├── service/
│   └── {namespace}/
│       └── {service_name}/
│           └── {metric_name}/
│               └── records.txt
└── pod/
    └── {namespace}/
        └── {pod_name}/
            └── {metric_name}/
                └── records.txt
```

#### Advantages
- ✅ No external dependencies
- ✅ Simple setup and debugging
- ✅ Persistent across restarts
- ✅ Human-readable storage format

#### Limitations
- ⚠️ Not suitable for multi-instance deployments
- ⚠️ Performance limited by disk I/O
- ⚠️ No built-in data retention policies

### Redis Backend

The Redis backend provides high-performance in-memory storage with optional persistence.

**Status**: 🚧 **Planned** (Coming in v0.2.0)

#### Planned Configuration

```python
from k8s_metrix import K8sMetrix

# Use Redis backend (planned)
metrix = K8sMetrix(
    backend="redis",
    redis_url="redis://localhost:6379",
    redis_db=0
)
```

#### Planned Features
- 🚧 High-performance in-memory storage
- 🚧 Multi-instance support with shared state
- 🚧 Built-in data expiration and cleanup
- 🚧 Optional persistence to disk
- 🚧 Clustering support

## Backend Selection Guide

Choose the appropriate backend based on your deployment requirements:

### Use Filesystem Backend When:
- Single-instance deployments
- Development and testing
- Simple setups without external dependencies
- Persistent storage is required
- Human-readable debug output is helpful

### Use Redis Backend When: *(Available in v0.2.0)*
- Multi-instance deployments
- High-throughput metrics collection
- Shared state across multiple adapter instances
- Advanced data management features needed
- Scalability is a primary concern

## Custom Backend Development

You can create custom backends by implementing the `BaseBackend` interface:

```python
from k8s_metrix.backends.base import BaseBackend
from typing import List, Dict, Tuple
from datetime import datetime

class CustomBackend(BaseBackend):
    async def record(self, name: str, value: float, service: str = "", 
                    pod: str = "", namespace: str = "") -> None:
        # Implement metric recording logic
        pass
    
    async def retrieve(self, name: str, service: str = "", pod: str = "", 
                      namespace: str = "") -> Dict[str, List[Tuple[datetime, int]]]:
        # Implement metric retrieval logic
        pass
    
    async def list_all_metrics(self) -> List[str]:
        # Implement metric listing logic
        pass
    
    async def init_backend(self) -> None:
        # Implement backend initialization
        pass
```

## Performance Considerations

### Filesystem Backend
- **Read Performance**: O(n) where n is the number of records
- **Write Performance**: O(1) append operations
- **Memory Usage**: Low, data stored on disk
- **Scalability**: Limited to single instance

### Redis Backend *(Planned)*
- **Read Performance**: O(1) for recent values, O(log n) for ranges
- **Write Performance**: O(1) for all operations
- **Memory Usage**: Higher, data stored in RAM
- **Scalability**: Excellent with clustering support

## Data Retention

### Filesystem Backend
Currently, the filesystem backend does not implement automatic data retention. You can implement custom 
cleanup scripts or use system-level tools like `logrotate`.

### Redis Backend *(Planned)*
Will support built-in TTL (Time To Live) settings for automatic data expiration.

## Migration Between Backends

When migrating between backends, consider:

1. **Data Export**: Export existing metrics before switching
2. **Downtime**: Plan for brief service interruption during migration
3. **Testing**: Validate new backend thoroughly before production use
4. **Rollback Plan**: Keep backup of original data for emergency rollback
