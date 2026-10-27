# Host Acceptance与隔离

10项独立业务验收覆盖title-only、body-only、两处同时命中、混合大小写、输入顺序、重复id、空字符串/空白、Unicode casefold、无命中、输入不变。测试保留在宿主UAT源码内，未放入Agent工作区、工具Schema、README或模型请求；模型不能通过路径越界读取。宿主测试hash在预注册/prepare及完整源码hash中冻结。

复用mybot.evaluation.coding_judge.run_suite，而非另写宿主import。候选源码只作为Image字节读取，复制到新的隔离评分目录；public/hidden测试都来自可信资产，不采用候选改动的断言。在子进程-I/-S启动、实际Seatbelt13项自检通过后，deny-first profile拒绝网络/外部内容/Home私有文件读取，workspace只读、临时目录可写，子进程继承限制。单套10秒/8192字节输出上限，复用原32MiB/512条目临时目录、8MiB文件和进程清理限制。自检失败为grader_error/BLOCKED，不回退宿主执行。

评分仅在Agent Turn结束、服务安全清理之后运行；只返回计数/布尔/固定类别给操作员，不将隐藏名称、预期值或结果注入后续模型。没有付费Judge或任何额外模型调用。

边界：复用的grader检查unittest关键方法完整性、suite数量/token和进程状态，但候选与unittest位于同一受沙盒Python进程，不能宣称对任意解释器篡改已有完备防伪。Seatbelt保护宿主文件/网络边界，功能验收是本固定业务样本的证据。

评分拷贝中的候选与unittest同进程，候选理论上可能观察该拷贝的测试文件；它不是Agent工具工作区，且评分发生于最后模型请求之后、输出不回模型。本实现不宣称对敌意候选提供完备的测试保密或语义防伪。
