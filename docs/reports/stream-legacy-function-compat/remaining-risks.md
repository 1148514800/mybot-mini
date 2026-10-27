# Remaining risks and Live boundary

1. D01实际legacy字段值未保存，无法证明它为空；本轮只确认可达代码分支与SDK空对象缺陷，原FAIL保留。
2. 新逻辑尚无新的真实DeepSeek/GLM证据。SDK默认construct解析宽松，未来字段/版本变化应继续保守拒绝并单独验收。
3. 空legacy兼容不是全面放宽协议；未知extras可能来自兼容供应商，但不能自动取得执行权限。
4. 本轮没有实现所有Provider差异或通用协议转换；观察Usage与可信结算Usage必须分列，账单价格未知时cost=null。
5. 同钟浏览器延迟与SDK时刻分属时钟域，不相减。Mock延迟不是Provider性能。
6. 独立profile和正常退出仅证明本次环境；未来D02前仍需重新核验端口/Lease/进程/库和浏览器身份。
7. D02未授权、真实请求0；单次预算包含失败与备用，不能继承D01旧额度或为补Usage重试。

8. Push时Git尝试解析外置盘共享对象目录的._pack…idx并警告non-monotonic index。只读核验其magic=00051607（AppleDouble），正式idx magic=ff744f63且git verify-pack exit0；未删除/移动/修改共享对象库旁文件。推送成功且远程HEAD核对一致，冻结verify通过。该文件何时被OS创建未归因；未来Git操作仍可能出现同类环境警告。
