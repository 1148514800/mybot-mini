from __future__ import annotations

import base64
import json

from ..result import BrowserResult
from .base import SNAPSHOT_MAX_OUTPUT_CHARS, PlaywrightCliTool


DEFAULT_SNAPSHOT_DEPTH = 8
MIN_SNAPSHOT_DEPTH = 1
MAX_SNAPSHOT_DEPTH = 20
DEFAULT_INSPECT_LIMIT = 20
MAX_INSPECT_LIMIT = 50
MAX_INSPECT_QUERY_CHARS = 1_000


_INSPECT_SCRIPT = """() => {
const query=JSON.parse(atob('__QUERY_BASE64__'));
const normalize=(value)=>String(value||'').replace(/\\s+/g,' ').trim();
const lowered=(value)=>normalize(value).toLocaleLowerCase();
const implicitRole=(node)=>{
  const explicit=normalize(node.getAttribute('role'));
  if(explicit)return explicit;
  const tag=node.tagName.toLocaleLowerCase();
  if(tag==='a'&&node.hasAttribute('href'))return 'link';
  if(tag==='button')return 'button';
  if(tag==='textarea')return 'textbox';
  if(tag==='select')return 'combobox';
  if(tag==='img')return 'img';
  if(tag==='input'){
    const type=lowered(node.getAttribute('type')||'text');
    if(type==='checkbox'||type==='radio')return type;
    if(['button','submit','reset'].includes(type))return 'button';
    return 'textbox';
  }
  return '';
};
const visible=(node)=>{
  const rect=node.getBoundingClientRect();
  const style=getComputedStyle(node);
  return rect.width>0&&rect.height>0&&style.display!=='none'&&
    style.visibility!=='hidden';
};
const targetFor=(node)=>{
  if(node.id)return '#'+CSS.escape(node.id);
  const tag=node.tagName.toLocaleLowerCase();
  for(const attr of ['data-testid','name','aria-label','placeholder']){
    const value=node.getAttribute(attr);
    if(!value)continue;
    const candidate=tag+'['+attr+'='+JSON.stringify(value)+']';
    try{if(document.querySelectorAll(candidate).length===1)return candidate;}
    catch(error){}
  }
  const parts=[];
  let current=node;
  while(current&&current.nodeType===1&&parts.length<6){
    const currentTag=current.tagName.toLocaleLowerCase();
    const siblings=Array.from(current.parentElement?.children||[])
      .filter((item)=>item.tagName===current.tagName);
    const suffix=siblings.length>1
      ? ':nth-of-type('+(siblings.indexOf(current)+1)+')':'';
    parts.unshift(currentTag+suffix);
    const candidate=parts.join(' > ');
    try{if(document.querySelectorAll(candidate).length===1)return candidate;}
    catch(error){}
    current=current.parentElement;
  }
  return parts.join(' > ');
};
const hasDomQuery=Boolean(query.selector||query.text||query.role||query.placeholder);
let candidates=[];
try{
  if(hasDomQuery)candidates=Array.from(document.querySelectorAll(query.selector||'*'));
}catch(error){
  throw new Error('Invalid selector: '+error.message);
}
const matches=[];
for(const node of candidates.slice(0,5000)){
  if(query.visible_only&&!visible(node))continue;
  const text=normalize(node.innerText||node.textContent);
  const accessibleName=normalize(
    node.getAttribute('aria-label')||node.getAttribute('title')||text||
    node.getAttribute('placeholder')||node.getAttribute('value')
  );
  const role=implicitRole(node);
  const placeholder=normalize(node.getAttribute('placeholder'));
  const compare=(actual,expected)=>query.exact
    ? lowered(actual)===lowered(expected)
    : lowered(actual).includes(lowered(expected));
  if(query.text&&!compare(accessibleName,query.text)&&!compare(text,query.text))continue;
  if(query.role&&lowered(role)!==lowered(query.role))continue;
  if(query.placeholder&&!compare(placeholder,query.placeholder))continue;
  matches.push({
    position:matches.length+1,
    tag:node.tagName.toLocaleLowerCase(),
    role,
    text:text.slice(0,500),
    accessible_name:accessibleName.slice(0,500),
    placeholder,
    type:normalize(node.getAttribute('type')),
    href:node.href||'',
    target:targetFor(node)
  });
  if(matches.length>=query.limit)break;
}
const urlMatches=!query.url_contains||location.href.includes(query.url_contains);
const enoughMatches=!hasDomQuery||matches.length>=query.min_count;
const postconditionMet=urlMatches&&enoughMatches;
if(query.verify&&!postconditionMet){
  throw new Error('POSTCONDITION_NOT_MET: structured browser evidence was not found');
}
return {
  query,
  url:location.href,
  count:matches.length,
  truncated:matches.length>=query.limit,
  postcondition_met:query.verify?postconditionMet:undefined,
  matches
};
}"""


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


