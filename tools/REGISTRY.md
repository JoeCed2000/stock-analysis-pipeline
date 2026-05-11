# Tool Registry — stock-analysis-pipeline

> Auto-generated 2026-05-11. 2 tools available.
> Agents: read this file to discover available tools.
> Each tool's tool.json has full input/output specs.

## Finance

- **[analyze-ticker](analyze-ticker/tool.json)** — Run full stock analysis and return BUY/HOLD/SELL verdict with scoring breakdown

- **[generate-pdf](generate-pdf/tool.json)** — Generate deep-dive earnings PDF report for a ticker with EN and JP versions


## Usage for Agents

To call a tool:
1. `cat tools/<name>/tool.json` — read the input spec
2. `cd tools/<name> && ./run.sh <args>` — execute
3. Parse stdout as JSON (or text, as declared in tool.json outputs)
4. Handle errors using the error codes in tool.json

## Tool Creation

```bash
mkdir -p tools/my-tool
cat > tools/my-tool/tool.json << 'EOF'
{
  "name": "my-tool",
  "version": "1.0.0",
  "description": "What this tool does",
  "inputs": [{"name": "arg1", "type": "string", "required": true}],
  "outputs": [{"name": "stdout", "type": "json"}],
  "examples": [{"description": "Example usage", "command": "./run.sh value", "expected_output": "{}"}]
}
EOF
cat > tools/my-tool/run.sh << 'EOF'
#!/bin/bash
set -euo pipefail
echo '{"status": "ok"}'
EOF
chmod +x tools/my-tool/run.sh
./scripts/registry-update.sh
```
