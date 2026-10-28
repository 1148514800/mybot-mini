"""Tool batch dispatch, argument parsing and bounded host event projection."""
from __future__ import annotations

import json
import time
import unicodedata
from typing import Any
from ..tools import ToolResult


async def _execute(self, name: str, raw_arguments: Any) -> ToolResult:
    if self.tools.is_metadata(name):
        return await self._execute_tool(name, raw_arguments)
    error = self.plan.execution_error()
    if error:
        return ToolResult(success=False, error=error)
    if self.discovery is not None and self.discovery.is_mcp(name) and name not in self._request_visible_names:
        result = ToolResult(success=False,error='mcp_tool_not_visible_in_request; search and activate it, then wait for the next model request')
    else:
        result = await self._execute_tool(name, raw_arguments)
    from ..tools.patch import ApplyPatchTool
    from ..tools.run_command import RunCommandTool
    self.plan.observe(name, result, native_command=(name == 'run_command' and type(self.tools.get_tool(name)) is RunCommandTool), native_patch=(
        name == 'apply_patch' and type(self.tools.get_tool(name)) is ApplyPatchTool))
    return result


async def _execute_tool(self, name: str, raw_arguments: Any) -> ToolResult:
    from .task_contract import ContractTool, MAX_BYTES
    if name == 'record_task_contract' and type(self.tools.get_tool(name)) is ContractTool:
        from ..tools.arguments import parse_object
        try: arguments = parse_object(raw_arguments, max_bytes=MAX_BYTES)
        except ValueError: return ToolResult(False, error='contract_proposal_rejected')
        return await self.tools.execute(name, arguments)
    from ..tools.run_command import RunCommandTool, parse_arguments as parse_command_arguments
    if name == 'run_command' and type(self.tools.get_tool(name)) is RunCommandTool:
        try: arguments = parse_command_arguments(raw_arguments)
        except ValueError as exc:
            return RunCommandTool.failure_result(str(exc))
        return await self.tools.execute(name, arguments)
    from ..tools.patch import ApplyPatchTool, parse_arguments, patch_diagnostics
    if name == 'apply_patch' and type(self.tools.get_tool(name)) is ApplyPatchTool:
        try:
            arguments = parse_arguments(raw_arguments)
        except ValueError as exc:
            patch_tool = self.tools.get_tool(name)
            if patch_tool.preview_receipt: patch_tool._revoke_receipt()
            result = ToolResult(False, error=str(exc), metadata={
                'status': 'preflight_failed', 'failure_phase': 'argument_parsing', 'applied': False,
                'execution_evidence': False, 'safe_to_retry': False,
                **({'patch_protocol': 'receipt', 'receipt_created': False, 'receipt_commit_attempted': None,
                    'receipt_commit_success': False, 'receipt_error_category': None,
                    'preview_to_commit_consistent': None, 'file_revision_verified': False}
                   if patch_tool.preview_receipt else {}),
                'input_feedback': {'version': 'patch-input-v1', 'issues': [{'field': '$', 'category': 'invalid_json_object'}],
                    'action': 'supply_bounded_unique_key_json_object; intent_unknown_no_retry'}})
            result.metadata.update(patch_diagnostics(result))
            return result
        return await self.tools.execute(name, arguments)
    try:
        arguments = json.loads(raw_arguments or "{}") if isinstance(raw_arguments, str) else raw_arguments
    except json.JSONDecodeError as exc:
        return ToolResult(success=False, error=f"invalid JSON arguments: {exc}")
    if not isinstance(arguments, dict):
        return ToolResult(success=False, error="arguments must be a JSON object")
    if name == 'write_file' and not self.tools.has_tool(name): return self.tools.denied()
    if not self.tools.has_tool(name):
        return ToolResult(success=False, error=f"unknown tool '{name}'")
    schema = self.tools.get_parameters(name)
    properties = schema.get("properties", {})
    for required in schema.get("required", []):
        if required not in arguments:
            return ToolResult(success=False, error=f"missing required field '{required}'")
    for key, value in arguments.items():
        rule = properties.get(key, {})
        expected = rule.get("type")
        if expected == "string" and not isinstance(value, str):
            return ToolResult(success=False, error=f"field '{key}' must be a string")
    return await self.tools.execute(name, arguments)


