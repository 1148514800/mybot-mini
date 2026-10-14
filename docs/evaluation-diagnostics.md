# Evaluation 诊断补充

这是 Phase 09 后的诊断修复，不创建新 Phase 或移动旧 Tag。JSON 主版本仍为2，新增 diagnostic_version=1；严格任务评分不放宽，审查质量汇总仅包含可评分结果。

## 默认脱敏诊断

- review.status：区分 empty、invalid_json、fenced_json、invalid_fenced_json、json_with_surrounding_text、non_object、missing_findings、findings_not_list、invalid_fields、valid_review。
- 只记录 JSON 错误行/列，不记录错误原文或内容。代码围栏包裹可被识别，但不会自动去掉围栏让任务通过。
- field_issues：记录报告项索引及缺失/非法的固定字段名。
- finding_matches：区分命中、已知文件/函数但证据未匹配、未标注位置；记录标注ID与缺失证据组编号，不记录模型的文件名、函数名、证据原文。
- document.fields：定位缺失字段、类型错误、数组项不匹配、仅大小写/空白差异、值不匹配。缺失项只展示基准中的公开合成标准值，实际新增文本只计数。
- runtime：同时显示整项/单次请求超时、ReAct上限，以及供应商 finish_reason=length 是否出现。不自动修改这些限制。

不可解析或结构不合法的审查结果，其 review_findings=null，不再伪装成 TP=0、FN=全部缺陷。汇总 review_unscorable_cases 与 review_quality.scored_cases 说明分母；task_success 仍因格式不符合要求失败。证据未匹配仍需人工确认，不能自动认定语义错误。

旧报告没有原始回复和文件，无法补充诊断或恢复产物；保留原文件。新增的诊断只作用于后续运行。

## 可选合成产物

```bash
uv run python -m scripts.eval_agent \
  --case-ids complex-code-review,complex-document-summary \
  --groups auto,guided \
  --retain-artifacts runs/evals-artifacts
```

加入 --live 才发真实请求，可能收费。开发回归默认不会调用真实API。

默认不保存正文。显式 --retain-artifacts DIRECTORY 后，只允许当前版本内置合成基准：逐案例建立唯一目录，保存 final-response.txt 和评分指定的文件产物。不会复制整个workspace、Fixture、Skill正文、工具转录或真实聊天历史；修改后的自定义案例拒绝留存。

单文件最大100000字节，拒绝越界和文件符号链接；文件来源路径只来自受控基准。retained_artifacts 记录来源、文件名、SHA256、是否脱敏、跳过/失败原因。已知配置API Key和常见凭证格式会被替换，留存内容可能与原始输出不同，不能直接拿脱敏后的文本替代原评分。

留存目录允许人工查看完整的合成任务输出，可能包含模型生成的文字；自动凭证屏蔽不是通用隐私检测器，不应将此功能用于私人基准。默认路径 runs/ 已忽略，不提交留存内容。留存失败单独记录，不冒充成功、不改变真实工具执行语义或任务评分。

## 测试与限制

```bash
uv run python -m scripts.check_diagnostics
uv run python -m scripts.check_phase
```

7项新增测试覆盖解析与字段诊断、格式失败不虚构漏报、证据定位、数组大小写诊断不放宽评分、默认不留存/仅内置案例、凭证屏蔽、大小与符号链接限制、输出Token上限标记。原33项评测及Agent回归仍执行。

字符串和证据诊断不是语义Judge；同义改写是否正确、额外缺陷是否真实仍需人工查看留存产物。没有追加模型分类调用，没有重跑旧报告，没有修改Phase1–9 Tag/ZIP。

## 本次真实复核

用户明确授权后，使用Auto/Guided各跑两个复杂案例一次，max_requests=40、timeout=75，显式留存合成输出。实际15次请求、29564总Token、无超时，两组task均0/2、process_clean均2/2。报告：runs/evals/live-20261014T160909-832f9c2c.json（不提交）。

人工查看留存后，Auto审查包含分析文字及JSON，属于json_with_surrounding_text；Guided审查命中全部4项标注但另报greeting对非字符串输入缺少校验。Auto文档多列一个未批准的Python提案，Guided文档出现同义改写（do not upload personal data、JavaScript language等），说明失败不能简单解释为事实全部错误。严格评分保留，诊断让人工能定位争议。报告生成后补充了额外说明识别，因此原报告status仍为invalid_json；原报告不改写，留存可只读复核。
