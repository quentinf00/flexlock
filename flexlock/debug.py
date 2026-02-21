"""Debugging utilities for FlexLock."""

import os
import sys
from pathlib import Path
from typing import List, Dict, Any, Optional
from loguru import logger


def _is_notebook() -> bool:
    """Check if running in a Jupyter notebook or IPython environment."""
    try:
        from IPython import get_ipython

        ipython = get_ipython()
        if ipython is None:
            return False
        # Check if we're in a notebook (not just IPython terminal)
        if "IPKernelApp" in ipython.config:
            return True
        # Also check for Jupyter console
        return hasattr(ipython, "kernel")
    except (ImportError, AttributeError):
        return False


def _is_interactive_shell() -> bool:
    """Check if running in interactive Python shell (not notebook)."""
    try:
        from IPython import get_ipython

        ipython = get_ipython()
        if ipython is None:
            return False
        # IPython terminal (not notebook)
        return "IPKernelApp" not in ipython.config
    except (ImportError, AttributeError):
        # Check for regular python -i
        return hasattr(sys, "ps1")


def _is_boring_frame(filename: str) -> bool:
    """Check if frame is from stdlib, site-packages, or flexlock internals."""
    if not filename or filename == "<string>":
        return True

    try:
        p = Path(filename).resolve()
    except (OSError, ValueError):
        return True

    path_str = str(p)

    # Skip stdlib
    if path_str.startswith(sys.prefix):
        # But don't skip if it's in site-packages (that's checked next)
        if "site-packages" not in path_str:
            return True

    # Skip site-packages
    if "site-packages" in p.parts:
        return True

    # Skip flexlock itself (but not test code)
    if "flexlock" in p.parts and "test" not in path_str:
        # Check if it's actually the flexlock package
        for part in p.parts:
            if (
                part == "flexlock"
                and p.parts[p.parts.index(part) - 1] != "test_project"
            ):
                return True

    return False


def _is_project_frame(filename: str) -> bool:
    """Check if frame is from the current project (working directory)."""
    if not filename or filename == "<string>":
        return False

    try:
        p = Path(filename).resolve()
        cwd = Path.cwd().resolve()
        return p.is_relative_to(cwd)
    except (OSError, ValueError, RuntimeError):
        return False


def _score_frame(frame_info: Dict[str, Any]) -> int:
    """
    Score frame by 'interestingness'.

    Higher score = more interesting = more likely to be where you want to debug.
    """
    score = 0
    frame = frame_info["frame"]
    filename = frame_info["filename"]
    locals_dict = frame_info["locals"]

    # Project frames are much more interesting
    if _is_project_frame(filename):
        score += 1000

    # More locals = more interesting (but cap to avoid explosion)
    num_locals = len(locals_dict)
    score += min(num_locals * 10, 200)

    # Frames with data structures are more interesting
    for val in locals_dict.values():
        if isinstance(val, (list, dict, set)):
            score += 20
        elif isinstance(val, tuple) and len(val) > 2:
            score += 10

    # Frames with non-trivial local names (not just 'self', 'cls', '_')
    interesting_names = [
        name
        for name in locals_dict.keys()
        if not name.startswith("_") and name not in ("self", "cls")
    ]
    score += len(interesting_names) * 5

    # Penalize frames with very few locals (likely thin wrappers)
    if num_locals < 2:
        score -= 100

    return score


def _extract_frames(exc_info) -> List[Dict[str, Any]]:
    """
    Extract all frames from exception traceback, with metadata.

    Returns list of dicts with:
        - frame: The actual frame object
        - locals: Copy of frame locals
        - filename: Source file
        - function: Function name
        - lineno: Line number
        - score: Interest score
        - is_project: Whether it's in project code
        - is_boring: Whether it's stdlib/site-packages
    """
    tb = exc_info[2]
    frames = []

    while tb is not None:
        frame = tb.tb_frame

        # Get frame metadata
        filename = frame.f_code.co_filename
        function = frame.f_code.co_name
        lineno = tb.tb_lineno

        # Handle C extensions and frames without proper locals
        try:
            locals_dict = dict(frame.f_locals)  # Make a copy
        except (AttributeError, RuntimeError):
            # C extension or broken frame
            locals_dict = {}

        is_boring = _is_boring_frame(filename)
        is_project = _is_project_frame(filename)

        frame_info = {
            "frame": frame,
            "locals": locals_dict,
            "filename": filename,
            "function": function,
            "lineno": lineno,
            "is_project": is_project,
            "is_boring": is_boring,
            "score": 0,  # Will be scored later
        }

        # Score the frame
        frame_info["score"] = _score_frame(frame_info)

        frames.append(frame_info)
        tb = tb.tb_next

    return frames


