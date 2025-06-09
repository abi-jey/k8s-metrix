from k8s_metrix.backends.base import BaseBackend
import os
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

    async def record(self, name: str, value: int, service: str = "", pod: str = "", namespace: str = ""):
        """
        Record a metric with the given name and value.

        Args:
            name (str): The name of the metric.
            value (int): The value of the metric.
            service (str): The service name (optional).
            pod (str): The pod name (optional).
            namespace (str): The namespace (optional).
        """
        # Determine the metric path based on whether it's for a service or pod
        if service and namespace:
            # Format: service/namespace/service_name/metric_name/
            metric_path = os.path.join(self.path, "service", namespace, service, name)
        elif pod and namespace:
            # Format: pod/namespace/pod_name/metric_name/
            metric_path = os.path.join(self.path, "pod", namespace, pod, name)
        else:
            # Fallback to structured format for backward compatibility
            metric_path = os.path.join(self.path, "no_resource_type", "no_namespace", "no_instance", name)
        
        # Create the directory structure if it doesn't exist
        os.makedirs(metric_path, exist_ok=True)
        
        # Add to metrics set for tracking
        if service and namespace:
            metric_key = f"service/{namespace}/{service}/{name}"
        elif pod and namespace:
            metric_key = f"pod/{namespace}/{pod}/{name}"
        else:
            metric_key = f"no_resource_type/no_namespace/no_instance/{name}"
        self.metrics.add(metric_key)

        timestamp = datetime.now().isoformat()
        metric_file = os.path.join(metric_path, "records.txt")
        with open(metric_file, 'a') as f:
            f.write(f"{timestamp}:{value}\n")

    def init_path(self):
        """
        Initialize the path for storing metrics.
        """
        path = os.path.abspath(self.path)
        if not os.path.exists(path):
            os.makedirs(path)
        if not os.path.isdir(path):
            raise ValueError(f"Path {path} is not a directory, please provide a remove or select a different path.")
        if not os.access(path, os.W_OK):
            raise ValueError(f"Path {path} is not writable, make sure user {os.getuid()} has write permissions.")
        logger.debug(f"[k8s-metrix]: Path initialized: {path}")
        self.path = path

    async def retrieve(self, name: str, service: str = "", pod: str = "", namespace: str = "") -> List[Tuple[datetime, int]]:
        """
        Retrieve a metric by its name.
        Args:
            name (str): The name of the metric.
            service (str): The service name (optional).
            pod (str): The pod name (optional).
            namespace (str): The namespace (optional).
        Returns:
            List[Tuple[datetime, int]]: A list of tuples containing the metric's timestamps and values.
        """
        # Determine the metric path based on whether it's for a service or pod
        if service and namespace:
            # Format: service/namespace/service_name/metric_name/
            metric_file = os.path.join(self.path, "service", namespace, service, name, "records.txt")
        elif pod and namespace:
            # Format: pod/namespace/pod_name/metric_name/
            metric_file = os.path.join(self.path, "pod", namespace, pod, name, "records.txt")
        else:
            # Fallback to structured format for backward compatibility
            metric_file = os.path.join(self.path, "no_resource_type", "no_namespace", "no_instance", name, "records.txt")
            
        if not os.path.exists(metric_file):
            return []

        records = []
        with open(metric_file, 'r') as f:
            for line in f:
                timestamp, value = line.strip().split(':', maxsplit=1)
                records.append((datetime.fromisoformat(timestamp), int(value)))
        return records
    
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
        if not os.path.exists(self.path):
            return
        
        # Check for fallback structure (no_resource_type/no_namespace/no_instance)
        fallback_path = os.path.join(self.path, "no_resource_type", "no_namespace", "no_instance")
        if os.path.exists(fallback_path):
            for metric in os.listdir(fallback_path):
                metric_path = os.path.join(fallback_path, metric)
                if os.path.isdir(metric_path):
                    self.metrics.add(f"no_resource_type/no_namespace/no_instance/{metric}")
        
        # Check for service structure
        service_path = os.path.join(self.path, "service")
        if os.path.exists(service_path):
            for namespace in os.listdir(service_path):
                namespace_path = os.path.join(service_path, namespace)
                if os.path.isdir(namespace_path):
                    for service_name in os.listdir(namespace_path):
                        service_dir = os.path.join(namespace_path, service_name)
                        if os.path.isdir(service_dir):
                            for metric in os.listdir(service_dir):
                                metric_path = os.path.join(service_dir, metric)
                                if os.path.isdir(metric_path):
                                    self.metrics.add(f"service/{namespace}/{service_name}/{metric}")
        
        # Check for pod structure
        pod_path = os.path.join(self.path, "pod")
        if os.path.exists(pod_path):
            for namespace in os.listdir(pod_path):
                namespace_path = os.path.join(pod_path, namespace)
                if os.path.isdir(namespace_path):
                    for pod_name in os.listdir(namespace_path):
                        pod_dir = os.path.join(namespace_path, pod_name)
                        if os.path.isdir(pod_dir):
                            for metric in os.listdir(pod_dir):
                                metric_path = os.path.join(pod_dir, metric)
                                if os.path.isdir(metric_path):
                                    self.metrics.add(f"pod/{namespace}/{pod_name}/{metric}")
        
        logger.debug(f"[k8s-metrix]: Loaded {len(self.metrics)} metrics from filesystem")

