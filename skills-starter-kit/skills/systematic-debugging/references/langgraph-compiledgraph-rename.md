# Langgraph API Changes (1.0.x → 1.1.x)

## CompiledGraph → CompiledStateGraph

**langgraph >= 1.1.0** renamed `CompiledGraph` to `CompiledStateGraph`.

**Error:**
```
ImportError: cannot import name 'CompiledGraph' from 'langgraph.graph.state'
Did you mean: 'CompiledStateGraph'?
```

**Fix:**
```python
# Before (langgraph 1.0.x)
from langgraph.graph.state import CompiledGraph

def save_graph_as_png(app: CompiledGraph, output_file_path) -> None:
    ...

# After (langgraph 1.1.x)
from langgraph.graph.state import CompiledStateGraph

def save_graph_as_png(app: CompiledStateGraph, output_file_path) -> None:
    ...
```

## Other Breaking Changes (1.1.x)

| Old | New |
|-----|-----|
| `CompiledGraph` | `CompiledStateGraph` |
| `StateGraph.compile()` return type | Now `CompiledStateGraph` |

## Version Detection

```bash
pip show langgraph | grep Version
# Version: 1.1.10  → need CompiledStateGraph
# Version: 1.0.x   → CompiledGraph is fine
```
