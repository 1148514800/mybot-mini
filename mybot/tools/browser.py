from __future__ import annotations

import asyncio
import json
import os
import re
import shutil
import subprocess
from pathlib import Path

from .base import BrowserResult, Tool


MANAGED_BROWSER_SESSION = "managed_browser"
LOCAL_BROWSER_SESSION = "local_browser"
MANAGED_PROFILE_DIRECTORY = "managed_browser"

COMMAND_TIMEOUT_SECONDS = 60
MAX_OUTPUT_CHARS = 12000
SNAPSHOT_MAX_OUTPUT_CHARS = 30000

DEFAULT_SNAPSHOT_DEPTH = 8
MIN_SNAPSHOT_DEPTH = 1
MAX_SNAPSHOT_DEPTH = 20
DEFAULT_INSPECT_LIMIT = 20
MAX_INSPECT_LIMIT = 50
MAX_INSPECT_QUERY_CHARS = 1000

_CLI_ERROR_BLOCK = re.compile(
    r"(?ms)^### Error[ \t]*\r?\n(.*?)(?=^### [^\r\n]+[ \t]*\r?$|\Z)"
)
_PAGE_URL = re.compile(r"(?m)^- Page URL:\s*(.+?)\s*$")
_PAGE_TITLE = re.compile(r"(?m)^- Page Title:\s*(.+?)\s*$")

# Failure classification keeps only categories the model can act on.
_ERROR_PATTERNS: tuple[tuple[str, bool, re.Pattern[str]], ...] = (
    ("stale_target", True, re.compile(
        r"(?:stale\s+(?:element|target)|ref(?:erence)?\s+[^\n]*not\s+found)", re.I)),
    ("ambiguous_target", True, re.compile(
        r"(?:strict\s+mode\s+violation|resolved\s+to\s+\d+\s+elements"
        r"|multiple\s+(?:matching\s+)?elements)", re.I)),
    ("tool_syntax_error", False, re.compile(
        r"(?:syntaxerror|unexpected\s+token|invalid\s+selector)", re.I)),
    ("page_timeout", True, re.compile(r"(?:timed?\s*out|timeouterror)", re.I)),
    ("auth_required", True, re.compile(
        r"(?:login\s+required|sign[ -]?in\s+required|unauthorized|not\s+authenticated)", re.I)),
    ("navigation_failure", True, re.compile(
        r"(?:net::err_|navigation\s+(?:failed|aborted)|page\s+crashed)", re.I)),
    ("target_not_found", True, re.compile(
        r"(?:target\s+[^\n]*not\s+found|no\s+element\s+(?:found|matches)"
        r"|postcondition_not_met)", re.I)),
)


def classify_browser_error(error: str | None, output: str = "") -> tuple[str, bool]:
    """Return (error_type, recoverable) for a failed browser command."""
    text = "\n".join(part for part in (error or "", output) if part)
    for name, recoverable, pattern in _ERROR_PATTERNS:
        if pattern.search(text):
            return name, recoverable
    return "unknown", False


