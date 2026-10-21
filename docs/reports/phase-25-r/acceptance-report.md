# Phase25-R：取消生命周期与评测可靠性修复

## 边界与基线

本轮为Phase25归档之后的离线后续修复，不重写原归档。起点8acf9ab58752e3e1b7162f4d967dc6f67cc1233a，分支codex/phase-25，工作树起始干净；标准Harness b008f35563c266d89ebbdd67a3c31607f9c47819。原949项、25套件保留。没有真实模型API、付费Live或外部项目模型复测，没有修改任何模型配置、API凭证、main或用户文件；不归档、不Push、不Merge、不进入26。

Phase25-R只修复评测执行可靠性，不提高或重新解释历史模型成功率。新的标准Live须单独授权，并新建以当前配置coco/deepseek-v4.1-flash为基线的独立Cohort；不能复用或拼接原coco2/gpt-6-astra的36次结果。

## 1. 历史证据重建

使用只读`uv run python -m scripts.audit_phase25r`重新校验原evidence-sha256.json的170份文件，以及manifest、每槽started/raw/finished的Run ID、配置SHA、来源SHA及报告SHA；结果另存[historical-audit.json](historical-audit.json)。旧报告没有重写。历史Campaign ID为1d3391f2119645c2adeb2a07cf2f2641，配置SHA为4744178d9d033a202e1b09518c167218309f7b8ceb5031de3357a2967562ca54。审计JSON保留每次取消的起止时间及raw SHA。

36次全部留在分母。Agent verified及严格完整成功均15/36；Judge hidden_pass为31/36，Judge verified_repair为18/36。差额包括13次取消及3次已通过真实测试、但未完成Agent收尾的预算耗尽。不能剔除13次取消后宣称模型成功率提升。

13次取消都具有task_timeout、Controller task_interrupted、Controller command_attempts=1、已完成Trace命令=0、已提交Patch=1、Judge hidden_pass、无真实Agent测试、Journal异常。26是13次运行中累计文件记录数，不是26个唯一文件名。每次的异常计数与Judge changed_files如下：

| Run ID | Journal不匹配数 | Judge变更路径 |
|---|---|---|
| r2-validation-chain-001 | 3 | app/normalize.py, app/service.py, app/validation.py |
| r2-cache-sync-001 | 2 | app/cache.py, app/service.py |
| r2-parse-convert-001 | 3 | app/conversion.py, app/parser.py, app/service.py |
| r2-error-retry-001 | 3 | app/client.py, app/policy.py, app/transport.py |
| r3-pagination-001 | 1 | app/paging.py |
| r3-file-recovery-001 | 1 | app/storage.py |
| r3-config-default-001 | 1 | app/options.py |
| r3-csv-export-001 | 1 | app/formatting.py |
| r3-timezone-day-001 | 1 | app/parsing.py |
| r3-cli-precedence-001 | 2 | app/cli.py, app/configuration.py |
| r3-cache-sync-001 | 2 | app/cache.py, app/service.py |
| r3-parse-convert-001 | 3 | app/conversion.py, app/parser.py, app/service.py |
| r3-error-retry-001 | 3 | app/client.py, app/policy.py, app/transport.py |

原始报告没有保留审批输入线程堆栈或逐次审批读入回执。“这些运行在审批等待中断”的归因由上述计数、约600秒时长、原生审批代码与操作事件checkpoint-supervision-incident.json共同支持，不能冒充每次均有堆栈级直接证明。没有原始after-hash证据可以事后恢复这26项的真实Journal归属，本轮不补写历史归属。

外部项目独立报告证实6次请求/5次响应，Controller stop_reason=model_request_timeout，0 Patch提交、0 Agent测试；不能仅凭脱敏元数据区分网络、Provider排队或服务端超时。原先0模型请求的路径别名失败也保留，不混入标准36次。

## 2. 已证实的根因和已有修复

- 原b008f35编排只拦截execution_uncertain，没有拦截cancelled/task_timeout，因此继续后续槽位。29fedef已补runtime/cancelled/未完成命令停止门，以及继承真实TTY的单槽子进程；本轮保留并复用，没有重复实现。
- 旧原生审批通过asyncio.to_thread(input)读取。协程取消不停止线程读TTY，会残留input等待，亦可拖延解释器退出。进程隔离能隔离解释器状态，但没有从根本上提供可取消的输入读入或回答绑定。
- 原Loop在except BaseException中关闭ChangeJournal，close会清空entries；评测器随后从_git_capsule读取归属集合，得到空集合。只读源码和合成Patch→审批取消复现证明该证据丢失路径；与13份历史元数据一致，但不据此篡改历史判分。
- 新增反例从8acf9ab的可信函数源码复现：带runtime_error的伪verified报告会被旧strict_success接受；旧inventory不核对finished.run_id。补充检查还发现blocked完成回执可能在汇总中呈现success，以及Controller时间预算停止未进入审计门。这些是离线反例，不能宣称它们已经在36次历史运行里被利用。
- e7a1f39已把外部临时根规范化为resolve路径，原真实临时Git/合成客户端测试保留；没有放宽模型cwd或Seatbelt规则。没有新的干净标准Live验证。

