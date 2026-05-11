#!/bin/bash
# registry-update.sh — scan tools/ and regenerate REGISTRY.md
set -euo pipefail

TOOLS_DIR="$(cd "$(dirname "$0")/.." && pwd)"
REGISTRY="$TOOLS_DIR/REGISTRY.md"
PROJECT_NAME="$(basename "$(dirname "$TOOLS_DIR")")"

# Count tools
TOOL_COUNT=$(ls -d "$TOOLS_DIR"/*/tool.json 2>/dev/null | wc -l)

cat > "$REGISTRY" << 'HEADER'
# Tool Registry — PROJECT_NAME_PLACEHOLDER

> Auto-generated DATE_PLACEHOLDER. TOOL_COUNT_PLACEHOLDER tools available.
> Agents: read this file to discover available tools.
> Each tool's tool.json has full input/output specs.

HEADER

# Replace placeholders
sed -i "s/PROJECT_NAME_PLACEHOLDER/$PROJECT_NAME/" "$REGISTRY"
sed -i "s/DATE_PLACEHOLDER/$(date -I)/" "$REGISTRY"
sed -i "s/TOOL_COUNT_PLACEHOLDER/$TOOL_COUNT/" "$REGISTRY"

if [ "$TOOL_COUNT" -eq 0 ]; then
  echo "_No tools registered yet. Create a tool: mkdir tools/<name> && create tool.json + run.sh_" >> "$REGISTRY"
  mv "$REGISTRY" "${REGISTRY}.tmp" && mv "${REGISTRY}.tmp" "$REGISTRY"
  echo "Registry: $REGISTRY (empty)"
  exit 0
fi

# Group by category
declare -A CATEGORIES
declare -A CATEGORY_TOOLS

for tool_json in "$TOOLS_DIR"/*/tool.json; do
  [ -f "$tool_json" ] || continue
  name=$(python3 -c "import json; print(json.load(open('$tool_json'))['name'])" 2>/dev/null || echo "unknown")
  cat=$(python3 -c "import json; print(json.load(open('$tool_json')).get('category','uncategorized'))" 2>/dev/null || echo "uncategorized")
  desc=$(python3 -c "import json; print(json.load(open('$tool_json'))['description'])" 2>/dev/null || echo "")
  dir=$(basename "$(dirname "$tool_json")")
  
  CATEGORY_TOOLS["$cat"]+="$(printf "\n- **[%s](%s/tool.json)** — %s" "$name" "$dir" "$desc")"$'\n'
done

for cat in $(echo "${!CATEGORY_TOOLS[@]}" | tr ' ' '\n' | sort); do
  echo "## ${cat^}" >> "$REGISTRY"
  echo "${CATEGORY_TOOLS[$cat]}" >> "$REGISTRY"
done

cat >> "$REGISTRY" << 'FOOTER'

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
FOOTER

echo "Registry updated: $REGISTRY ($TOOL_COUNT tools)"