async def dispatch_batch(self, message, messages):
    controller = self.coding_controller
    debug = self.config.debug
    calls, content = message.tool_calls, message.content
    messages.append({
        "role": "assistant",
        "content": content,
        "tool_calls": [
            {"id": call.id, "type": "function", "function": {
                "name": call.function.name,
                "arguments": call.function.arguments,
            }}
            for call in calls
        ],
    })
    if self.steer_inbox is not None and self.steer_inbox.pending is not None:
        for call in calls:
            messages.append(dict(role='tool',tool_call_id=call.id,content=ToolResult(False,error='not_executed_pending_user_steer',metadata={'executed':False}).to_text()))
        self._notify('tools_deferred_by_steer',count=len(calls))
        return None
    batch_allowed = controller.before_batch(calls) if controller is not None else True
    permission_denied = False
    denial_is_mcp = False
    command_stopped = False
    for call in calls:
        if debug:
            if getattr(self.tools.get_tool(call.function.name), 'private_arguments', False):
                args = '<Coding arguments omitted>'
                if call.function.name == 'write_file':
                    try:
                        value = json.loads(call.function.arguments or '{}').get('content')
                        if type(value) is str: args += f' content=<{len(value)} chars>'
                    except (ValueError, AttributeError): pass
            else:
                try:
                    args = json.loads(call.function.arguments or "{}")
                except json.JSONDecodeError:
                    args = "<invalid JSON>"
                if isinstance(args, dict) and "content" in args:
                    args["content"] = f"<{len(str(args['content']))} chars>"
                if call.function.name.startswith("mcp__") or (self.discovery is not None and call.function.name in self.discovery.tool_names):
                    args = "<MCP arguments omitted>"
            print(f"[CALL] {call.function.name}: {args}")
        if self.steer_inbox is not None and self.steer_inbox.pending is not None:
            messages.append(dict(role='tool',tool_call_id=call.id,content=ToolResult(False,error='not_executed_pending_user_steer',metadata={'executed':False}).to_text()))
            continue
        was_stopped = permission_denied or command_stopped
        if controller is not None and (not batch_allowed or controller.state != 'running'
                or not controller.before_tool(call.function.name, call.function.arguments)):
            messages.append({'role': 'tool', 'tool_call_id': call.id, 'content':
                ToolResult(False, error='autonomy_stopped', metadata={'reason': controller.stop_reason, 'executed': False}).to_text()})
            continue
        tool_started_at = time.perf_counter()
        self._notify('tool_started', tool=call.function.name, call_id=call.id)
        result = (ToolResult(success=False,error="approval_cancelled: earlier call denied")
                  if permission_denied or command_stopped else await self._execute(call.function.name, call.function.arguments))
        if not result.success: self.resources.tool_failures += 1
        if controller is not None and not was_stopped:
            controller.observe(call.function.name, call.function.arguments, result)
        if self.task_contract is not None and not was_stopped:
            self.task_contract.observe_read(self.tools.get_tool(call.function.name), call.function.arguments, result)
            if call.function.name == 'run_command' and result.success:
                self.task_contract.observe_test()
                result.metadata['contract_test_refs'] = list(self.task_contract._tests)
            self._notify('task_contract', contract=self.task_contract.public_snapshot())
        if self._event_callback is not None:
            from ..tools.patch import ApplyPatchTool
            native_patch = type(self.tools.get_tool(call.function.name)) is ApplyPatchTool
            safe_keys = ('dry_run', 'applied', 'status', 'exit_code', 'execution_mode', 'sandbox_applied',
                         'receipt_created', 'receipt_commit_success', 'receipt_error_category', 'diff_truncated', 'authority_denied', 'executed')
            safe_meta = {key: result.metadata[key] for key in safe_keys if key in result.metadata}
            if native_patch:
                for key in ('error_category', 'safe_error_code', 'failure_phase', 'safe_to_retry',
                            'operation_intent', 'file_metadata_supported', 'guidance_code'):
                    if key in result.metadata: safe_meta[key] = result.metadata[key]
            from ..tools.read_file_range import ReadFileRangeTool
            from ..tools.file import ReadFileTool
            native_read = type(self.tools.get_tool(call.function.name)) in (ReadFileRangeTool, ReadFileTool)
            if native_read and result.success:
                safe_meta.update(safe_read_metadata(self.tools.get_tool(call.function.name), call.function.arguments, result))
            preview = result.metadata.get('preview_diff', '') if native_patch and result.success and result.metadata.get('dry_run') is True else ''
            if native_patch: safe_meta['diff_truncated'] = bool(safe_meta.get('diff_truncated') or len(preview) > 12000)
            self._notify('tool_finished', tool=call.function.name, call_id=call.id, success=result.success,
                duration_seconds=round(time.perf_counter() - tool_started_at, 3), metadata=safe_meta,
                diff=preview[:12000],
                changed_files=result.metadata.get('changed_files', [])[:8] if native_patch else [],
                plan=[{'description': step.description[:256], 'status': step.status, 'verified': step.verified} for step in self.plan.steps],
                coding_state=controller.state if controller is not None else None)
        from ..tools.run_command import RunCommandTool
        native_command = (call.function.name == 'run_command' and type(self.tools.get_tool(call.function.name)) is RunCommandTool)
        command_stopped = command_stopped or (native_command and not was_stopped and not result.success and result.metadata.get('completed') is not True)
        if result.metadata.get("permission_denied", False) and not permission_denied:
            denial_is_mcp = call.function.name.startswith("mcp__")
        permission_denied = permission_denied or result.metadata.get("permission_denied",False)
        if debug:
            print(
                f"[RESULT] success={result.success} "
                f"chars={len(result.output)} error={result.error}"
            )
        messages.append({
            "role": "tool", "tool_call_id": call.id, "content": result.to_text(),
        })

    return command_stopped, permission_denied, denial_is_mcp


def safe_read_metadata(tool, raw, result):
    """Validate a local path with repository policy; MCP never calls this helper."""
    from ..tools.repository import RepositoryTool
    try:
        args = json.loads(raw) if isinstance(raw, str) else raw
        target = RepositoryTool.resolve(tool, args['path'])
        relative = target.relative_to(tool.workspace).as_posix()
        if not relative or any(unicodedata.category(c) in ('Cc', 'Cf', 'Cs') for c in relative): return {}
        data = {'relative_path': relative}
        for key in ('requested_start_line', 'returned_start_line', 'returned_end_line',
                    'truncated', 'next_start_line'):
            value = result.metadata.get(key)
            if type(value) in (int, bool) or value is None: data[key] = value
        if type(args.get('end_line')) is int: data['requested_end_line'] = args['end_line']
        data['has_more_lines'] = type(result.metadata.get('next_start_line')) is int
        return data
    except (ValueError, OSError, TypeError, KeyError):
        return {}
