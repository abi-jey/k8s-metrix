from k8s_metrix.backends.base import BaseBackend
import os
from typing import List, Dict, Tuple
from typing import Set
from datetime import datetime
from logging import getLogger

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

    async def record(self, name: str, value: int) -> None:
        """
        Record a metric with the given name and value.

        Args:
            name (str): The name of the metric.
            value (int): The value of the metric.
        """
        if name not in self.metrics:
            self.metrics.add(name)
            os.makedirs(os.path.join(self.path, name), exist_ok=True)

        timestamp = datetime.now().isoformat()
        metric_file = os.path.join(self.path, name, "records.txt")
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
    
    async def retrieve(self, name: str) -> List[Tuple[datetime, int]]:
        """
        Retrieve a metric by its name.
        Args:
            name (str): The name of the metric.
        Returns:
            List[Tuple[datetime, int]]: A list of tuples containing the metric's timestamps and values.
        """
        metric_file = os.path.join(self.path, name, "records.txt")
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
        List all recorded metrics.
        Returns:
            List[str]: A list of all metric names.
        """
        return [d for d in os.listdir(self.path) if os.path.isdir(os.path.join(self.path, d))]
    