class PlaywrightCliTool(Tool):
    """Shared playwright-cli subprocess boundary for every browser_* tool."""

    async def _run(
        self,
        parts: list[str],
        max_output_chars: int = MAX_OUTPUT_CHARS,
    ) -> BrowserResult:
        action = self.name.removeprefix("browser_")
        session = next(
            (part[3:] for part in parts if part.startswith("-s=") and part[3:]),
            "",
        )
        proc = None
        try:
            command, extra_kwargs = self._spawn_command(parts)
            proc = await asyncio.create_subprocess_exec(
                *command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                **extra_kwargs,
            )
            out, err = await asyncio.wait_for(
                proc.communicate(), timeout=COMMAND_TIMEOUT_SECONDS
            )
            output = out.decode(errors="replace")
            if err:
                output += f"\nSTDERR:\n{err.decode(errors='replace')}"
            output = output or "(no output)"

            error_match = _CLI_ERROR_BLOCK.search(output)
            explicit_error = error_match.group(1).strip()[:2000] if error_match else ""
            url_match = _PAGE_URL.search(output)
            title_match = _PAGE_TITLE.search(output)
            url = url_match.group(1).strip() if url_match else None
            title = title_match.group(1).strip() if title_match else None
            truncated = len(output) > max_output_chars
            output = self._truncate(output, max_output_chars)
            metadata: dict = {"exit_code": proc.returncode, "output_truncated": truncated}

            if proc.returncode or explicit_error:
                error = (
                    f"playwright-cli exited with code {proc.returncode}"
                    if proc.returncode
                    else f"playwright-cli reported an error: {explicit_error}"
                )
                error_type, recoverable = classify_browser_error(error, output)
                metadata.update({"error_type": error_type, "recoverable": recoverable})
                return BrowserResult(
                    success=False,
                    action=action,
                    session=session,
                    url=url,
                    title=title,
                    error=error,
                    output=output,
                    metadata=metadata,
                )
            return BrowserResult(
                success=True,
                action=action,
                session=session,
                url=url,
                title=title,
                output=output,
                metadata=metadata,
            )
        except FileNotFoundError:
            return self._failed(
                action,
                session,
                "playwright-cli was not found in PATH. Install Node.js and "
                "playwright-cli first.",
            )
        except TimeoutError:
            if proc is not None and proc.returncode is None:
                proc.kill()
                await proc.communicate()
            return self._failed(
                action,
                session,
                f"playwright-cli timed out after {COMMAND_TIMEOUT_SECONDS} seconds.",
            )
        except Exception as exc:
            return self._failed(action, session, f"{type(exc).__name__}: {exc}")

    @staticmethod
    def _failed(action: str, session: str, error: str) -> BrowserResult:
        error_type, recoverable = classify_browser_error(error)
        return BrowserResult(
            success=False,
            action=action,
            session=session,
            error=error,
            metadata={"error_type": error_type, "recoverable": recoverable},
        )

    @staticmethod
    def _truncate(text: str, limit: int) -> str:
        if len(text) <= limit:
            return text
        omitted = len(text) - limit
        marker = f"\n\n...[output truncated; at least {omitted} characters omitted]"
        if len(marker) >= limit:
            return marker[:limit]
        return text[: limit - len(marker)] + marker

    @staticmethod
    def _spawn_command(parts: list[str]) -> tuple[list[str], dict]:
        if os.name != "nt":
            return parts, {}
        kwargs = {"creationflags": getattr(subprocess, "CREATE_NO_WINDOW", 0)}
        cli_path = shutil.which(parts[0])
        if cli_path and cli_path.lower().endswith((".cmd", ".bat")):
            cli_dir = Path(cli_path).resolve().parent
            node = cli_dir / "node.exe"
            script = cli_dir / "node_modules" / "@playwright" / "cli" / "playwright-cli.js"
            node_command = str(node) if node.exists() else shutil.which("node")
            # npm's .cmd shim re-parses `%*`, mangling JS metadata characters.
            if node_command and script.exists():
                return [node_command, str(script), *parts[1:]], kwargs
            return ["cmd", "/d", "/s", "/c", *parts], kwargs
        return parts, kwargs


class BrowserAttachTool(PlaywrightCliTool):
    @property
    def name(self) -> str:
        return "browser_attach"

    @property
    def description(self) -> str:
        return (
            "Attach to the user's already-open local Chrome through CDP, reusing "
            "its profile, tabs and login state."
        )

    @property
    def parameters(self) -> dict:
        return {"type": "object", "properties": {}}

    async def execute(self, session: str = "", **kwargs) -> BrowserResult:
        return await self._run(
            ["playwright-cli", f"-s={LOCAL_BROWSER_SESSION}", "attach", "--cdp=chrome"]
        )


class BrowserOpenTool(PlaywrightCliTool):
    def __init__(self, workspace: Path):
        self._workspace = workspace.resolve()
        self._profile = self._workspace / "browser_profiles" / MANAGED_PROFILE_DIRECTORY
        if not self._profile.is_relative_to(self._workspace):
            raise ValueError("managed browser profile must stay inside workspace")

    @property
    def name(self) -> str:
        return "browser_open"

    @property
    def description(self) -> str:
        return (
            "Open a separate visible Chrome with MyBot's persistent profile. "
            "This is the default browser mode."
        )

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "url": {"type": "string", "description": "Optional URL to open", "default": ""},
                "session": {"type": "string", "description": "Browser session name", "default": ""},
            },
        }

    async def execute(self, url: str = "", session: str = "", **kwargs) -> BrowserResult:
        self._profile.mkdir(parents=True, exist_ok=True)
        parts = [
            "playwright-cli",
            f"-s={MANAGED_BROWSER_SESSION}",
            "open",
        ]
        if url.strip():
            parts.append(url.strip())
        parts.extend(["--browser=chrome", "--headed", f"--profile={self._profile}"])
        return await self._run(parts)


