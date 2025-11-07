"""Debugging utilities for FlexLock."""

import os
import sys
from loguru import logger


def debug_on_fail(fn=None, *, stack_depth=1):
    """
    A decorator that, upon exception, injects the failed function's
    local variables into the caller's frame.

    Args:
        fn: The function to decorate. If None, returns a decorator.
        stack_depth: How many frames up to inject locals (default 1, 0 would be the current frame).
                    Use 2 to inject into the main calling context when used inside flexcli wrapper.

    This decorator is only active if the environment variable FLEXLOCK_DEBUG is set to '1' or 'true'.

    WARNING: This is an advanced and potentially dangerous pattern.
    Modifying a caller's locals can lead to unpredictable and hard-to-debug code.
    """

    def decorator(fn):
        flexlock_debug = os.environ.get("FLEXLOCK_DEBUG", "false").lower() in (
            "1",
            "true",
        )

        if not flexlock_debug:
            return fn

        def _fn(*args, **kwargs):
            try:
                return fn(*args, **kwargs)
            except Exception:
                # Get the local variables from the frame where the exception was raised
                exc_type, exc_value, traceback = sys.exc_info()

                # The frame where the exception occurred
                exception_frame = traceback.tb_next.tb_frame
                fn_locals = exception_frame.f_locals

                logger.debug(
                    f"--- FLEXLOCK_DEBUG: An exception occurred in {fn.__name__}: {exc_value} ---",
                    file=sys.stderr,
                )
                logger.debug(
                    f"--- FLEXLOCK_DEBUG: Locals in '{fn.__name__}' at time of error: {list(fn_locals)} ---",
                    file=sys.stderr,
                )

                # Update the locals of the caller function at specified stack depth
                try:
                    # sys._getframe(n) gets the frame n levels up the stack
                    caller_frame = sys._getframe(stack_depth)
                    caller_frame.f_locals.update(fn_locals)
                    logger.debug(
                        f"--- FLEXLOCK_DEBUG: Injected locals into '{caller_frame.f_code.co_name}'. ---",
                        file=sys.stderr,
                    )
                finally:
                    # It is crucial to delete frame references to avoid reference cycles
                    del traceback, exception_frame, caller_frame

                raise

        return _fn

    # Support both @debug_on_fail and @debug_on_fail(stack_depth=2) usage
    if fn is None:
        # Called as @debug_on_fail(stack_depth=2)
        return decorator
    else:
        # Called as @debug_on_fail
        return decorator(fn)
