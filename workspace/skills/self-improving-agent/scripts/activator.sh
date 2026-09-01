#!/bin/bash
# Lightweight reminder for self-improvement review in the MyBot project.

set -e

cat << 'EOF'
<self-improvement-reminder>
After completing this MyBot task, ask:
- Did a repeated failure appear?
- Did the user correct a durable rule or preference?
- Did a missing capability become obvious?
- Should this be logged to .learnings/ and then promoted to instructions or memory?
</self-improvement-reminder>
EOF
