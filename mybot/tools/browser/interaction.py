from __future__ import annotations

import json

from ..result import BrowserResult
from .base import SNAPSHOT_MAX_OUTPUT_CHARS, PlaywrightCliTool


DEFAULT_SNAPSHOT_DEPTH = 8
MIN_SNAPSHOT_DEPTH = 1
MAX_SNAPSHOT_DEPTH = 20


class BrowserSnapshotTool(PlaywrightCliTool):
    @property
    def name(self) -> str:
        return "browser_snapshot"

    @property
    def description(self) -> str:
        return (
            "Capture an inline accessibility snapshot of the current page or a "
            "specific element, including refs for later browser actions."
        )

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "session": {
                    "type": "string",
                    "description": "Browser session name",
                    "default": "",
                },
                "target": {
                    "type": "string",
                    "description": "Optional element ref or selector",
                    "default": "",
                },
                "depth": {
                    "type": "integer",
                    "description": "Maximum accessibility tree depth",
                    "minimum": MIN_SNAPSHOT_DEPTH,
                    "maximum": MAX_SNAPSHOT_DEPTH,
                    "default": DEFAULT_SNAPSHOT_DEPTH,
                },
            },
        }

    async def execute(
        self,
        session: str = "",
        target: str = "",
        depth: int = DEFAULT_SNAPSHOT_DEPTH,
        **kwargs,
    ) -> BrowserResult:
        if (
            isinstance(depth, bool)
            or not isinstance(depth, int)
            or not MIN_SNAPSHOT_DEPTH <= depth <= MAX_SNAPSHOT_DEPTH
        ):
            raise ValueError(
                f"depth must be an integer from {MIN_SNAPSHOT_DEPTH} to "
                f"{MAX_SNAPSHOT_DEPTH}"
            )

        # An explicitly empty filename makes the CLI return YAML inline instead
        # of replacing large snapshots with a link to a generated file.
        parts = self._session_prefix(session) + [
            "snapshot",
            "--filename=",
            f"--depth={depth}",
        ]
        if target.strip():
            parts.append(target.strip())
        return await self._run_parts(
            parts,
            max_output_chars=SNAPSHOT_MAX_OUTPUT_CHARS,
        )


class BrowserClickTool(PlaywrightCliTool):
    @property
    def name(self) -> str:
        return "browser_click"

    @property
    def description(self) -> str:
        return "Click or double-click an element by ref or selector."

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "target": {"type": "string", "description": "Element ref or selector"},
                "session": {
                    "type": "string",
                    "description": "Browser session name",
                    "default": "",
                },
                "double": {
                    "type": "boolean",
                    "description": "Use double click instead of single click",
                    "default": False,
                },
            },
            "required": ["target"],
        }

    async def execute(
        self,
        target: str,
        session: str = "",
        double: bool = False,
        **kwargs,
    ) -> BrowserResult:
        command = "dblclick" if double else "click"
        return await self._run_parts(
            self._session_prefix(session) + [command, target.strip()]
        )


class BrowserTypeTool(PlaywrightCliTool):
    @property
    def name(self) -> str:
        return "browser_type"

    @property
    def description(self) -> str:
        return "Type text or fill a target element in the browser."

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "text": {"type": "string", "description": "Text to input"},
                "target": {
                    "type": "string",
                    "description": "Optional element ref or selector to fill",
                    "default": "",
                },
                "submit": {
                    "type": "boolean",
                    "description": "Submit after filling the target element",
                    "default": False,
                },
                "session": {
                    "type": "string",
                    "description": "Browser session name",
                    "default": "",
                },
            },
            "required": ["text"],
        }

    async def execute(
        self,
        text: str,
        target: str = "",
        submit: bool = False,
        session: str = "",
        **kwargs,
    ) -> BrowserResult:
        if target.strip():
            parts = self._session_prefix(session) + ["fill", target.strip(), text]
            if submit:
                parts.append("--submit")
        else:
            parts = self._session_prefix(session) + ["type", text]
        return await self._run_parts(parts)


