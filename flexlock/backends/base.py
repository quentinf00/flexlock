# flexlock/backends/base.py
from abc import ABC, abstractmethod
from typing import Any, List

class Job:
    @property
    def job_id(self) -> str: ...

class JobEnvironment:
    @property
    def global_rank(self) -> int: ...
    @property
    def world_size(self) -> int: ...

class Backend(ABC):
    @abstractmethod
    def submit(self, fn, *args, **kwargs) -> Job: ...

    @abstractmethod
    def environment(self) -> JobEnvironment: ...
