# C02 unique preregistration

LIVE_AUTHORIZATION: NOT_GRANTED

Baseline `c56a03813f9a0472d72d96e5bc3915ff667f0d60`, branch `codex/coding-cross-file-canary-v2`; fresh unique batch `~/.mybot-mini/uat/coding-cross-file-canary-v2-20261027/`, 127.0.0.1:8904. Only C02, one Attempt, 18 physical sends globally and per case. Future exact GRANTED_18_REQUESTS, no old C01 allowance.

Unique task, no append/rewrite/resend:

> 请修复 csvmini/parser.py 和 csvmini/report.py，使 parse_records 能使用 csv.DictReader 正确解析带 id、category、amount 表头的 CSV，支持引号和逗号字段，保持 id 原文，去除 category 首尾空白，并将合法金额精确转换为 Decimal；非法或非有限金额、超过两位的小数必须抛出 ValueError。category_totals 必须调用 parse_records，按照类别首次出现顺序精确汇总，返回类别与固定两位小数字符串组成的元组列表，不允许排序或去重。请同时修复这两个模块，不修改其他文件。先阅读代码和测试，使用原生 apply_patch 预览、Receipt 提交，然后运行 python -m unittest discover -s tests -v。测试失败时不得声明修复完成。

Official path create_app → ChatRuntime → AgentLoop → CodingTaskController → ToolRegistry → ProviderFailover → SDK Streaming. coco/deepseek-v4.1-flash; backup coco2/glm-5.3-flash, stream/include_usage true, retries0. coding write, generic access read_only, preview_receipt true, macos_readonly command, autonomy/git workflow true, Undo false. Steer enabled but unused. MCP/Skills/model summary/Judge off.

Budget fixed before freeze: ReAct/model18, tools64, patch-write attempts3, commands3, no-progress4, native task900s, Web1200s, command30s/32768 bytes; input32000 estimated tokens, output1800 reserve, context120000 chars, single tool result16000. No invented deployment window or supplier usage. Config validated by original GatewayConfig. Only parser.py/report.py may change; final both must actually change through native receipts. A one-commit or two-commit path is equally legal; later edits require fresh current-revision tests.

Only command python -m unittest discover -s tests -v, cwd '.', original approval and Seatbelt. Live operator never clicks approve or resolves an approval. Each real command requires human action; model grant is independent. No approval or no tests => no Strict PASS.

Public8/Host18 behavior and all format ambiguities are fixed in fixture-contract/public-host-tests and fixture.py. Actual baseline FAIL/FAIL, Reference PASS/PASS in Seatbelt. Hidden tests exist outside model workspace and run only after the turn, with no feedback into the AgentLoop. No candidate import on host. No installs/remotes/Git writes permitted to Agent.

Every SDK/HTTP and tool admission checks frozen identities and full protected bytes/Git metadata/native revision ownership. Each commit stores before/after maps, delta, cumulative native journal/receipt proof. Unknown drift/publication/request/cleanup state HALT, no reset/checkout/reprepare. Case completion is distinct from semantic success. Preserve every failed dimension; no retries, extra Judge, source repair or score reinterpretation.

Original15 independent strict dimensions plus both-file attribution are defined in frozen plan/score. Strict needs all, including actual human command approval; synthetic workflow success is not Live Strict PASS. Optional contract metadata errors are reported separately and cannot create proof of requirement coverage. Usage from actual supplier/ledger only; cost=null without price. Full source/config/message/fixture/test/scoring/budget/port/workspace/DB inode/browser evidence hashes freeze after this commit on a clean worktree. Acceptance changes documentation only.
