# AI Handoff

## 当前状态

Phase09归档保持不变：phase-09→1ea3b6d77b50f6af2c3a82ad64bae42cebaeef0f，../mybot-mini-snapshots/phase-09.zip。本次完成评测诊断补充，非Phase10；不移动旧Tag/ZIP，不自动Push。用户明确授权真实API，本次仅做有界4任务复核。

## 修改

- evaluation/diagnostics.py：区分空输出/坏JSON/代码围栏/额外说明/结构或字段错误；证据按位置与缺失组诊断；文档字段/数组差异和大小写空白诊断。默认不保存实际值、原文、错误全文。
- grader.py：格式失败review_findings=null，不伪装成真实漏报；汇总不可评分数量与有效评分分母，严格task_success未放宽。
- artifacts.py、runner.py、CLI：显式--retain-artifacts目录才保存当前内置合成案例的最终回复与评分指定产物，单文件100KB、拒绝越界/符号链接/自定义案例，屏蔽配置Key/常见凭证；唯一目录+哈希，留存失败单独记录。runs继续忽略，默认不留正文。
- trace.py记录安全finish_reason；runtime诊断显示整例75秒/模型请求60秒/ReAct16及输出上限信号。check_diagnostics.py新7项，统一回归接入；README与docs/evaluation-diagnostics.md说明。

## 验证

新7项、原33项评测及全部Agent回归通过，编译与归档安全测试通过。真实API复核：auto/guided×两复杂任务×1，15/40请求，无超时，29564总Token；报告runs/evals/live-20261014T160909-832f9c2c.json，opt-in产物runs/evals-artifacts/，均不提交。

两组task0/2/clean2/2：Auto审查最终输出含分析文字而非纯JSON（留存复核为json_with_surrounding_text）；Guided命中全部4项标注，额外报告utils.greeting类型校验问题。Auto文档额外把未批准Python提案列为过期；Guided文档主要是“do not upload personal data”等同义改写与严格值不匹配。真实结果未伪造，不因此放宽评分。

## 局限

诊断不是语义Judge，未标注位置/证据未匹配仍需人工确认。旧报告无原文/产物不能补恢复。仅Opt-in合成输出留存，凭证屏蔽不是通用隐私识别，不用于私人基准。报告version2加diagnostic_version1，格式失败不进入质量分母，旧分母不可直接混比。用户Live复核在提交前执行，报告git_commit为当时基线422831c。

## 环境与用户修改

macOS、Python3.12+、uv。默认Offline；Live必须显式。app.py/USER.md改动保留不提交；不输出真实配置/Session，不保存工具转录/Skill正文。COPYFILE_DISABLE=1减少AppleDouble，归档排除。

## 下一步

本次诊断补充完成；下一步由用户指定。不进入Phase10，不覆盖旧报告/Tag/ZIP。使用docs/evaluation-diagnostics.md中的可选留存命令复核后续结果。
