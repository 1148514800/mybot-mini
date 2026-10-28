# AI_HANDOFF

## 当前目标与状态

codex/coding-project-launch，基线f9fe98d06975fb0770b55a133f4b127a9a85d60a。真实项目Web入口开发完成；新增--workspace和--check，相关离线专项125通过（新增启动专项24），真实模型0，不创建Canary/冻结或完整Benchmark。

## 实现与权限

mybot/web/launch.py只读校验JSON、默认Provider/字段/声明顺序、规范化路径、Git根/HEAD/Index。缺失/非法路径拒绝，支持linked worktree、detached/unborn；禁用hooks/fsmonitor/filters与可选Index写锁，不执行项目代码。JSON错误固定CONFIG_JSON_INVALID+行列，检查不输出Key/URL、不构造SDK/WebRuntime或打开Session数据库。

mybot/web/__main__.py在预检后才导入/启动服务；覆盖仅dataclasses.replace本进程workspace，不写配置。mybot和agent包延迟导入，保证JSON错误不会抢先终止--check，公共AgentLoop/ContextBuilder/Session/run_gateway身份不变。

Web runtime项目模式不初始化目录/instructions；原配置的Coding/Patch/Receipt/RunCommand权限保持，--workspace不升级写权限。侧栏/设置显示项目名、Git启动分支和Coding/Patch状态。原WorkspaceLease、工具根目录限制、WebApproval及Seatbelt不变，网页消息不可切换workspace。Provider Chain共享纯配置顺序/字段校验，与上轮功能兼容。

## 验证与限制

启动专项24+原Web/Patch/审批与Failover/Streaming相关专项125通过；Python编译、JS和diff检查见交付。包括默认/覆盖/不存在/非法/不可访问目录、Git损坏与恶意filter不执行、JSON/字段/脱敏、预检不启动服务、Mock真实源码读取、无自动文件创建、workspace消息拒绝及Lease互斥。--check只验证本地字段，不证明远端Key有效；没有真实API验证。Git分支为启动快照，不实现运行中多项目切换。

先前主仓库真实配置有JSON语法错误；本次只读语法检查已为合法JSON，未改动该凭证文件。配置及命令详见README、docs/coding-project-launch.md。新项目根必须预先存在并为Git工作树，状态数据库必须在项目之外。

## 下一步与保留

本轮只交付入口功能，Commit/Push到codex/coding-project-launch并核对远程HEAD。不拆Phase、不新建Tag/ZIP。C01/C02报告、旧私库/冻结/账本及14次余额不修改或复用；main/用户服务/Chrome/共享AppleDouble不操作。实际使用时由用户配置Coding写权限并逐条批准测试命令；未来真实模型验证仍需明确授权。
