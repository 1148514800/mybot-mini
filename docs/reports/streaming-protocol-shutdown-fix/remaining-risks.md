# Remaining risks

- ORIGINAL_R01_ROOT_CAUSE: UNKNOWN。没有原328块shape/异常记录，不能把合成重复finish解释为真实故障，也不能宣称已修复DeepSeek部署协议。
- SSE连接轮转有250ms重连间隙与本地连接开销；状态和Last-Event-ID恢复通过本轮合成，极端长时间/慢客户端仍需长期观察。
- 原始OSError只能证明迭代异常，不证明远端网络；调用方CancelledError不能单独区分用户Stop和外层deadline。上层保留原timeout/Stop状态。
- 异步清理deadline是合作式边界；不响应取消的第三方协程无法安全强制终止。本轮不引入强杀或虚假Lease释放。
- TTY补发SIGINT基于本机macOS ps/lsof身份核验，有操作员层不可完全消除的检查到信号竞态；出生时间、命令、端口、亲子归属共同收紧，身份无法确认时拒绝。
- 原冻结UAT入口不改，HALT后的verify/Case finish仍可能失败；未来新UAT须把验收失败、HALT和资源退出证据独立建模。
- 合成HALT拒绝仍显示通用409说明；不是新的用户权限或已完成产品级HALT恢复入口。
- 真实DeepSeek Usage、流尾具体变体、真实工具与Steer语义、远端取消计费都未新验证，必须另行新批次/新授权。原7次不得借用。
