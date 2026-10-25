# Real browser, offline synthetic acceptance

真实headed Google Chrome152.0.7977.83由外部Python Playwright1.64.1控制；全新0700非符号链接profile、初始空Cookie Jar、实际user-data-dir参数核对、chromium_sandbox=True。没有复用用户profile，没打开8765或真实Provider。只启动8897临时合成服务，显式SyntheticClient和独立SQLite/workspace；生产Origin/Cookie/CSRF/CSP不变。

|场景|真实页面操作及实际请求核验|结果|
|---|---|---|
|A 兼容Pin|用户发送两核心约束，页面分别确认；两active、multiple_same_category、needs_review=false，中性UI|PASS|
|B 替换|发送公开旧命名+3事实，固定；新命名+2事实后页面替换；实际第三请求含全部5事实、仅新active Pin，旧来源精确遮蔽|PASS|
|C 撤销|页面确认撤销新Pin；实际第四请求无active命名Pin，五项user事实仍在，两来源跨度遮蔽，Web显示历史筛选|PASS|
|D 重启|正常退出自己的服务后重启，原id/title/messages/pins相同，启动0自动请求，无approval/report/contract恢复；新请求仍保留5事实|PASS|
|E 工具历史|真实AgentLoop执行合成模型请求的本地只读list_files，配对完成；固定并撤销该user短句后，下一请求整体省略1协议轮/1user；无孤立call/result|PASS|

最终验收运行9次SyntheticClient请求；不是真实模型请求。记录的全部9个实际请求另经严格tool_call_id检查，无孤立结果或未回答调用。任务正确性是机制/协议断言，不是DeepSeek语义得分。截图展示合成页面固定状态和投影诊断；不以截图代替SDK请求核验。

驱动开发中两次等待错误已修正：首次wait_for_function被原CSP拒绝，改为原生locator轮询；第二次误等空输入框Send按钮可用，改正等待。没有关闭CSP。另有两次成功合成运行用于功能/截图检查（包括最终运行，共3次完整通过）；全部5次驱动运行合计29次合成请求，最终验收运行9次，不补跑任何原Live Case、不消耗真实额度。每次自己的服务/profile均清理，最终Chrome PID确认已退出，8897无监听。

脱敏browser-evidence.json只含布尔、计数、版本、哈希和合成session ID；完整临时请求、Cookie、CSRF、Chrome profile不提交。
