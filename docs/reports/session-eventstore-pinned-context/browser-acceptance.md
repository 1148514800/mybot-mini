# 真实浏览器离线验收

使用Codex真实IAB页面（loopback8887）、实际UI按钮/输入/确认弹窗、真实ASGI+AgentLoop+SQLite，模型由scripts.eventstore_browser显式SyntheticClient产生。APFS私有临时数据，不读取生产凭证；不是仅后端Mock请求。浏览器、临时server和已知测试子进程已关闭。截图不含审批nonce/Receipt/生产秘密。

| 场景 | 实际动作和结果 |
|---|---|
| A 重启 | 创建两个会话、多轮聊天；关页面、停止服务、同库重启。恢复标题/消息/Pin，设置面板确认首会话ID f51e6404d4cf478a852d88bf851b1e14 与重启前一致；状态completed，0自动请求。 |
| B 中断 | 新会话“中断演练”；UI批准只写合成PID并等待的真实host_confirm命令。执行中SIGKILL自己启动的server，清理已知fixture子PID，再同库重启。页面“执行结果不确定”、副作用警示、发送禁用；无审批、无verified、活动请求0。全局合成调用计数重启前后同为14。 |
| C 跨轮/撤销 | 固定“不允许第三方依赖”；8轮长消息后实际请求仍含Pin，发生历史裁剪（保留1/摘要5）；撤销后下一实际请求Pin集合=[]。 |
| D 替换 | 重新固定原要求，发送numpy新要求，弹窗明确选择替换；旧项superseded与来源仍可见，新请求仅含numpy新Pin。 |
| E 删除 | 第二会话设置→删除→确认；刷新后列表不再出现。专项额外验证正常API返回404、DB级联移除及重开库无记录；不宣称物理不可恢复。 |

- [跨轮Pin](browser-pin-window.png)
- [重启恢复](browser-restart.png)
- [替换后有效项](browser-pin-replaced.png)
- [确认删除并刷新](browser-deleted.png)
- [真实命令中断恢复](browser-interrupted.png)

SyntheticClient按实际request的PIN_LABEL读取当前有效项并生成可见回复；不访问真实API，不评价回答语义质量。A/C/D/E截图生成后，将面板“版本”更准确命名为“状态修订”，没有改变Pin状态合同；B截图为该收尾版本。完整HTTP状态、SSE/刷新、跨进程缓存删除和context边界同步另有自动化检查。