## 3. 执行身份和取消状态机

`coding_lifecycle.Attempt`是评测层的宿主执行令牌，绑定Campaign/Run/配置SHA及独立UUID Attempt。同一Case在不同Round或新Campaign重试必有新Attempt；不提供自动重放或自动重试接口。

执行路径：started(独占落盘) → active → completed，或active → revoked → settling → cancelled / execution_uncertain。revoke只记录首个终止原因，后续普通返回不能恢复令牌。CodingClient在调用前及响应后检查令牌；BenchmarkAgent在工具调用前及返回后检查。旧响应、工具和清理回调只保留自己实例的Trace，不能切换到新Case；输出前deepcopy，迟到的旧回调不能修改已发布报告。

不再以wait_for是否抛异常作为唯一终止证据：独立Agent Task接受取消，宿主用固定截止点等待清理，即使子协程吞掉CancelledError也不能把返回值当成功。重复取消不打断清理等待；5秒清理预算后仍未settle则execution_uncertain，并隔离保留临时Workspace，不删除仍可能被操作的文件。新的模型请求和后续Case/Repeat/Slot均停止。

外部调用者的CancelledError在有界记录后重新抛出，不记录正常finished。Provider关闭也受有界等待保护；关闭取消、失败或无法确认均不能成为成功。Supervisor仍原样继承真实终端；重复中断也进入kill与有界wait。124表示中断/超时，125表示退出清理无法确认，都不能自动重放。

审批前取消、尚未批准且无执行副作用时可以记cancelled。命令已经批准或Patch执行中收到取消，没有原生可信完成/终止回执时严格记execution_uncertain；即使工具内部尝试了清理，也不编造process_terminated=true。原run_process已有防重复取消的保护清理，本轮不改原安全模块。

## 4. Phase25专用审批

新增`coding_approval.AttemptApproval`：使用事件循环add_reader和os.read，取消时finally移除本次FD reader；不使用后台input线程，不打开/dev/tty或伪造TTY。仍展示原inspectable_command的完整有效命令，仍由原RunCommandTool进行批准后和spawn前校验，仍逐次审批和使用macOS Seatbelt。

新Phase25 Campaign/外部入口要求真实stdin/output文件描述符都是TTY；每条命令生成唯一挑战，用户必须输入`yes <本次随机挑战>`。裸yes、旧挑战、其他Attempt的回答都不能批准新命令。取消使该Attempt永久失效。通用Phase24的cli_command_approval接口不修改；直接评测API未传Campaign身份时保留旧yes协议，但读入同样无后台线程，取消后不启动下一任务。新标准Cohort必须走Campaign入口获得回答绑定；旧网关审批不属于本轮改动。

## 5. Journal证据和清理顺序

BenchmarkAgent在每次工具返回/取消的finally中、原Loop关闭Journal之前，读取原生Journal已提交条目。只保留公开夹具路径、original/final SHA以及valid/pending不确定标志；不保留原始字节、Patch、命令参数、凭证或源码。

顺序为：原Patch准备/发布 → 原Journal after_success → 工具边界采样 → 取消屏障/清理 → 有界文件快照与哈希核对 → 原Controller/原Judge → terminal元数据fsync → 临时目录清理 → raw/finished校验落盘。若直接外部取消，则跳过Judge、先写terminal，再传播CancelledError并保留blocked。未确认清理时不读取不稳定快照、不评分、不删除Workspace。

仅当记录的original SHA与初始快照一致且final SHA与最终文件一致才接受归属。没有Journal条目的变化、哈希不符、pending或失效Journal都继续保留异常；不能从Trace中“Patch成功”或“文件发生改变”推定归属。合成测试证明取消后的正常已提交Patch可以保留准确归属，但取消仍不成功；另有测试故意丢失归属，确认原Judge仍如实报错。

Tool Call ID另有宿主终态账本，只保存ID SHA与工具名及returned/cancelled/not_executed_after_stop状态；取消不是伪造成功ToolResult，未执行调用也不会送回模型冒充执行。原Loop消息配对和真实测试证据检查继续保留。

## 6. 恢复和统计

新manifest/version为3：冻结真实配置中的Provider/模型、完整工具Schema、源码HEAD、Benchmark/Grading/uv.lock/私有配置哈希、预算与平台；另对槽位计划SHA校验。没有修改用户配置或凭证，也没有自动扩大预算。

