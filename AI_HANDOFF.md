# AI_HANDOFF

## 当前目标与状态

在独立 `codex/provider-failover` 分支（基于 Phase25-R e35044e）实现 CLI 的 coco → coco2 自动回退。
原 Phase25 冻结工作区、Campaign 和历史报告保持不变；主工作区的两处用户修改不动。
这不是 Phase26，也不重写或重新归档 Phase25。

## 实现

- 新增 mybot/provider_failover.py，app 的客户端工厂启用回退；其他 Provider 或未配置 coco2 时保持原客户端。
- coco 的 OpenAI APIError/超时最多触发一次 coco2 请求；切换后进程内继续使用备用模型，重启恢复主模型。
- 主请求使用原时限一半，为备用保留时间；两者受原 Loop 请求/任务截止时间约束。取消不回退，工具不重放，备用失败不重试。
- 两个客户端关闭 SDK 隐式重试；备用请求先经 Controller.before_request 计数和预算校验。
  Loop 仅新增预算拒绝异常处理，避免把正常预算停止改记成不确定状态；工具、审批、Seatbelt、Patch、Judge不改。
- 评测 build_client 不改，冻结 Campaign 不启用混合模型回退；继续评测须独立授权/版本/评测组，不能并入旧 DeepSeek 组。

## 配置与安全

独立工作区 config/config.json 是未跟踪、被忽略的本地副本，权限0600。
主配置保持 coco/deepseek-v4.1-flash，备用为 coco2/glm-5.3-flash，使用用户本轮提供的新备用凭证。
不在文档、代码或日志保存凭证；原 Phase25 配置及凭证不改。代码与配置副本仅在本工作区生效。

## 验证与限制

新增17项离线测试：成功不切换、API/超时回退、备用自身模型/凭证、粘性切换、备用失败不重试、取消、工具不重放与ID配对、预算、日志和关闭清理。
全量 `uv run python -m scripts.check_phase`：1008项、27套件通过（原991/26保留）；Phase1/2兼容断言通过。
compileall、diff检查通过。写入本地配置后，17项专项及模拟工厂配置绑定检查再次通过。
没有真实API或Live；缺少真实故障切换运行验证，不能声称模型能力或混合模型稳定性通过。
全量原始日志仅在 /tmp/mybot-provider-failover-regression.log，不提交生成日志。

## 下一步

从此工作区运行CLI需用户后续明确的真实调用授权。只创建本地代码提交，不Push/Merge、不移动Tag、不导出ZIP。
原DeepSeek Campaign现有CSV provider_error/blocked证据仍保留，不能删除blocked记录或直接恢复付费运行。
Phase25-R原学习资料见 docs/phases/phase-25-r.md 和 docs/reports/phase-25-r/acceptance-report.md。
