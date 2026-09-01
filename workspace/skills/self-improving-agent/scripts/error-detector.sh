#!/bin/bash
# Minimal error detector for environments that expose tool output to hooks.

set -e

OUTPUT="${CLAUDE_TOOL_OUTPUT:-}"

ERROR_PATTERNS=(
    "error:"
    "Error:"
    "failed"
    "fatal:"
    "Traceback"
    "Exception"
    "Permission denied"
    "No such file"
)

contains_error=false
for pattern in "${ERROR_PATTERNS[@]}"; do
    if [[ "$OUTPUT" == *"$pattern"* ]]; then
        contains_error=true
        break
    fi
done

if [ "$contains_error" = true ]; then
    cat << 'EOF'
<error-detected>
A command or tool error was detected.
If this looks non-obvious, recurring, or architecturally meaningful, log it to:
- .learnings/ERRORS.md
Then promote stable rules to workspace/instructions or workspace/memory if needed.
</error-detected>
EOF
fi