started、terminal、raw、finished、blocked通过Campaign/Run/Attempt/配置SHA交叉绑定；finished同时记录raw和terminal SHA。已完成不重放，任何started未完成、身份不符、冻结配置/源码漂移、SHA不符或blocked均不能启动下一槽位。V2历史目录仍可只读审计，无法在V3及新模型下继续执行，不自动迁移证据。

strict_success额外拒绝runtime_error、取消/不确定生命周期、取消Controller和Journal不确定。blocked证据优先于表面verified回执，汇总不能把它分类为success。失败分类保留Provider错误、审批取消、任务超时、Patch失败、预算耗尽、execution_uncertain与Journal异常；隐藏测试通过继续单独统计，不代替完整Agent成功。

## 7. 修改范围

新增coding_lifecycle.py、coding_approval.py、check_coding_reliability.py、audit_phase25r.py。修改coding_campaign/coding_supervisor的外层状态、恢复与统计，coding_live的请求前后令牌，coding_metrics的评测子类证据采样，coding_benchmark的任务边界与清理；Campaign和外部入口复用这些边界，外部报告按实际模型标签记录。check_phase增加独立可靠性套件。

Phase24 AgentLoop、CodingTaskController、apply_patch、run_command校验、command_process、Seatbelt、Benchmark Fixtures/Gold/Reference/隐藏测试、Judge及依赖均未修改。没有关闭审批、自动批准真实命令或放宽cwd/超时/沙盒。synthetic_approval仍仅用于离线临时夹具。

## 8. 验证命令与结果

```bash
uv run python -m scripts.audit_phase25r
uv run python -m scripts.check_coding_reliability
uv run python -m scripts.check_coding_campaign
uv run python -m compileall -q mybot scripts
uv run python -m scripts.check_phase
git diff --check
```

新增42项专项全部通过；原949项/25套件保留，固定源码的最终全量991项/26套件全部通过。Phase1/2原断言、Seatbelt/TTY/Journal/Revision/Patch安全回归、mybot/scripts编译和git diff --check均通过。见[验证回执](validation-summary.json)，含各套件数量、42项测试名及固定源码SHA。使用真实内核PTY、合成模型、临时Git仓库、asyncio.Event控制取消/清理及原生Seatbelt真实测试；不访问真实模型。没有新增长sleep等待。

## 9. 资产保留和仍未证明的部分

phase-25 annotated对象44be2dc9f0c2a8efaf8f36181453da5dd17d089a保持指向8acf9ab；phase-24保持指向3f53b05。原phase-25.zip SHA256为2686325f14d47d133e642cb4aeef7db813f3c71771fe224bab43039754beb57c；Harness ZIP为06e7f4d07daa2962d704d29a9479538ed4a8db91f91b9036ce4cdf486a28bf9f。Phase24原ZIP为3c69bb4eb29d982f3f8a9b1c1ea9fe968e098f1e58d3d5a04b8ca7a3fc5f8e09。两处原Phase25 ZIP副本和既有184项保护资产在结束时再次逐字节校验。

历史26条归属异常不能恢复成真实Journal证据。未进行任何新的模型能力、Provider可用性或长期稳定性验证。极端不响应取消的任务/OS进程只能严格隔离并标记不确定，不承诺Python协程取消能强制终止任意代码。SHA用于损坏检测，不是对可同时篡改所有证据的恶意宿主提供认证；同进程Python候选的既有限制仍适用。故本轮不宣称生产安全或模型成功率提升。

当本轮离线回归与资产校验通过后，具备另行授权、在干净提交和真实审批值守下创建DeepSeek独立重复Cohort的工程条件；实际Live稳定性仍未验收，必须另获费用授权。不自动执行。


## 10. 最终本地验收回执

固定12个源码/测试文件SHA后执行最终全量；26套件991项均通过，原949项没有删除或改写。42项新增专项覆盖真实PTY读入取消/旧回答、终止与迟到回调、重复取消/未知清理、Patch与Journal证据、身份恢复、统计及完整正常工作流。外部入口只有本地合成上游+模拟客户端控制流回归，未访问或复测真实外部模型。

结束时184项保护文件、170份历史证据、全部Tag和main引用均再次一致；用户模型配置与凭证未修改。原phase-25 Tag/两种ZIP、Phase24 Tag/ZIP和36次标准/外部历史报告保留。测试故意注入的execution_uncertain不算成功；未知清理的临时Workspace采用保留策略，异常退出也不抹去现场。

本轮创建一个新的本地Phase25后续可靠性修复提交，SHA以当前分支Git记录及本次交付消息为准，避免把自身SHA写入自身。未Push、未Merge、未重新归档、未进入26。源码与测试清单见validation-summary.json的source_file_sha256；开发文档为README、交接、阶段索引及Phase25/25-R学习记录，新增修复验收、历史审计和验证回执；没有任何原始源码/凭证/Patch/模型报文入报告。