class BrowserInspectTool(PlaywrightCliTool):
    """Read DOM state through fixed, structured queries instead of model JS."""

    @property
    def name(self) -> str:
        return "browser_inspect"

    @property
    def description(self) -> str:
        return (
            "Read visible DOM elements using structured selector, text, role, or "
            "placeholder filters. Prefer this over browser_eval for finding "
            "text, inputs, buttons, and element attributes. No JavaScript is "
            "accepted from the caller."
        )

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "selector": {
                    "type": "string",
                    "description": "Optional CSS selector",
                    "default": "",
                },
                "text": {
                    "type": "string",
                    "description": "Optional visible or accessible text",
                    "default": "",
                },
                "role": {
                    "type": "string",
                    "description": "Optional explicit or common implicit ARIA role",
                    "default": "",
                },
                "placeholder": {
                    "type": "string",
                    "description": "Optional input placeholder text",
                    "default": "",
                },
                "exact": {
                    "type": "boolean",
                    "description": "Use exact text and placeholder matching",
                    "default": False,
                },
                "visible_only": {
                    "type": "boolean",
                    "description": "Only return rendered elements",
                    "default": True,
                },
                "limit": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": MAX_INSPECT_LIMIT,
                    "default": DEFAULT_INSPECT_LIMIT,
                },
                "session": {
                    "type": "string",
                    "description": "Browser session name",
                    "default": "",
                },
            },
            "anyOf": [
                {"required": ["selector"]},
                {"required": ["text"]},
                {"required": ["role"]},
                {"required": ["placeholder"]},
            ],
        }

    @staticmethod
    def _validated_query_value(name: str, value: str) -> str:
        normalized = value.strip()
        if len(normalized) > MAX_INSPECT_QUERY_CHARS:
            raise ValueError(
                f"{name} must not exceed {MAX_INSPECT_QUERY_CHARS} characters"
            )
        return normalized

    def _build_script(self, query: dict) -> str:
        serialized = json.dumps(
            query,
            ensure_ascii=True,
            separators=(",", ":"),
        )
        encoded = base64.b64encode(serialized.encode("ascii")).decode("ascii")
        return _INSPECT_SCRIPT.replace("__QUERY_BASE64__", encoded)

    @staticmethod
    def _strip_internal_script(output: str) -> str:
        marker = "\n### Ran Playwright code"
        return output.split(marker, 1)[0].rstrip()

    async def execute(
        self,
        selector: str = "",
        text: str = "",
        role: str = "",
        placeholder: str = "",
        exact: bool = False,
        visible_only: bool = True,
        limit: int = DEFAULT_INSPECT_LIMIT,
        session: str = "",
        **kwargs,
    ) -> BrowserResult:
        query = {
            "selector": self._validated_query_value("selector", selector),
            "text": self._validated_query_value("text", text),
            "role": self._validated_query_value("role", role),
            "placeholder": self._validated_query_value(
                "placeholder",
                placeholder,
            ),
            "exact": exact,
            "visible_only": visible_only,
            "limit": limit,
            "min_count": 1,
            "url_contains": "",
            "verify": False,
        }
        if not any(
            query[name]
            for name in ("selector", "text", "role", "placeholder")
        ):
            raise ValueError(
                "browser_inspect requires selector, text, role, or placeholder"
            )
        if not isinstance(exact, bool) or not isinstance(visible_only, bool):
            raise ValueError("exact and visible_only must be booleans")
        if (
            isinstance(limit, bool)
            or not isinstance(limit, int)
            or not 1 <= limit <= MAX_INSPECT_LIMIT
        ):
            raise ValueError(
                f"limit must be an integer from 1 to {MAX_INSPECT_LIMIT}"
            )
        result = await self._run_parts(
            self._session_prefix(session) + ["eval", self._build_script(query)]
        )
        result.output = self._strip_internal_script(result.output)
        return result


