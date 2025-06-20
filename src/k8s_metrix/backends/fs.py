from k8s_metrix.backends.base import BaseBackend
import os
from pathlib import Path
from typing import List, Dict, Tuple
from typing import Set
from datetime import datetime
from logging import getLogger
from typing import Any

logger = getLogger(__name__)

class FsBackend(BaseBackend):
    """
    File System backend for K8sMetrix.
    This backend stores metrics in a file system.
    How it works:
    1. Metrics are stored in a directory specified by the `path` parameter.
    2. Each metric is recorded in it's own folder named after the metric.

    """

    def __init__(self, path: str="./metrics"):
        """
        Initialize the FsBackend instance.

        Args:
            path (str): The path to the directory where metrics will be stored.
        """
        logger.debug(f"[k8s-metrix]: Initializing FsBackend with path: {path}")
        self.path = path
        self.metrics: Set[str] = set()
        self._metrics_loaded = False  # Flag to track if metrics have been loaded from filesystem


    async def init_backend(self):
        """
        Initialize the backend.
        This method is a placeholder and should be implemented in subclasses.
        """
        logger.debug(f"[k8s-metrix]: Initializing FsBackend.")
        self.init_path()
        logger.debug(f"[k8s-metrix]: FsBackend initialized with path: {self.path}")

    async def start(self):
        """
        Start the FsBackend instance.
        This method is a placeholder and should be implemented in subclasses.
        """
        await self.init_backend()
        logger.debug(f"[k8s-metrix]: FsBackend startup complete")

    async def record(self, name: str, value: float, service: str = "", pod: str = "", namespace: str = ""):
        """
        Record a metric with the given name and value.

        Args:
            name (str): The name of the metric.
            value (int): The value of the metric.
            service (str): The service name (optional).
            pod (str): The pod name (optional).
            namespace (str): The namespace (optional).
        """
        base_path = Path(self.path)
        
        # Determine the metric path based on whether it's for a service or pod
        if pod and namespace:
            # Format: pod/namespace/pod_name/metric_name/
            metric_path = base_path / "pod" / namespace / pod / name
        elif service and namespace:
            # Format: service/namespace/service_name/metric_name/
            metric_path = base_path / "service" / namespace / service / name
        else:
            # Fallback to structured format for backward compatibility
            metric_path = base_path / "no_resource_type" / "no_namespace" / "no_instance" / name
        
        # Create the directory structure if it doesn't exist
        metric_path.mkdir(parents=True, exist_ok=True)
        
        # Add to metrics set for tracking
        if service and namespace:
            metric_key = f"service/{namespace}/{service}/{name}"
        elif pod and namespace:
            metric_key = f"pod/{namespace}/{pod}/{name}"
        else:
            metric_key = f"no_resource_type/no_namespace/no_instance/{name}"
        self.metrics.add(metric_key)

        timestamp = datetime.now().isoformat()
        metric_file = metric_path / "records.txt"
        with metric_file.open('a') as f:
            f.write(f"{timestamp}:{value}\n")

    async def get_metric_value(self, name: str, service: str = "", pod: str = "", namespace: str = "") -> int:
        """
        Get the latest value of a metric by its name.
        
        Args:
            name (str): The name of the metric.
            service (str): The service name (optional).
            pod (str): The pod name (optional).
            namespace (str): The namespace (optional).
        
        Returns:
            int: The latest value of the metric, or None if not found.
        """
        records_dict = await self.retrieve(name, service, pod, namespace)
        
        # Get the latest record from any resource
        latest_value = None
        latest_timestamp = None
        
        for resource_name, records in records_dict.items():
            if records:
                # Get the latest record for this resource
                latest_record = records[-1]
                if latest_timestamp is None or latest_record[0] > latest_timestamp:
                    latest_timestamp = latest_record[0]
                    latest_value = latest_record[1]
        
        return latest_value if latest_value is not None else 0

    def init_path(self):
        """
        Initialize the path for storing metrics.
        """
        path = Path(self.path).resolve()
        if not path.exists():
            path.mkdir(parents=True, exist_ok=True)
        if not path.is_dir():
            raise ValueError(f"Path {path} is not a directory, please provide a remove or select a different path.")  # fmt: skip
        if not os.access(path, os.W_OK):
            raise ValueError(f"Path {path} is not writable, make sure user {os.getuid()} has write permissions.")  # fmt: skip
        logger.debug(f"[k8s-metrix]: Path initialized: {path}")
        self.path = str(path)

    async def retrieve(self, name: str, service: str = "", pod: str = "", namespace: str = "") -> Dict[str, List[Tuple[datetime, int]]]:
        """
        Retrieve a metric by its name with wildcard support.
        Args:
            name (str): The name of the metric.
            service (str): The service name (optional), can be wildcarded with "*".
            pod (str): The pod name (optional), can be wildcarded with "*".
            namespace (str): The namespace (optional).
        Returns:
            Dict[str, List[Tuple[datetime, int]]]: A dictionary with resource names as keys and 
                                                   lists of metric records as values.
        """
        result = {}
        base_path = Path(self.path)
        
        if pod and namespace:
            # Find all pods across all services
            pod_base = base_path / "pod" / namespace
            if pod_base.exists():
                if pod == "*":
                    dirs = list(pod_base.glob("*"))
                else:
                    dirs = [pod_base / pod]
                for pod_dir in dirs:
                    if pod_dir.is_dir():
                        records = self._read_metric_file(pod_dir / name / "records.txt")
                        if records:
                            result[pod_dir.name] = records
        elif service and namespace:
            # Handle service metrics - check if there are service-level metrics
            service_base = base_path / "service" / namespace
            if service == "*":
                dirs = list(service_base.glob("*"))
            else:
                dirs = [service_base / service]
            for service_dir in dirs:
                if service_dir.is_dir():
                    records = self._read_metric_file(service_dir / name / "records.txt")
                    if records:
                        result[service_dir.name] = records
        else:
            # Fallback to structured format for backward compatibility
            fallback_path = base_path / "no_resource_type" / "no_namespace" / "no_instance" / name / "records.txt"
            records = self._read_metric_file(fallback_path)
            if records:
                result["no_instance"] = records
                    
        return result
    
    async def list_all_metrics(self) -> List[str]:
        """
        List all recorded metrics using the cached metrics set for efficiency.
        On first call, loads metrics from filesystem. Subsequent calls use cached set.
        Returns:
            List[str]: A list of all metric keys.
        """
        if not self._metrics_loaded:
            await self._load_metrics_from_filesystem()
            self._metrics_loaded = True
        return list(self.metrics)

    async def list_service_metrics(self, namespace: str = "", service: str = "") -> List[str]:
        """
        List all metrics for services using the cached metrics set for efficiency.
        Args:
            namespace (str): Filter by namespace (optional).
            service (str): Filter by service name (optional).
        Returns:
            List[str]: A list of service metric paths.
        """
        if not self._metrics_loaded:
            await self._load_metrics_from_filesystem()
            self._metrics_loaded = True
            
        metrics = []
        for metric_key in self.metrics:
            if metric_key.startswith("service/"):
                parts = metric_key.split("/")
                if len(parts) >= 4:  # service/namespace/service_name/metric_name
                    metric_namespace = parts[1]
                    metric_service = parts[2]
                    
                    # Apply filters
                    if namespace and metric_namespace != namespace:
                        continue
                    if service and metric_service != service:
                        continue
                        
                    metrics.append(metric_key)
        
        return metrics

    async def list_pod_metrics(self, namespace: str = "", pod: str = "") -> List[str]:
        """
        List all metrics for pods using the cached metrics set for efficiency.
        Args:
            namespace (str): Filter by namespace (optional).
            pod (str): Filter by pod name (optional).
        Returns:
            List[str]: A list of pod metric paths.
        """
        if not self._metrics_loaded:
            await self._load_metrics_from_filesystem()
            self._metrics_loaded = True
            
        metrics = []
        for metric_key in self.metrics:
            if metric_key.startswith("pod/"):
                parts = metric_key.split("/")
                if len(parts) >= 4:  # pod/namespace/pod_name/metric_name
                    metric_namespace = parts[1]
                    metric_pod = parts[2]
                    
                    # Apply filters
                    if namespace and metric_namespace != namespace:
                        continue
                    if pod and metric_pod != pod:
                        continue
                        
                    metrics.append(metric_key)
        
        return metrics

    async def _load_metrics_from_filesystem(self):
        """
        Load existing metrics from the filesystem into the metrics set.
        This is called once on the first list operation to populate the cache.
        """
        base_path = Path(self.path)
        if not base_path.exists():
            return
        
        # Check for fallback structure (no_resource_type/no_namespace/no_instance)
        fallback_path = base_path / "no_resource_type" / "no_namespace" / "no_instance"
        if fallback_path.exists():
            for metric_dir in fallback_path.iterdir():
                if metric_dir.is_dir():
                    self.metrics.add(f"no_resource_type/no_namespace/no_instance/{metric_dir.name}")
        
        # Check for service structure
        service_path = base_path / "service"
        if service_path.exists():
            for namespace_dir in service_path.iterdir():
                if namespace_dir.is_dir():
                    for service_dir in namespace_dir.iterdir():
                        if service_dir.is_dir():
                            for metric_dir in service_dir.iterdir():
                                if metric_dir.is_dir():
                                    metric_key = f"service/{namespace_dir.name}/{service_dir.name}/{metric_dir.name}"  # fmt: skip
                                    self.metrics.add(metric_key)
        
        # Check for pod structure
        pod_path = base_path / "pod"
        if pod_path.exists():
            for namespace_dir in pod_path.iterdir():
                if namespace_dir.is_dir():
                    for pod_dir in namespace_dir.iterdir():
                        if pod_dir.is_dir():
                            for metric_dir in pod_dir.iterdir():
                                if metric_dir.is_dir():
                                    metric_key = f"pod/{namespace_dir.name}/{pod_dir.name}/{metric_dir.name}"  # fmt: skip
                                    self.metrics.add(metric_key)
        
        logger.debug(f"[k8s-metrix]: Loaded {len(self.metrics)} metrics from filesystem")

    def _read_metric_file(self, metric_file_path: Path) -> List[Tuple[datetime, int]]:
        """
        Read metric records from a metric file.
        Args:
            metric_file_path (Path): The path to the metric file.
        Returns:
            List[Tuple[datetime, int]]: A list of metric records.
        """
        if not metric_file_path.exists():
            return []

        records = []
        try:
            with metric_file_path.open('r') as f:
                for line in f:
                    line = line.strip()
                    if line:
                        timestamp_str, value_str = line.rsplit(':', 1)
                        records.append((datetime.fromisoformat(timestamp_str), float(value_str)))
        except (ValueError, OSError) as e:
            logger.error(f"Error reading metric file {metric_file_path}: {e}")
            return []
        
        return records

