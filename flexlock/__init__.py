"""FlexLock: A lightweight library for reproducible ML experiments."""

from loguru import logger
logger.disable("flexlock")

from .flexcli import flexcli
from .snapshot import snapshot
from .mlflowlink import mlflowlink
from .debug import debug_on_fail
from .resolvers import register_resolvers

# Register OmegaConf resolvers when the library is imported
register_resolvers()

__all__ = [
    "flexcli",
    "snapshot",
    "mlflowlink",
    "debug_on_fail",
]
