# 共存执行安全审计

- 本轮明确记录ALLOW_ISOLATED_WEB_COEXISTENCE=GRANTED；这只替代操作员“无其他MyBot进程”条件，不改冻预算、消息、Pin跨度、评分、源码或硬门。未因空闲launcher存在而停止。
- 实时ps/lsof只发现同UID501的39852 uv launcher，cwd为旧post-live-quality-hardening worktree；其子39853 defunct。此前60449/60450已不在，本轮8765无监听；原因未调查，不归因于本次操作。没有发送任何信号、关闭/重启/修改旧服务或用户浏览器。
- 未认领/读取/改动8765页面、聊天、Cookie、设置窗口或原Chrome配置。旧内存会话当前是否仍存在无法在不访问且无旧进程情况下证明；本轮未对其造成修改或主动丢失，不声称旧服务仍在运行。
- 仅读取必要进程/cwd/open-file/path元数据与原冻结配置中的workspace路径；原配置本来由verify只读校验，没有输出Key或端点。配置旧workspace与UAT解析后为不同真实目录；这是配置路径核对，不冒充不存在旧进程的运行时查询。lsof未见进程打开UAT两个DB，原WorkspaceLease可用，8889空闲。
- 浏览器能力枚举不改变Chrome用户profile。实际测试仅在IAB的8896非生产页面，使用自己的专用Cookie/LocalStorage标记，不用mybot_browser；新标签共享标记，无法作为独立上下文证明。没有启动8889 UAT服务、SDK或Case来试探授权Cookie。
- 两个探针标签和自己的本地HTTPServer已清理，未删除任何用户Cookie或其它LocalStorage项。测试截图不含凭证、聊天或原始Prompt，探针脚本只在/tmp，源码未更改。探针零模型调用。
- 原verify再次通过；同一freeze/prepared/config/source/DB inode/workspace保持。真实ledger case/reservation/halt均0，event DB完整且0事件；没有prepare/freeze、新账本、Case补跑或预算扩大。
- 既有OFFLINE/BLOCKED/recovery-execution-01保持；只新增coexisting-execution-01和更新交接。提交前校验文件SHA、diff和真实凭证字节匹配，无SQLite/凭证/CSRF/Receipt/聊天导出入Git，不改main/Tag/ZIP。
