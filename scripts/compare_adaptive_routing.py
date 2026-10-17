"""Current-code paired comparison: fixed offline scripts + real synthetic stdio MCP.

Live retains the same double confirmation gate; development/archives never use it.
"""
from scripts.evaluate_tool_agent import main

if __name__=='__main__':
    main(default_modes=('eager','progressive_hybrid','adaptive_hybrid'))
