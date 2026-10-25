# Persistent Session Live UAT — Playwright execution 01

本轮按冻结合同一次执行L01→L02→L03，三个Case的Task、Workflow与Safety均PASS。真实页面操作、真实DeepSeek回复、持久账本及SDK请求证据共同支持结论；这是本批次结果，不是通用长期记忆能力保证。历史OFFLINE/BLOCKED记录不变。

- 输入HEAD：`4e10abda3a89d2b598d4d343a49240efa621234e`；分支：`codex/persistent-session-live-uat`。
- Preregistration：`86105406ed46c32024a4c8d7d669eaaf6ca0be10`；复用原20261025批次、原配置、workspace、两库、消息、Pin跨度、评分与预算。没有prepare/freeze/new ledger。
- 用户授权：GRANTED_16_REQUESTS、隔离共存及终端Python Playwright。操作员环境例外已明确记录，不声称与以前的浏览器前置条件逐字相同。
- 真实入口：冻结server→正式create_app→ChatRuntime→AgentLoop；发消息/Pin创建替换撤销全部是Playwright DOM交互。只读GET/SQLite用于核验；没有模型直连评分、补跑或临时提示。
- 14/16物理模型请求：L01=9/10、L02=4/4、L03=1/2；每Case一次Attempt，均finished。DeepSeek14、GLM0、模型摘要0、失败0、付费Judge0；HTTP模型发送尝试14。
- 供应商Usage：输入31,348，输出10,497，总41,845 Token；`cost=null`，没有可信账单价格。

L01最终回复与L03重启后的新回复均保留“仅本地扫描”“不得自动删除或修改原Markdown”两项早期边界；全文搜索、索引格式、哈希算法、缓存策略仍待定/未实现。首条SQLite来源始终存在，两条Pin均实际进入末轮请求。发生确定性上下文压缩/省略，但没有Pin遗漏，所有模型finish_reason=stop，无输出截断。

L02第三轮采用catalog.md，旧Pin superseded、过期修订真实UI返回409；撤销后第四轮无active命名Pin，模型明确将历史命名与当前有效要求分开。移除整个来源轮产生3项、累计5项原用户信息来源损失；部分事实经助手复述继续留在请求，详见独立分析，不能称为物理遗忘。

L03实际退出并重启服务，L01的ID、标题、18条消息、两Pin、最后turn及事件计数在继续前精确恢复。启动/打开页面没有模型请求；旧Approval/Receipt/verified未恢复、无工具重放。唯一冻结消息后第14次真实请求成功继续讨论。

独立0700 Chrome配置文件及双向Cookie/LocalStorage探针通过；用户Chrome未关闭或操控。8765在本轮检查时已无监听，仅残留停止launcher/defunct子进程；没有操作它，不能据此宣称此前内存会话仍存在。UAT服务全部正常退出、锁释放、临时浏览器profile清理，无执行不确定、源码/配置/workspace污染。

主要产品问题是整轮撤回损失无关用户来源、助手复述仍可影响后续，以及非冲突Pin被统一标为needs_review。另有建议升格为决定、模型误解释Pin生命周期和verify固定显示0请求的诊断问题。详见case-results、semantic-adherence、information-loss-analysis、security-audit与JSON证据。
