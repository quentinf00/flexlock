import os
import sys

def debug_on_fail(fn):
    """
    A decorator that, upon exception, injects the failed function's
    local variables into the caller's frame.

    This decorator is only active if the environment variable FLEXLOCK_DEBUG is set to '1' or 'true'.

    WARNING: This is an advanced and potentially dangerous pattern.
    Modifying a caller's locals can lead to unpredictable and hard-to-debug code.
    """
    flexlock_debug = os.environ.get('FLEXLOCK_DEBUG', 'false').lower() in ('1', 'true')

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
            
            print(f"--- FLEXLOCK_DEBUG: An exception occurred in {fn.__name__}: {exc_value} ---", file=sys.stderr)
            print(f"--- FLEXLOCK_DEBUG: Locals in '{fn.__name__}' at time of error: {fn_locals} ---", file=sys.stderr)

            # Update the locals of the caller function
            try:
                # sys._getframe(1) gets the frame of the function that called this wrapper
                caller_frame = sys._getframe(1)
                caller_frame.f_locals.update(fn_locals)
                print(f"--- FLEXLOCK_DEBUG: Injected locals into '{caller_frame.f_code.co_name}'. ---", file=sys.stderr)
            finally:
                # It is crucial to delete frame references to avoid reference cycles
                del traceback, exception_frame, caller_frame
            
            raise

    return _fn
