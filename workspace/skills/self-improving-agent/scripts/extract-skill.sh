#!/bin/bash
# Create a new skill scaffold inside this MyBot project's workspace/skills directory.
# Usage: ./extract-skill.sh <skill-name> [--dry-run]

set -e

SKILLS_DIR="./workspace/skills"
SKILL_NAME=""
DRY_RUN=false

usage() {
    cat << EOF
Usage: $(basename "$0") <skill-name> [options]

Create a new skill scaffold for the MyBot project.

Options:
  --dry-run         Show what would be created
  --output-dir DIR  Relative output directory (default: ./workspace/skills)
  -h, --help        Show help
EOF
}

while [[ $# -gt 0 ]]; do
    case $1 in
        --dry-run)
            DRY_RUN=true
            shift
            ;;
        --output-dir)
            SKILLS_DIR="$2"
            shift 2
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        *)
            if [ -z "$SKILL_NAME" ]; then
                SKILL_NAME="$1"
            else
                echo "Unexpected argument: $1" >&2
                exit 1
            fi
            shift
            ;;
    esac
done

if [ -z "$SKILL_NAME" ]; then
    usage
    exit 1
fi

if ! [[ "$SKILL_NAME" =~ ^[a-z0-9]+(-[a-z0-9]+)*$ ]]; then
    echo "Skill name must use lowercase letters, digits, and hyphens only." >&2
    exit 1
fi

SKILL_PATH="$SKILLS_DIR/$SKILL_NAME"

if [ "$DRY_RUN" = true ]; then
    echo "Would create:"
    echo "  $SKILL_PATH/SKILL.md"
    exit 0
fi

mkdir -p "$SKILL_PATH"

cat > "$SKILL_PATH/SKILL.md" << TEMPLATE
---
name: $SKILL_NAME
description: "What this skill does and when to use it in the MyBot project."
---

# $(echo "$SKILL_NAME" | sed 's/-/ /g' | awk '{for(i=1;i<=NF;i++) $i=toupper(substr($i,1,1)) tolower(substr($i,2))}1')

## Use This Skill When

- [trigger]

## Workflow

1. Identify the situation
2. Apply the repo-specific fix
3. Validate against this MyBot project structure

## Project Paths

- \`config/config.json\`
- \`workspace/instructions/\`
- \`workspace/memory/memory.json\`
- \`workspace/state/runtime_state.json\`
- \`workspace/sessions/\`

## Source

- Learning ID: [TODO]
TEMPLATE

echo "Created $SKILL_PATH/SKILL.md"
