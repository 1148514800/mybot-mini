# Real headed Chrome synthetic acceptance — PASS

Playwright1.64.1，Chrome152.0.7977.83，全新0700非符号链接profile，实际--user-data-dir/UID核对、初始Cookie为空，sandbox启用。使用继承TTY的uv操作员拓扑，MockTransport拦截全部SDK HTTP，真实Provider0。没有操作用户Chrome或8765。

|场景|真实页面与Mock SDK证据|
|---|---|
|A|多块文本先显示预览，stop＋自然EOF后completed；1次Mock|
|B|已有预览后合成重复finish，DOM显示“协议结构不兼容”、provider_error，未报成功|
|C|DOM仍显示生成中、EventSource保持打开；自身服务SIGINT退出0、流关闭、端口/Lease释放|
|D|真实页面提交完整分块read_file，读取公开SYNTHETIC-LOCAL-42；不完整参数不执行|
|E|页面Steer queued→applied，原请求不含补充，下一请求包含原文；旧工具配对not_executed|
|F|模拟协议失败写入独立HALT，新消息被409拒绝且SDK计数不变；保持页面时服务正常关闭，HALT保留|
|G|重启后从实际历史按钮恢复C，标题保持、无旧流/工具/Steer重放，不保存部分回复为完整assistant|

最终本次合成运行9次Mock HTTP、9次Mock流关闭、真实模型0。每场景真实DOM元数据/hash见browser-evidence.json，SDK逐请求hash及标志见browser-sdk-evidence.json。只读DOM采集使用已提交操作员脚本的临时副本，未修改应用逻辑、客户端请求或合成Chunk；原始SDK完整Prompt和临时profile不提交。

C服务从操作员开始关闭至exit0约1.777s，F约3.285s；两者均在重新验证自身子进程后补发SIGINT。计时是本机合成结果，不是Provider网络性能。profile已移除、自己服务均关闭；没有强杀、锁删除或其他用户进程操作。

截图只含公开合成内容、状态标签和补充说明。F页面409文字仍为通用“工作区正忙，或本次审批已失效”，未新增专门HALT文案，属于UX限制。合成通过不证明真实DeepSeek协议或Steer语义遵从。