def _select_default_frame(frames: List[Dict[str, Any]]) -> int:
    """
    Select the default frame to show.

    Strategy:
    1. If exception frame is in project → use it
    2. Else: Find deepest (last) project frame
    3. If no project frames: Use exception frame anyway

    Returns: Index into frames list
    """
    if not frames:
        return 0

    # Check if last frame (exception site) is in project
    last_idx = len(frames) - 1
    if frames[last_idx]["is_project"]:
        return last_idx

    # Find deepest project frame (iterate backwards)
    for i in range(len(frames) - 1, -1, -1):
        if frames[i]["is_project"]:
            return i

    # No project frames found - use exception frame
    logger.warning(
        "No project frames found in traceback. "
        "Exception may be in C extension or library code."
    )
    return last_idx


def _inject_notebook_debug(frames: List[Dict[str, Any]], default_idx: int):
    """
    Inject debug information into IPython/Jupyter notebook namespace.

    Provides:
    - Direct injection of default frame's locals
    - _debug_frames: All frames
    - _debug_current: Current frame index
    - _debug_up(), _debug_down(), _debug_goto(n): Navigation
    - _debug_show(): Show all frames
    """
    try:
        from IPython import get_ipython

        ipython = get_ipython()
        if ipython is None:
            logger.warning("Could not get IPython instance for debug injection")
            return
    except ImportError:
        logger.warning("IPython not available for debug injection")
        return

    # State for navigation
    state = {"current_idx": default_idx}

    def show_frames():
        """Show all available frames."""
        print("\n" + "=" * 70)
        print("Available frames (most recent call last):")
        print("=" * 70)
        for i, f in enumerate(frames):
            marker = "→" if i == state["current_idx"] else " "
            project_marker = "📁" if f["is_project"] else "  "
            boring_marker = "⚙️" if f["is_boring"] else "  "

            print(
                f"{marker} [{i:2d}] {project_marker}{boring_marker} "
                f"{f['function']}() at {Path(f['filename']).name}:{f['lineno']}"
            )

            if i == state["current_idx"]:
                # Show locals preview
                local_names = [k for k in f["locals"].keys() if not k.startswith("_")]
                if local_names:
                    preview = ", ".join(local_names[:5])
                    if len(local_names) > 5:
                        preview += f", ... ({len(local_names)} total)"
                    print(f"       Locals: {preview}")

        print("=" * 70)
        print("Legend: 📁=project code, ⚙️=library/stdlib, →=current frame")
        print("\nNavigation: _debug_up(), _debug_down(), _debug_goto(n), _debug_show()")
        print("=" * 70 + "\n")

    def inject_frame(idx: int):
        """Inject a specific frame's locals."""
        if not (0 <= idx < len(frames)):
            print(f"Invalid frame index: {idx} (valid: 0-{len(frames) - 1})")
            return

        state["current_idx"] = idx
        frame_info = frames[idx]

        # Inject locals into namespace
        ipython.user_ns.update(frame_info["locals"])

        # Update debug metadata
        ipython.user_ns["_debug_current"] = idx
        ipython.user_ns["_debug_frame_info"] = frame_info

        print(
            f"\n🔍 Injected frame [{idx}]: {frame_info['function']}() "
            f"at {Path(frame_info['filename']).name}:{frame_info['lineno']}"
        )

        local_names = [k for k in frame_info["locals"].keys() if not k.startswith("_")]
        if local_names:
            print(f"   Available: {', '.join(local_names[:10])}")
            if len(local_names) > 10:
                print(f"              ... and {len(local_names) - 10} more")

    def debug_up():
        """Move to caller frame (up the stack)."""
        new_idx = state["current_idx"] - 1
        if new_idx < 0:
            print("Already at top of stack")
            return
        inject_frame(new_idx)

    def debug_down():
        """Move to callee frame (down the stack, toward exception)."""
        new_idx = state["current_idx"] + 1
        if new_idx >= len(frames):
            print("Already at bottom of stack (exception site)")
            return
        inject_frame(new_idx)

    def debug_goto(idx: int):
        """Jump to specific frame."""
        inject_frame(idx)

    # Inject navigation functions
    ipython.user_ns["_debug_frames"] = frames
    ipython.user_ns["_debug_show"] = show_frames
    ipython.user_ns["_debug_up"] = debug_up
    ipython.user_ns["_debug_down"] = debug_down
    ipython.user_ns["_debug_goto"] = debug_goto

    # Inject default frame
    logger.info("Injecting debug locals into notebook namespace...")
    inject_frame(default_idx)

    # Show quick help
    print("\n💡 Debug Mode: Use _debug_show() to see all frames")