class BrowserGotoTool(PlaywrightCliTool):
    @property
    def name(self) -> str:
        return "browser_goto"

    @property
    def description(self) -> str:
        return "Navigate the current page to a URL."

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "url": {"type": "string", "description": "URL to navigate to"},
                "session": {"type": "string", "description": "Browser session name", "default": ""},
            },
            "required": ["url"],
        }

    async def execute(self, url: str, session: str = "", **kwargs) -> BrowserResult:
        return await self._run(self._session(session) + ["goto", url.strip()])

    def _session(self, session: str) -> list[str]:
        return ["playwright-cli", f"-s={session.strip() or MANAGED_BROWSER_SESSION}"]


class BrowserTabTool(BrowserGotoTool):
    @property
    def name(self) -> str:
        return "browser_tab"

    @property
    def description(self) -> str:
        return "List, create, select or close tabs. Use list/select after an action opens a tab."

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "description": "Tab operation",
                    "enum": ["list", "new", "select", "close"],
                },
                "index": {"type": "integer", "description": "Zero-based tab index", "minimum": 0},
                "url": {"type": "string", "description": "Optional URL for a new tab", "default": ""},
                "session": {"type": "string", "description": "Browser session name", "default": ""},
            },
            "required": ["action"],
        }

    async def execute(
        self,
        action: str,
        index: int | None = None,
        url: str = "",
        session: str = "",
        **kwargs,
    ) -> BrowserResult:
        resolved = action.strip().lower()
        if resolved not in {"list", "new", "select", "close"}:
            raise ValueError("action must be list, new, select or close")
        parts = self._session(session)
        if resolved == "list":
            parts.append("tab-list")
        elif resolved == "new":
            parts.append("tab-new")
            if url.strip():
                parts.append(url.strip())
        else:
            if isinstance(index, bool) or not isinstance(index, int) or index < 0:
                raise ValueError(f"index is required for tab {resolved}")
            parts.extend([f"tab-{resolved}", str(index)])
        return await self._run(parts)


class BrowserCloseTool(BrowserGotoTool):
    @property
    def name(self) -> str:
        return "browser_close"

    @property
    def description(self) -> str:
        return "Close the current browser session."

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "session": {"type": "string", "description": "Browser session name", "default": ""},
            },
        }

    async def execute(self, session: str = "", **kwargs) -> BrowserResult:
        return await self._run(self._session(session) + ["close"])


