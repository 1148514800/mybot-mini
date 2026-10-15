from __future__ import annotations

import json
from copy import deepcopy

from jsonschema import Draft202012Validator
from jsonschema.exceptions import SchemaError

from ..tools import Tool, ToolResult
from .config import TOOL_NAME


class DefinitionError(ValueError):
    """Only fixed application messages, safe for startup diagnostics."""


SCHEMA_KEYS = {'type','properties','required','additionalProperties','items','enum','anyOf',
               'description','title','default','minimum','maximum','exclusiveMinimum','exclusiveMaximum',
               'minLength','maxLength','minItems','maxItems','uniqueItems','minProperties','maxProperties'}


def check_schema(schema):
    """Preserve a conservative non-strict Function Calling subset, reject the rest."""
    if not isinstance(schema,dict) or schema.get('type')!='object':
        raise DefinitionError('MCP input schema must be an object schema')
    try:
        size = len(json.dumps(schema,allow_nan=False))
    except (ValueError,TypeError,RecursionError):
        raise DefinitionError('MCP input schema is not safe JSON') from None
    if size>32768:
        raise DefinitionError('MCP input schema exceeds 32768 characters')
    def visit(node,depth=0):
        if not isinstance(node,dict) or depth>12 or set(node)-SCHEMA_KEYS:
            raise DefinitionError('Unsupported MCP schema keyword or nesting')
        for child in node.get('properties',{}).values():visit(child,depth+1)
        for key in ('items','additionalProperties'):
            if isinstance(node.get(key),dict):visit(node[key],depth+1)
        for child in node.get('anyOf',[]):visit(child,depth+1)
    try:
        Draft202012Validator.check_schema(schema)
    except SchemaError:
        raise DefinitionError('Invalid MCP JSON Schema') from None
    visit(schema)
    return deepcopy(schema)


class MCPToolAdapter(Tool):
    max_result_chars = 12000
    marker = '\n[MCP result truncated; omitted content was not fully processed]\n'

    def __init__(self,manager,server,definition):
        self.manager,self.server,self.remote_name = manager,server,definition.name
        self._name = f'mcp__{server}__{definition.name}'
        if not TOOL_NAME.fullmatch(definition.name) or len(self._name)>64:
            raise DefinitionError('Invalid or overlong MCP function name')
        self._description = definition.description or 'Call an allowed tool on a trusted local MCP server.'
        if len(self._description)>4096:
            raise DefinitionError('MCP tool description exceeds 4096 characters')
        self._parameters = check_schema(definition.input_schema)
        self.validator = Draft202012Validator(self._parameters)

    @property
    def name(self):return self._name

    @property
    def description(self):return self._description

    @property
    def parameters(self):return deepcopy(self._parameters)

    async def execute(self,**kwargs):
        try:
            json.dumps(kwargs,allow_nan=False)
            valid = self.validator.is_valid(kwargs)
        except (ValueError,TypeError,RecursionError):
            valid = False
        if not valid:
            return ToolResult(success=False,error='Invalid MCP arguments: input schema validation failed')
        return await self.manager.call(self.server,self.remote_name,kwargs)

    @classmethod
    def result(cls,result):
        if getattr(result,'result_type','complete')!='complete':
            return ToolResult(success=False,error='Unsupported MCP multi-round result')
        if any(block.type!='text' for block in result.content):
            return ToolResult(success=False,error='Unsupported MCP content: only text and JSON structured content are supported')
        parts = [block.text for block in result.content]
        if result.structured_content is not None:
            try:
                parts.append(json.dumps(result.structured_content,ensure_ascii=False,allow_nan=False))
            except (ValueError,TypeError,RecursionError):
                return ToolResult(success=False,error='MCP structured content is not safe JSON')
        text = '\n'.join(parts)
        truncated = len(text)>cls.max_result_chars
        if truncated:
            text = text[:cls.max_result_chars-len(cls.marker)]+cls.marker
        # Error bodies can contain credentials: do not forward them to debug error logs.
        if result.is_error:
            return ToolResult(success=False,error='MCP server reported a tool error',metadata={'mcp_error':True})
        return ToolResult(success=True,output=text,metadata={'truncated':True} if truncated else {})
