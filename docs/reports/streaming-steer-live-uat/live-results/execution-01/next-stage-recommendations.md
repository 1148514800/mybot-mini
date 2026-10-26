# Next stage recommendations

优先在独立开发任务增加有界、脱敏的stream拒绝原因（块序号、字段形状、终态次数与异常类别），在Mock中覆盖真实协议可能差异；不要保存完整模型Prompt/私有回复或放宽终态完整性安全检查。当前证据不足以直接断言应放宽某个特定校验。

第二优先修复并验证操作员对uv/子Python的优雅关闭流程与HALT后的shutdown可观测性。保留真实HALT和Case状态，禁止手工结算来制造PASS。先离线验证正常退出、halt shutdown、进程归属与Lease释放。

修复与离线验收完成后另立新预注册与明确新Live授权，再验证R02–R04；不能补跑本批次或借用剩余额度。后续评分仍分别保留stream协议、真实预览、Steer queued/applied/semantic及取消远端Usage UNKNOWN。
