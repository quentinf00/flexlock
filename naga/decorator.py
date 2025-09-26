from functools import wraps
from .clicfg import clicfg
from .snapshot import snapshot
from .track_data import track_data
from .load_stage import load_stage
from .runlock import runlock
from .debug import unsafe_debug
from .mlflow_log import mlflow_log_run

def naga(
    snapshot_params: dict = {},
    track_data_params: list = None,
    load_stage_params: list = None,
    mlflow_log_params: dict = {},
    use_clicfg: bool = True,
    use_runlock: bool = True,
    use_debug: bool = True,
):
    """
    A master decorator that combines the functionality of all naga decorators.

    Args:
        snapshot_params (dict, optional): Parameters for the @snapshot decorator. 
            Defaults to {}.
        track_data_params (list, optional): A list of keys for the @track_data decorator.
            Example: ['data.raw', 'data.processed']. Defaults to None.
        load_stage_params (list, optional): A list of keys for the @load_stage decorator.
            Example: ['previous_stage_dir']. Defaults to None.
        mlflow_log_params (dict, optional): Parameters for the @mlflow_log_run decorator.
            Defaults to {}.
        use_clicfg (bool, optional): Whether to apply the @clicfg decorator. Defaults to True.
        use_runlock (bool, optional): Whether to apply the @runlock decorator. Defaults to True.
        use_debug (bool, optional): Whether to apply the @unsafe_debug decorator. Defaults to True.
    """
    def decorator(fn):
        # Apply decorators in reverse order of execution (inside-out)
        decorated_fn = fn

        if use_debug:
            decorated_fn = unsafe_debug(decorated_fn)

        if snapshot_params is not None:
            decorated_fn = snapshot(**snapshot_params)(decorated_fn)

        if load_stage_params:
            decorated_fn = load_stage(*load_stage_params)(decorated_fn)

        if track_data_params:
            decorated_fn = track_data(*track_data_params)(decorated_fn)

        
        if mlflow_log_params is not None:
            decorated_fn = mlflow_log_run(**mlflow_log_params, exec_fn_first=True)(decorated_fn)
        if use_runlock:
            decorated_fn = runlock(decorated_fn)

        if use_clicfg:
            decorated_fn = clicfg(decorated_fn)


        
        return decorated_fn

    return decorator
