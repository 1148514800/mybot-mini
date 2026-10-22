# AI_HANDOFF

## 当前目标与状态

Patch Preview Receipt 离线工程已实现，分支 codex/patch-preview-receipt，基线 cc8f00ad661292da0db433324e2ae2e14143b367。源码/专项/全量/安全审计通过；准备 Implementation Commit 后生成独立验收报告并提交、推送。不是 Phase26，不合并 main，不动历史 Tag/ZIP。

## 实现与决策

原生 ApplyPatchTool 新增显式 coding.preview_receipt=true（默认 false，配置为 keyword-only 保留旧位置参数）。Preview 保留一份不可变有界内存快照，返回随机256-bit、最长300秒、单次 Receipt；模型仅用 dry_run=false 与 token 显式提交。消费后重新检查完整内容哈希、inode/版本/元数据、父目录身份、Workspace/turn、权限与时限。复用原 preflight/recheck/stage/publish/recovery/Journal；无新写入器或自动重放。Preview 不增 Revision，成功 Commit 增一次；当前哈希审批测试与 python -c 排除规则保留。

Loop finally 清理 scope；Session 写盘前删除 Patch 参数/结果及可能复制的能力值；Trace 仅记录白名单诊断，不存 token/正文。原关键发布/Controller 方法 AST、Journal、命令审批、Strict 评分代码保持一致。

修改集中于 patch、Loop/Controller、config/registry/app、benchmark flag 传递、metrics 诊断；新增 scripts/check_patch_preview_receipt.py 并接入 check_phase。

## 验证与合成结果

专项53/53；原1187保留，全量1240/1240、34套件、零跳过。单独 Patch61、tool-verification44、live-AB29、failover50、batch25、reliability42 全部通过；compileall/diff通过。12条件×2组均保留失败/取消/预算分母：参数错误 Legacy2 vs Receipt0；两组提交/verified/公开合成合同均4/12；正式尝试均8。原 Strict 只接受 Live，合成不具备资格，计数均0，不将公开合同代理称为Strict。请求33 vs31混有提前停止，不推断真实成功率/节费。权限变化条件 Receipt 更保守，Legacy 可按当前 mode 继续。

真实模型HTTP0，实际操作员yes/nonce0。1034个保护文件校验不变，含原13个与最近8个Attempt raw、历史Phase/报告、53 ZIP/AppleDouble；main和26 Tag不变。原工作区 mybot/app.py 与 workspace/instructions/USER.md 用户修改未触碰。旧实验入口 docs/reports/tool-verification-live-ab/，禁止重放或猜测未保存参数。

## 下一步与限制

生成 docs/reports/patch-preview-receipt/ 验收、架构、离线计数、合成、安全/失败分析与下一阶段方案，完成 Acceptance Commit、独立分支 push、远程 HEAD 核对。供应商 Schema 支持、模型行为、上下文裁剪/TTL、真实 fallback/取消分布未 Live 验证；继承 POSIX 单文件原子发布与多文件 best-effort 回滚限制。下一轮可建议全新8对、同模型/预算、USD5建议硬上限；必须可靠单价、新授权和预注册冻结后另行启动。本轮不消耗旧剩余68次额度。
