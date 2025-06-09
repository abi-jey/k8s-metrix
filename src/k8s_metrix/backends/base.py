from abc import ABC, abstractmethod
from typing import Any, Dict, List, Tuple
from datetime import datetime

class BaseBackend(ABC):
    """
    Base class for all backend implementations.
    This class defines the interface that all backends must implement.
    """

    @abstractmethod
    async def record(self, name: str, value: int) -> None:
        """
        Record a metric with the given name and value.
        Args:
            name (str): The name of the metric.
            value (int): The value of the metric.
        """
        raise NotImplementedError("This method should be implemented in subclasses.")


    @abstractmethod
    async def retrieve(self, name: str) -> List[Tuple[datetime, int]]:
        """
        Retrieve a metric by its name.
        Args:
            name (str): The name of the metric.
        Returns:
            List[Tuple[datetime, int]]: A list of tuples containing the metric's timestamps and values.
        """
        raise NotImplementedError("This method should be implemented in subclasses.")


    @abstractmethod
    async def list_all_metrics(self) -> List[str]:
        """
        List all recorded metrics.
        Returns:
            List[str]: A list of all metric names.
        """
        raise NotImplementedError("This method should be implemented in subclasses.")

    @abstractmethod
    async def init_backend(self) -> None:
        """
        Initialize the backend.
        This method is called when the K8sMetrix instance starts.
        """
        raise NotImplementedError("This method should be implemented in subclasses.")
