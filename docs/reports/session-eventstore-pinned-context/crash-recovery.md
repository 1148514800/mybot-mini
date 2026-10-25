# 崩溃和恢复边界

恢复只读当前namespace，查询pending/running owner_pid。活PID保留running，不自动接管；PID不存在时写turn.interrupted。PID重用会保守误认为仍活，需要检查进程；不以时间猜测任务成功。跨CLI/Web只共享工作区不确定布尔屏障，不共享私聊文本。原WorkspaceLease仍是工作区执行锁；不能删除锁来规避。

| 实际子进程退出点 | 恢复结果 |
|---|---|
| 仅conversation.created | idle |
| 用户消息已提交、尚无turn.started | interrupted |
| 模型请求等待 | interrupted |
| 只读工具已dispatch、未返回 | interrupted |
| 外部副作用工具dispatch未返回 | execution_uncertain |
| 原生Patch Preview完成，未Commit | interrupted；无新文件 |
| 原生Patch Commit完成，回复前退出 | execution_uncertain；文件保留 |
| 文件publish成功，tool.finished尚未提交 | execution_uncertain；文件保留 |
| 原生命令运行中退出 | execution_uncertain；不启动第二个命令 |
| 原生unittest通过，最终回复未提交 | execution_uncertain；不恢复verified |

另有真实子进程在DB事务内修改并触发脏页写盘后os._exit，验证hot journal由SQLite回滚、既有已提交聊天不丢失、未提交内容不出现；陌生库带hot journal不恢复、不改写。

check_session_recovery使用真实子进程os._exit(17)、原Patch/Receipt/命令/unittest；测试不以Mock状态代替这些边界。测试命令的遗留子进程只由fixture按已知PID清理。另验证活owner不误判、重复recover幂等、无自动模型请求和无授权恢复；客户端清理失败也持久化execution_uncertain。

Registry在真实dispatch前提交started，完成后只提交安全元数据。started包含审批等待，因此批准前崩溃也可能保守标为不确定；拒绝/未执行完成元数据则effect=none。即使工具返回成功，只要最终任务没完成且有副作用也保守标不确定。SQLite不能与文件系统发布、外部服务或子进程创建组成原子事务；两者之间崩溃只能如实记录未知。

重启没有模型/命令/Patch重放入口；历史不含Receipt/nonce，不创建旧Controller/TaskContract/Plan/MCP会话/verified。聊天里的旧声明显示为历史文本，恢复模型投影也带“不作为当前执行证据”标记。execution_uncertain阻止同工作区新任务；用户检查文件、Git状态和残留进程后通过Web复核确认或CLI `/review-session confirm WORKSPACE_AND_PROCESSES_CHECKED`记为interrupted。复核只解除保守屏障，不证明旧任务成功、不杀进程、不撤销副作用、不恢复任何授权。

Web最终回复/终态在资源清理后提交，数据库失败不显示永久保存成功。事件已写但UI publication失败时事实保留且不请求模型；SSE断连不回滚事实、不自动批准，刷新重新读状态。关闭/取消沿用原清理与lease屏障。浏览器SIGKILL场景见browser-acceptance.md。
