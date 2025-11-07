"""Base classes for FlexLock backend integrations."""

from abc import ABC, abstractmethod
from typing import Any, List

class Job:
    """Abstract base class representing a submitted job."""
    @property
    def job_id(self) -> str:
        """The unique identifier for the job.""" 
        ...

class JobEnvironment:
    """Abstract base class providing environment information for a running job."""
    @property
    def global_rank(self) -> int:
        """The global rank of the current process within the job (0-indexed).""" 
        ...
    @property
    def world_size(self) -> int:
        """The total number of processes in the job.""" 
        ...

class Backend(ABC):
    """Abstract base class for FlexLock job submission backends."""
    @abstractmethod
    def submit(self, fn, *args, **kwargs) -> Job:
        """Submits a single function for execution.""" 
        ...

    @abstractmethod
    def environment(self) -> JobEnvironment:
        """Returns a JobEnvironment object providing environment-specific variables.""" 
        ...
