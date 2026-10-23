# AI_HANDOFF

## 当前状态

真实用户Web UAT已完成一次性执行与只读评分，结论UAT NOT PASSED。基线e3bfc897363b766c5cfacba62f571a26657898f4，分支codex/real-user-task-uat；冻结提交f7a2c00e3739525375c22b0c21f76ade57249ef5，报告为本快照所属docs提交。产品mybot/、依赖与安全策略未改，不合main、不改Tag/ZIP。

## 真实结果

六案例全部执行，无补跑或第七任务。整体UAT1/6、Task1/6、Workflow2/6，Coding0/2。U01正常中文问答PASS；U02记住三轮但增加硬规则FAIL；U03找到真实入口却未使用要求的代码搜索工具且bool说明矛盾FAIL；U04受Fixture属组前提BLOCKED；U05首次Patch preflight失败、确切类别未知FAIL；U06两次摘要均未应用、规则回退与最终主要约束保留，语义要求FAIL。

全批26/48物理reservation、26可观察HTTP、26逻辑请求，全部coco/deepseek-v4.1-flash，GLM0，Fallback NOT_TRIGGERED。Provider输入67179、输出9339、总76518 Token，Usage完整，费用null。摘要2次消耗6452 Token，分别summary_does_not_fit和输出length/不完整JSON；不能称语义压缩成功。

Preview成功0、Receipt Commit0、Agent命令/测试0、Controller verified0；实际浏览器批准/拒绝0/0，因为两个Coding任务均未到审批。操作员后验公开/隐藏断言仅为只读Seatbelt评分，仍失败，不计Agent工作流。未出现不确定执行或文件污染；六工作区全部文件/Index/HEAD内容哈希未变，原Session用户消息SHA匹配、配对正确、没有持久化摘要。

## 架构、验证与证据

新增仅scripts/uat预算适配、预注册/Fixture/oracle、真实Web启动与私有观察，以及scripts/check_real_user_uat.py；生产执行器仍原create_app/ChatRuntime/AgentLoop/Provider/Controller/Registry。持久SQLite事务在SDK调用前reservation，HTTP单次门覆盖延迟创建的备用模型、摘要与取消；固定2/4/6/14/14/8，结束后账本封存，不使用剩余22次。

六指定专项209项+UAT13项=222项通过，compileall/diff检查通过；本轮未重跑历史完整1354。真实浏览器完成所有发送、连续会话、空会话隔离状态与工具卡片；无模型Smoke或Benchmark。2160个历史保护文件、main与Tag不变，原工作区用户改动保留。

报告docs/reports/real-user-task-uat含完整六例、预算/Usage/审批、失败与UX、截图、SHA及建议。私有原始资料与已封存账本只在/tmp/mybot-uat/batch-20261022，不提交真实配置/Key/Receipt/nonce或完整会话。

## 重要归因与下一步

U04实际文件uid501/gid0而服务egid20，原Patch只读check_metadata返回unsupported_ownership。Fixture继承/tmp属组，在冻结前未用原Patch预检覆盖，是本轮UAT工程缺口，不能据此否定受支持目录的Coding能力。冻结后未chown或补跑。U05同属组风险存在，但实际错误事件类别null，不能套用根因；原始工具参数/结果未保留，归因受限。

产品问题：安全停止诊断粗化/缺失，真实摘要产生费用后未适配剩余空间/输出限额，以及需求来源混淆/回复冗长。后续优先补测试前提检查、安全reason展示、摘要尺寸控制与工具/需求引导。Receipt成功、浏览器审批、Agent unittest/当前Revision验证和GLM恢复本轮NOT_VERIFIED。

不得重启此批、改标准或补跑失败Case；不得使用剩余额度。任何后续Live需新任务与明确新预算。当前不宣称全面日常READY；先解决工程前提与已观察问题，保留所有失败分母。
