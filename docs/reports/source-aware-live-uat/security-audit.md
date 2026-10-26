# Security audit

本轮真实模型授权为NOT_GRANTED。默认入口在读凭证/DB/构造SDK之前拒绝；旧GRANTED_16_REQUESTS和非精确字符串均拒绝。所有模型HTTP仅发生于MockTransport；真实DeepSeek/GLM/摘要/Judge0。原剩余额度未用。

生产mybot/、旧uat/uat_v2/persistent_uat Harness、依赖与旧报告的Git差异为零；不合main，不改Tag/ZIP/Live评分或模型回复，不访问原私有Live DB。只新增本专题隔离适配器、离线检查和文档。Provider配置只读，在内存检查模型/凭证存在；不复制真实凭证文件，端点只导出hash，远端有效性未验证。

新batch/workspace/SQLite独立。唯一prepare、唯一freeze绑定干净Preregistration提交、源码、计划、配置字节/端点、workspace指纹、DB dev/inode与浏览器proof；冻结后仅verify，不修补或替换。实际账本和事件库均空，DB权限0600/private目录0700、integrity ok、无未结算/不确定执行；lease正常获取释放，不删除锁。

所有Case消息、Pin操作顺序/来源跨度、评分、单位与4/4/2+10上限已固定。借额、重跑、非法输入、工具调用、摘要、隐式重试及认证异常fail-closed；回退与失败共用原独立ledger。异常SDK回复的Usage另留私有计数证据，确保停止时也不伪造Token。

新只读Source Preservation不修改SQLite或Session，不以助手/摘要/最终答案推断原user保留。报告只含公开冻结user输入、哈希/计数、脱敏fixture来源和非生产截图，无完整模型Prompt、Cookie/CSRF、Receipt、nonce、API Key、私有SQLite或用户原项目。

后续授权仍必须重查动态进程/端口、workspace/DB/锁隔离和新浏览器身份。当前离线准备通过不能代替未来Live时的环境证明；不得自动升级授权。