class BrowserPressTool(PlaywrightCliTool):
    @property
    def name(self) -> str:
        return "browser_press"

    @property
    def description(self) -> str:
        return "Press a keyboard key in the browser."

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "key": {
                    "type": "string",
                    "description": "Keyboard key such as Enter, Space, ArrowDown",
                },
                "session": {
                    "type": "string",
                    "description": "Browser session name",
                    "default": "",
                },
            },
            "required": ["key"],
        }

    async def execute(
        self,
        key: str,
        session: str = "",
        **kwargs,
    ) -> BrowserResult:
        return await self._run_parts(
            self._session_prefix(session) + ["press", key.strip()]
        )


class BrowserLinksTool(PlaywrightCliTool):
    @property
    def name(self) -> str:
        return "browser_links"

    @property
    def description(self) -> str:
        return (
            "List rendered links in visual top-to-bottom, left-to-right order, "
            "deduplicated by destination. Use this before selecting an ordinal "
            "search result such as the fifth video."
        )

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "target": {
                    "type": "string",
                    "description": "Optional element ref or selector containing the links",
                    "default": "",
                },
                "url_contains": {
                    "type": "string",
                    "description": "Optional substring required in each destination URL",
                    "default": "",
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum number of unique links to return",
                    "minimum": 1,
                    "maximum": 100,
                    "default": 30,
                },
                "session": {
                    "type": "string",
                    "description": "Browser session name",
                    "default": "",
                },
            },
        }

    def _build_script(self, has_target: bool, url_contains: str, limit: int) -> str:
        root = "root" if has_target else "document"
        filter_value = json.dumps(url_contains, ensure_ascii=True)
        return (
            ("(root) => {" if has_target else "() => {")
            + f"const rootNode={root};"
            + f"const urlFilter={filter_value};"
            + f"const limit={limit};"
            + "const candidates=Array.from(rootNode.querySelectorAll('a[href]'))"
            + ".map((anchor)=>{const rect=anchor.getBoundingClientRect();"
            + "const style=getComputedStyle(anchor);"
            + "const text=(anchor.innerText||anchor.getAttribute('aria-label')||"
            + "anchor.getAttribute('title')||anchor.querySelector('img')?.alt||'')"
            + ".replace(/\\s+/g,' ').trim();"
            + "return {text,url:anchor.href,top:rect.top+scrollY,left:rect.left+scrollX,"
            + "width:rect.width,height:rect.height,display:style.display,"
            + "visibility:style.visibility};})"
            + ".filter((item)=>item.width>0&&item.height>0&&item.display!=='none'&&"
            + "item.visibility!=='hidden'&&(!urlFilter||item.url.includes(urlFilter)));"
            + "candidates.sort((a,b)=>Math.abs(a.top-b.top)>2?a.top-b.top:a.left-b.left);"
            + "const seen=new Set();const links=[];"
            + "for(const item of candidates){const parsed=new URL(item.url);"
            + "const key=parsed.origin+parsed.pathname;"
            + "if(seen.has(key))continue;seen.add(key);"
            + "links.push({position:links.length+1,title:item.text,url:item.url});}"
            + "return {total:links.length,links:links.slice(0,limit)};}"
        )

    async def execute(
        self,
        target: str = "",
        url_contains: str = "",
        limit: int = 30,
        session: str = "",
        **kwargs,
    ) -> BrowserResult:
        if (
            isinstance(limit, bool)
            or not isinstance(limit, int)
            or not 1 <= limit <= 100
        ):
            raise ValueError("limit must be an integer from 1 to 100")

        resolved_target = target.strip()
        script = self._build_script(bool(resolved_target), url_contains.strip(), limit)
        parts = self._session_prefix(session) + ["eval", script]
        if resolved_target:
            parts.append(resolved_target)
        return await self._run_parts(parts)


class BrowserEvalTool(PlaywrightCliTool):
    @property
    def name(self) -> str:
        return "browser_eval"

    @property
    def description(self) -> str:
        return "Run JavaScript in the current page, optionally against a target element."

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "script": {
                    "type": "string",
                    "description": "JavaScript expression or function to evaluate",
                },
                "target": {
                    "type": "string",
                    "description": "Optional element ref or selector",
                    "default": "",
                },
                "session": {
                    "type": "string",
                    "description": "Browser session name",
                    "default": "",
                },
            },
            "required": ["script"],
        }

    async def execute(
        self,
        script: str,
        target: str = "",
        session: str = "",
        **kwargs,
    ) -> BrowserResult:
        parts = self._session_prefix(session) + ["eval", script]
        if target.strip():
            parts.append(target.strip())
        return await self._run_parts(parts)