_INSPECT_SCRIPT = """(query) => {
const norm=(v)=>String(v==null?'':v).replace(/\\s+/g,' ').trim();
const low=(v)=>norm(v).toLocaleLowerCase();
const role=(n)=>{
  const explicit=norm(n.getAttribute('role'));
  if(explicit)return explicit;
  const tag=n.tagName.toLocaleLowerCase();
  if(tag==='a'&&n.hasAttribute('href'))return 'link';
  if(tag==='button')return 'button';
  if(tag==='textarea')return 'textbox';
  if(tag==='select')return 'combobox';
  if(tag==='input'){
    const type=low(n.getAttribute('type')||'text');
    if(type==='checkbox'||type==='radio')return type;
    if(['button','submit','reset'].includes(type))return 'button';
    return 'textbox';
  }
  return '';
};
const visible=(n)=>{
  const r=n.getBoundingClientRect();
  const s=getComputedStyle(n);
  return r.width>0&&r.height>0&&s.display!=='none'&&s.visibility!=='hidden';
};
const target=(n)=>{
  if(n.id)return '#'+CSS.escape(n.id);
  const tag=n.tagName.toLocaleLowerCase();
  for(const attr of ['data-testid','name','aria-label','placeholder']){
    const v=n.getAttribute(attr);
    if(!v)continue;
    const c=tag+'['+attr+'='+JSON.stringify(v)+']';
    try{if(document.querySelectorAll(c).length===1)return c;}catch(e){}
  }
  const parts=[];
  let cur=n;
  while(cur&&cur.nodeType===1&&parts.length<6){
    const t=cur.tagName.toLocaleLowerCase();
    const sibs=Array.from(cur.parentElement?.children||[]).filter((x)=>x.tagName===cur.tagName);
    parts.unshift(t+(sibs.length>1?':nth-of-type('+(sibs.indexOf(cur)+1)+')':''));
    const c=parts.join(' > ');
    try{if(document.querySelectorAll(c).length===1)return c;}catch(e){}
    cur=cur.parentElement;
  }
  return parts.join(' > ');
};
const hasDom=Boolean(query.selector||query.text||query.role||query.placeholder);
let nodes=[];
try{
  if(hasDom)nodes=Array.from(document.querySelectorAll(query.selector||'*'));
}catch(e){throw new Error('invalid selector: '+e.message);}
const matches=[];
for(const n of nodes.slice(0,5000)){
  if(query.visible_only&&!visible(n))continue;
  const text=norm(n.innerText||n.textContent);
  const name=norm(n.getAttribute('aria-label')||n.getAttribute('title')||text||n.getAttribute('placeholder'));
  const r=role(n);
  const placeholder=norm(n.getAttribute('placeholder'));
  const cmp=(a,b)=>query.exact?low(a)===low(b):low(a).includes(low(b));
  if(query.text&&!cmp(name,query.text)&&!cmp(text,query.text))continue;
  if(query.role&&low(r)!==low(query.role))continue;
  if(query.placeholder&&!cmp(placeholder,query.placeholder))continue;
  matches.push({position:matches.length+1,tag:n.tagName.toLocaleLowerCase(),role:r,
    text:text.slice(0,500),accessible_name:name.slice(0,500),placeholder,
    type:norm(n.getAttribute('type')),href:n.href||'',target:target(n)});
  if(matches.length>=query.limit)break;
}
const urlOk=!query.url_contains||location.href.includes(query.url_contains);
const enough=!hasDom||matches.length>=query.min_count;
const met=urlOk&&enough;
if(query.verify&&!met)throw new Error('POSTCONDITION_NOT_MET: no structured evidence found');
return {url:location.href,count:matches.length,truncated:matches.length>=query.limit,
  postcondition_met:query.verify?met:undefined,matches};
}"""


class _InspectBase(PlaywrightCliTool):
    """Shared structured DOM query used by browser_inspect and browser_verify."""

    verify = False

    @property
    def parameters(self) -> dict:
        properties = {
            "selector": {"type": "string", "description": "Optional CSS selector", "default": ""},
            "text": {"type": "string", "description": "Optional visible text", "default": ""},
            "role": {"type": "string", "description": "Optional ARIA role", "default": ""},
            "placeholder": {"type": "string", "description": "Optional placeholder", "default": ""},
            "exact": {"type": "boolean", "description": "Exact text matching", "default": False},
            "limit": {
                "type": "integer",
                "minimum": 1,
                "maximum": MAX_INSPECT_LIMIT,
                "default": DEFAULT_INSPECT_LIMIT,
            },
            "session": {"type": "string", "description": "Browser session name", "default": ""},
        }
        required_options = [{"required": [name]} for name in ("selector", "text", "role", "placeholder")]
        if not self.verify:
            return {"type": "object", "properties": properties, "anyOf": required_options}
        properties["url_contains"] = {
            "type": "string",
            "description": "Optional substring required in the current URL",
            "default": "",
        }
        properties["min_count"] = {
            "type": "integer",
            "minimum": 1,
            "maximum": MAX_INSPECT_LIMIT,
            "default": 1,
        }
        required_options.append({"required": ["url_contains"]})
        return {"type": "object", "properties": properties, "anyOf": required_options}

    async def _query(
        self,
        *,
        selector: str,
        text: str,
        role: str,
        placeholder: str,
        url_contains: str,
        exact: bool,
        limit: int,
        session: str,
        min_count: int = 1,
    ) -> BrowserResult:
        fields = {
            "selector": selector.strip(),
            "text": text.strip(),
            "role": role.strip(),
            "placeholder": placeholder.strip(),
            "url_contains": url_contains.strip(),
        }
        for name, value in fields.items():
            if len(value) > MAX_INSPECT_QUERY_CHARS:
                raise ValueError(f"{name} must not exceed {MAX_INSPECT_QUERY_CHARS} characters")
        if not any(fields.values()):
            raise ValueError(
                f"{self.name} requires " + ", ".join(fields)
            )
        if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= MAX_INSPECT_LIMIT:
            raise ValueError(f"limit must be an integer from 1 to {MAX_INSPECT_LIMIT}")

        query = dict(fields, exact=exact, visible_only=True, limit=limit,
                     min_count=min_count, verify=self.verify)
        script = f"({_INSPECT_SCRIPT})({json.dumps(query, ensure_ascii=True, separators=(',', ':'))})"
        parts = ["playwright-cli", f"-s={session.strip() or MANAGED_BROWSER_SESSION}", "eval", script]
        result = await self._run(parts)
        # Drop the echoed script so the model only sees the returned JSON.
        result.output = result.output.split("\n### Ran Playwright code", 1)[0].rstrip()
        if self.verify:
            result.metadata["postcondition_met"] = result.success
        return result


