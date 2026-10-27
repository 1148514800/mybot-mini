# Trusted Steer source

原Web Cookie/Origin/CSRF和runtime.steer负责可信用户输入；UAT只允许冻结文本、Case、Session和expected_turn_id，单次提交。SteerInbox写source=user的steer.queued，保留source_event_id、steer_id、turn_id、sequence，不赋予Pin/审批/工具能力。

SDK观察器按当前Session读取真实queued事件，在内存构造原生reference并以role=user和完整原文精确比较。助手复述、同文其他Session、只有文本命中而没有Source ID均不构成来源证据。报告输出匹配布尔、来源ID及hash，不提交实际请求或完整私有消息。

初始request hash在DOM Steer接收及close时比较，wire messages与实际SDK messages hash比较；不得修改当前请求。T02排队但无下一步仍not_applied，不以语言偶然变化声称在途Steer生效。
