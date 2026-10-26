# Remaining risks

1. 本次真实终到端Streaming FAIL，具体协议拒绝分支UNKNOWN。observer的stop不等于可信终态；缺少逐块脱敏shape与异常分类限制根因定位。
2. 正常关闭SIGINT launcher等待25秒超时；随后已释放资源但退出码/方式UNKNOWN，Case仍running。不能以最终端口空闲倒推正常退出成功。
3. R02真实Tool Call分块组装、跳过工具executed=false、Steer原文与来源进入下一请求及真实语义全部未验证；R03 not_applied/R04取消未验证。
4. Usage缺失，真实供应商Token与费用UNKNOWN，cost=null。本次8次是物理请求上限，不是美元硬上限。
5. Browser DOM首次观察与Provider monotonic未校准，差值UNKNOWN；当前可见预览的局部成功不能代表所有长度/敏感边界体验。
6. 原模型部署窗口未知、Token仅估算；2730不能写成供应商输入Token。本批次HALT，剩余7次没有继续执行权限。