class BrowserInspectTool(_InspectBase):
    @property
    def name(self) -> str:
        return "browser_inspect"

    @property
    def description(self) -> str:
        return (
            "Read visible DOM elements by selector, text, role or placeholder. "
            "Prefer this over browser_eval for finding text, inputs and buttons."
        )

    async def execute(
        self,
        selector: str = "",
        text: str = "",
        role: str = "",
        placeholder: str = "",
        exact: bool = False,
        limit: int = DEFAULT_INSPECT_LIMIT,
        session: str = "",
        **kwargs,
    ) -> BrowserResult:
        return await self._query(
            selector=selector, text=text, role=role, placeholder=placeholder,
            url_contains="", exact=exact, limit=limit, session=session,
        )


class BrowserVerifyTool(_InspectBase):
    verify = True

    @property
    def name(self) -> str:
        return "browser_verify"

    @property
    def description(self) -> str:
        return (
            "Verify one structured DOM or URL postcondition before claiming task "
            "success. Returns postcondition_met=true only on evidence."
        )

    async def execute(
        self,
        selector: str = "",
        text: str = "",
        role: str = "",
        placeholder: str = "",
        url_contains: str = "",
        exact: bool = False,
        min_count: int = 1,
        limit: int = DEFAULT_INSPECT_LIMIT,
        session: str = "",
        **kwargs,
    ) -> BrowserResult:
        return await self._query(
            selector=selector, text=text, role=role, placeholder=placeholder,
            url_contains=url_contains, exact=exact, limit=limit, session=session,
            min_count=min_count,
        )


class BrowserSnapshotTool(PlaywrightCliTool):
    @property
    def name(self) -> str:
        return "browser_snapshot"

    @property
    def description(self) -> str:
        return "Capture an accessibility snapshot of the page, including refs for later actions."

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "target": {"type": "string", "description": "Optional element ref or selector", "default": ""},
                "depth": {
                    "type": "integer",
                    "description": "Maximum accessibility tree depth",
                    "minimum": MIN_SNAPSHOT_DEPTH,
                    "maximum": MAX_SNAPSHOT_DEPTH,
                    "default": DEFAULT_SNAPSHOT_DEPTH,
                },
                "session": {"type": "string", "description": "Browser session name", "default": ""},
            },
        }

    async def execute(
        self,
        target: str = "",
        depth: int = DEFAULT_SNAPSHOT_DEPTH,
        session: str = "",
        **kwargs,
    ) -> BrowserResult:
        if (
            isinstance(depth, bool)
            or not isinstance(depth, int)
            or not MIN_SNAPSHOT_DEPTH <= depth <= MAX_SNAPSHOT_DEPTH
        ):
            raise ValueError(
                f"depth must be an integer from {MIN_SNAPSHOT_DEPTH} to {MAX_SNAPSHOT_DEPTH}"
            )
        # An explicitly empty filename makes the CLI return YAML inline.
        parts = [
            "playwright-cli",
            f"-s={session.strip() or MANAGED_BROWSER_SESSION}",
            "snapshot",
            "--filename=",
            f"--depth={depth}",
        ]
        if target.strip():
            parts.append(target.strip())
        return await self._run(parts, max_output_chars=SNAPSHOT_MAX_OUTPUT_CHARS)


class BrowserClickTool(BrowserGotoTool):
    @property
    def name(self) -> str:
        return "browser_click"

    @property
    def description(self) -> str:
        return "Click an element by ref or selector."

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "target": {"type": "string", "description": "Element ref or selector"},
                "double": {"type": "boolean", "description": "Double click instead", "default": False},
                "session": {"type": "string", "description": "Browser session name", "default": ""},
            },
            "required": ["target"],
        }

    async def execute(
        self,
        target: str,
        double: bool = False,
        session: str = "",
        **kwargs,
    ) -> BrowserResult:
        command = "dblclick" if double else "click"
        return await self._run(self._session(session) + [command, target.strip()])