def _handle_exception_debug(exc_info):
    """
    Handle exception for debugging based on environment.

    - Notebook: Inject locals with navigation
    - Interactive shell: Inject locals (no navigation, use pdb if needed)
    - Script: Drop into PDB post-mortem
    """
    # Get configuration
    strategy = os.environ.get("FLEXLOCK_DEBUG_STRATEGY", "auto").lower()

    logger.debug(f"Debug strategy: {strategy}")
    # Extract frames
    frames = _extract_frames(exc_info)
    logger.debug(f"Extracted {len(frames)} frames for debugging")
    if not frames:
        logger.warning("No frames found in traceback")
        return

    # Select default frame
    default_idx = _select_default_frame(frames)
    logger.debug(f"Default debug frame index: {default_idx}")

    # Determine behavior
    in_notebook = _is_notebook()
    in_shell = _is_interactive_shell()
    logger.debug(
        f"Detected environment - Notebook: {in_notebook}, Interactive Shell: {in_shell}"
    )

    if strategy == "pdb":
        # Force PDB
        import pdb

        pdb.post_mortem(exc_info[2])
    elif strategy == "inject":
        # Force injection (even in script)
        if in_notebook or in_shell:
            _inject_notebook_debug(frames, default_idx)
        else:
            logger.warning("Cannot inject in non-interactive environment")
    else:  # 'auto'
        if in_notebook:
            # Notebook: Inject with navigation
            logger.info("In notebook - injecting locals with navigation.")
            _inject_notebook_debug(frames, default_idx)
        elif in_shell:
            # Interactive shell: Inject or PDB
            logger.info(
                "In interactive shell - injecting locals. Use pdb.post_mortem() for debugger."
            )
            _inject_notebook_debug(frames, default_idx)
        else:
            # Script: PDB
            logger.info("Dropping into PDB post-mortem debugger...")
            import pdb

            pdb.post_mortem(exc_info[2])


def debug_on_fail(fn=None):
    """
    A decorator that provides enhanced debugging on exception.

    Features:
    - Smart frame selection (prefers project code over libraries)
    - Frame navigation in notebooks (_debug_up, _debug_down, _debug_goto)
    - Handles C extensions gracefully
    - PDB post-mortem for scripts
    - Configurable via environment variables

    Environment Variables:
        FLEXLOCK_DEBUG: Set to '1' or 'true' to enable (via runner or manually)
        FLEXLOCK_NODEBUG: Set to '1' or 'true' to disable
        FLEXLOCK_DEBUG_STRATEGY: 'auto' (default), 'pdb', or 'inject'

    Args:
        fn: The function to decorate. If None, returns a decorator.
        stack_depth: DEPRECATED - kept for backward compatibility

    Usage:
        @debug_on_fail
        def my_function():
            ...

        # Or with explicit call:
        debug_on_fail(my_function)()

    In notebooks after exception:
        - Locals from relevant frame are injected
        - _debug_show(): Show all frames
        - _debug_up(): Move to caller
        - _debug_down(): Move toward exception
        - _debug_goto(n): Jump to frame n
    """

    def decorator(fn):
        # Check if debug is disabled
        flexlock_nodebug = os.environ.get("FLEXLOCK_NODEBUG", "false").lower() in (
            "1",
            "true",
        )

        if flexlock_nodebug:
            return fn

        def _fn(*args, **kwargs):
            try:
                return fn(*args, **kwargs)
            except Exception:
                exc_info = sys.exc_info()

                # Log exception
                logger.error(
                    f"Exception in {fn.__name__}(): {exc_info[1]}",
                    exc_info=False,  # Don't double-log traceback
                )

                # Handle debug
                try:
                    _handle_exception_debug(exc_info)
                except Exception as debug_err:
                    logger.error(f"Error in debug handler: {debug_err}")
                finally:
                    # Clean up to avoid reference cycles
                    del exc_info

                # Re-raise original exception
                raise

        return _fn

    # Support both @debug_on_fail and @debug_on_fail(stack_depth=2) usage
    return decorator(fn)