class BrowserVerifyTool(BrowserInspectTool):
    """Verify one structured browser postcondition without caller JavaScript."""

    @property
    def name(self) -> str:
        return "browser_verify"

    @property
    def description(self) -> str:
        return (
            "Verify a browser task postcondition using structured DOM or URL "
            "evidence. Call this after a final click, fill, submit, send, or "
            "publish action before claiming task success. No JavaScript is "
            "accepted from the caller."
        )

    @property
    def parameters(self) -> dict:
        parameters = super().parameters
        properties = dict(parameters["properties"])
        properties.update(
            {
                "url_contains": {
                    "type": "string",
                    "description": "Optional substring required in the current URL",
                    "default": "",
                },
                "min_count": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": MAX_INSPECT_LIMIT,
                    "default": 1,
                },
            }
        )
        return {
            "type": "object",
            "properties": properties,
            "anyOf": [
                {"required": ["selector"]},
                {"required": ["text"]},
                {"required": ["role"]},
                {"required": ["placeholder"]},
                {"required": ["url_contains"]},
            ],
        }

    async def execute(
        self,
        selector: str = "",
        text: str = "",
        role: str = "",
        placeholder: str = "",
        url_contains: str = "",
        exact: bool = False,
        visible_only: bool = True,
        min_count: int = 1,
        limit: int = DEFAULT_INSPECT_LIMIT,
        session: str = "",
        **kwargs,
    ) -> BrowserResult:
        query = {
            "selector": self._validated_query_value("selector", selector),
            "text": self._validated_query_value("text", text),
            "role": self._validated_query_value("role", role),
            "placeholder": self._validated_query_value(
                "placeholder",
                placeholder,
            ),
            "url_contains": self._validated_query_value(
                "url_contains",
                url_contains,
            ),
            "exact": exact,
            "visible_only": visible_only,
            "min_count": min_count,
            "limit": limit,
            "verify": True,
        }
        if not any(
            query[name]
            for name in (
                "selector",
                "text",
                "role",
                "placeholder",
                "url_contains",
            )
        ):
            raise ValueError(
                "browser_verify requires selector, text, role, placeholder, "
                "or url_contains"
            )
        if not isinstance(exact, bool) or not isinstance(visible_only, bool):
            raise ValueError("exact and visible_only must be booleans")
        for name, value in (("min_count", min_count), ("limit", limit)):
            if (
                isinstance(value, bool)
                or not isinstance(value, int)
                or not 1 <= value <= MAX_INSPECT_LIMIT
            ):
                raise ValueError(
                    f"{name} must be an integer from 1 to {MAX_INSPECT_LIMIT}"
                )
        result = await self._run_parts(
            self._session_prefix(session) + ["eval", self._build_script(query)]
        )
        result.output = self._strip_internal_script(result.output)
        result.metadata["postcondition_met"] = result.success
        if result.success:
            result.metadata["completion_evidence"] = {
                key: value
                for key, value in query.items()
                if value not in {"", False} and key != "verify"
            }
        return result


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