class BrowserTypeTool(BrowserGotoTool):
    @property
    def name(self) -> str:
        return "browser_type"

    @property
    def description(self) -> str:
        return "Type text into the page, or fill a target element."

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "text": {"type": "string", "description": "Text to input"},
                "target": {"type": "string", "description": "Optional element to fill", "default": ""},
                "submit": {"type": "boolean", "description": "Submit after filling", "default": False},
                "session": {"type": "string", "description": "Browser session name", "default": ""},
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
        parts = self._session(session)
        if target.strip():
            parts.extend(["fill", target.strip(), text])
            if submit:
                parts.append("--submit")
        else:
            parts.extend(["type", text])
        return await self._run(parts)


class BrowserPressTool(BrowserGotoTool):
    @property
    def name(self) -> str:
        return "browser_press"

    @property
    def description(self) -> str:
        return "Press a keyboard key, such as Enter or ArrowDown."

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "key": {"type": "string", "description": "Key name such as Enter"},
                "session": {"type": "string", "description": "Browser session name", "default": ""},
            },
            "required": ["key"],
        }

    async def execute(self, key: str, session: str = "", **kwargs) -> BrowserResult:
        return await self._run(self._session(session) + ["press", key.strip()])


class BrowserLinksTool(BrowserGotoTool):
    @property
    def name(self) -> str:
        return "browser_links"

    @property
    def description(self) -> str:
        return (
            "List rendered links in visual order, deduplicated by destination. "
            "Use this before selecting an ordinal result such as the fifth video."
        )

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "target": {"type": "string", "description": "Optional container element", "default": ""},
                "url_contains": {"type": "string", "description": "Optional URL substring filter", "default": ""},
                "limit": {
                    "type": "integer",
                    "description": "Maximum number of links",
                    "minimum": 1,
                    "maximum": 100,
                    "default": 30,
                },
                "session": {"type": "string", "description": "Browser session name", "default": ""},
            },
        }

    async def execute(
        self,
        target: str = "",
        url_contains: str = "",
        limit: int = 30,
        session: str = "",
        **kwargs,
    ) -> BrowserResult:
        if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 100:
            raise ValueError("limit must be an integer from 1 to 100")
        script = (
            "(root) => {"
            "const nodes=Array.from(root.querySelectorAll('a[href]'));"
            f"const filter={json.dumps(url_contains.strip(), ensure_ascii=True)};"
            f"const limit={limit};"
            "const items=nodes.map((a)=>{const r=a.getBoundingClientRect();"
            "const s=getComputedStyle(a);"
            "const text=(a.innerText||a.getAttribute('aria-label')||a.getAttribute('title')||'')"
            ".replace(/\\s+/g,' ').trim();"
            "return {text,url:a.href,top:r.top+scrollY,left:r.left+scrollX,"
            "width:r.width,height:r.height,display:s.display,visibility:s.visibility};})"
            ".filter((i)=>i.width>0&&i.height>0&&i.display!=='none'"
            "&&i.visibility!=='hidden'&&(!filter||i.url.includes(filter)));"
            "items.sort((a,b)=>Math.abs(a.top-b.top)>2?a.top-b.top:a.left-b.left);"
            "const seen=new Set();const links=[];"
            "for(const i of items){const u=new URL(i.url);const key=u.origin+u.pathname;"
            "if(seen.has(key))continue;seen.add(key);"
            "links.push({position:links.length+1,title:i.text,url:i.url});}"
            "return {total:links.length,links:links.slice(0,limit)};}"
        )
        parts = self._session(session) + ["eval", script]
        if target.strip():
            parts.append(target.strip())
        return await self._run(parts)


class BrowserEvalTool(BrowserGotoTool):
    @property
    def name(self) -> str:
        return "browser_eval"

    @property
    def description(self) -> str:
        return "Run JavaScript in the page. Use only when structured tools cannot answer."

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "script": {"type": "string", "description": "JavaScript expression or function"},
                "target": {"type": "string", "description": "Optional element ref or selector", "default": ""},
                "session": {"type": "string", "description": "Browser session name", "default": ""},
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
        parts = self._session(session) + ["eval", script]
        if target.strip():
            parts.append(target.strip())
        return await self._run(parts)
