# Live Readiness

当前NOT_GRANTED；本轮仅离线。新唯一C01批次coding-workflow-canary-v1-20261027，固定8903，12物理请求总额/Case额，1 Attempt，SDK retries0；主coco/deepseek-v4.1-flash，备coco2/glm-5.3-flash。失败HTTP、备用和任何SDK发送都计数；summary/JudgeLLM直接拒绝，不继承旧余额。

后续需新精确GRANTED_12_REQUESTS，并复核源码/原配置/Fixture HEAD/Public/Host hashes、两库inode、空Attempt/reservation、Revision-aware Gate、Lease/端口/浏览器身份。唯一输入见preregistration.md。命令批准另由真实用户在原WebApproval逐次确认，模型授权不是命令批准。无人批准则不执行，保留BLOCKED/未验证，不自动批准或额外请求。

入口：`uv run --no-project --with playwright python -m scripts.coding_workflow_canary_v1.browser --chrome <本机Chrome> --output <全新私有目录> --live --authorization GRANTED_12_REQUESTS`。先原冻结verify，再由operator监视真实审批弹窗与预算。浏览器Live不批准；operator应及时提示实际用户在本机独立Chrome核对并确认，不能代点或通过聊天授权伪造nonce批准。

当前最终prepare/freeze/verify身份与0请求状态见budget-evidence.json。无源码或测试修改时仅增加新的live-results/execution-01报告。真正严格成功必须同时满足15维，尤其当前Revision原生测试、独立Host10及真实人批准；只verified或只Public PASS不够。未授权禁止探测Provider。
