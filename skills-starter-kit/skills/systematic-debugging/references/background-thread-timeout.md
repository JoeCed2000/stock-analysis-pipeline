# Background Thread Timeout Pattern

## Symptom

A FastAPI background thread (spawned via `threading.Thread`) hangs. The status endpoint
shows `"running"` forever. No error is returned because the thread never finishes.

**Example:** Wiki builder scanning a large project on NTFS — thread blocks on I/O,
status stays "running" indefinitely.

## Root Cause

`threading.Thread(target=worker, daemon=True).start()` has no timeout mechanism.
If `worker()` blocks (I/O, deadlock, infinite loop), nothing will ever transition
the state back to "done" or "error".

## Fix Pattern: Watcher Thread with join() timeout

Wrap the worker in a **watcher thread** that `join()`s with a timeout:

```python
import threading
import time

_WIKI_BUILD_TIMEOUT = 300  # seconds

def _run_with_timeout():
    build_thread = threading.Thread(target=_run)
    build_thread.start()
    build_thread.join(timeout=_WIKI_BUILD_TIMEOUT)
    if build_thread.is_alive():
        with _wiki_lock:
            _wiki_build_state["status"] = "done"
            _wiki_build_state["error"] = f"Build timed out after {_WIKI_BUILD_TIMEOUT}s — may still be running"

# Outer daemon thread spawns the watcher
threading.Thread(target=_run_with_timeout, daemon=True).start()
```

### Key properties

- The outer thread is daemon=True — won't block app shutdown
- The watcher `join(timeout=N)` blocks at most N seconds
- If `build_thread.is_alive()` after timeout, we gracefully transition state
- The hung thread continues running (daemon=True on the outer, but the build thread itself is NOT daemon — it WILL keep running but the state is correctly marked)
- The status endpoint now shows elapsed time: `state["elapsed"] = round(time.time() - state["started_at"], 1)` — users can see how long it's been running

### Required state additions

```python
_wiki_build_state: dict = {
    "status": "idle",    # idle|running|done
    "result": None,      # build result on success
    "error": None,       # error string on failure or timeout
    "started_at": None,  # time.time() when build was triggered
}
```

## Bonus: Status endpoint enrichment

When status is "running", include elapsed seconds:

```python
if state["status"] == "running" and state.get("started_at"):
    state["elapsed"] = round(time.time() - state["started_at"], 1)
```

This lets polling UIs show "🔄 Build en cours... (45s)" and detect stalls early.

## Pitfalls

- **Don't** make the build thread daemon=True — if it's doing I/O, you want it to finish, not get killed at shutdown
- **Don't** use `threading.Timer` as a kill switch — Python threads can't be forcefully killed; `join(timeout=N)` + state transition is the correct pattern
- **Don't** forget `import time` — it's not always imported in FastAPI apps that use `datetime` instead
