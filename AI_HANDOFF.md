# AI_HANDOFF

## 当前状态

Phase25在codex/phase-25完成开发、36槽实测及证据汇总。标准执行提交b008f35563c266d89ebbdd67a3c31607f9c47819；停止边界修复29fedef；外部任务提交e7a1f396ffe95acfb52e10277b09287649c3e193，最终报告提交由phase-25 Tag解析。不得再跑标准付费任务，不Push/Merge，不进入Phase26。

## 验收结论

原916+新增33=949项/25套件通过，编译通过。标准15/36完整成功（9/12、6/12、0/12）；Judge隐藏31/36。13次审批等待取消混杂后两轮，Journal26文件不匹配，稳定性未验收。标准实际批准18次，不含外部审批；原始失败不删除、不重跑。外部项目6请求/5响应，第6次90秒超时，无修改/Agent测试，泛化未通过；外部宿主审批6次，总yes24次。

## 核心文件与边界

coding_campaign负责冻结/started-raw-finished/SHA/严格统计；coding_supervisor继承真实TTY单槽进程，中断/未完成命令调查后才能继续。原Loop/Controller/工具/审批/Seatbelt/Judge/Benchmark均保持。外部入口只规范化宿主临时根路径，不放宽模型cwd。

## 证据与下一步

学习docs/phases/phase-25.md；完整验收和36报告索引docs/reports/phase-25，SHA清单不可忽略。phase-25仅封存工程与真实结果，归档及还原实际验证回执伴随ZIP保存，原Phase24 Tag/ZIP及main两处用户修改保持。后续优先审批取消生命周期/归属证据、预算收尾、Patch契约；新干净稳定性Cohort必须另获授权，不能用本轮受干扰数据宣称模型下降或优化因果。
