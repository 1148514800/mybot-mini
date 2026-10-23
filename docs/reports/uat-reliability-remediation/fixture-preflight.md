# Fixture 与冻结前预检

历史 create 默认语义及 PROJECTS/HIDDEN 内容保留。create_v2 只创建全新目录，在写入子文件前将新根目录属组设置为服务当前 EGID；已存在路径直接拒绝。不对旧文件 chown，不删除 ACL/xattr，不放宽产品写入权限。

check_environment 报告实际解析根目录、UID/EUID、GID/EGID、根上级及逐层目录权限/属组、文件mode/regular/symlink、版本时间戳与SHA256、xattr观测、原生ACL/元数据支持结果、Git HEAD/Index清单摘要/工作树。文件元数据判断直接复用产品 check_metadata；每个允许修改的文件再执行原生 dry_run Preview，验证路径、哈希、anchor及重检。没有调用正式 Write，前后 fingerprint（含Git）必须相同。

原 Seatbelt 启动公开 unittest 和独立断言；U04/U05 必须既匹配初始源码，又观察到公开断言 FAIL 和独立断言失败，不能将 import error 当预期Bug。U03公开测试用于确认入口和沙箱。新 prepare 在写 prepared.json 前 require_environment；非Preview服务器 lifespan 在客户端工厂运行前再次检查，不合规即 BLOCKED。新的Live仍须独立预注册和预算授权，旧账本不复用。

实测：新建U04一个、新建U05三个文件的原生Preview均通过，初始Bug确认且文件/Git未变。不匹配EGID（注入进程视角）、真实ACL、真实xattr、symlink和错误hash均拒绝；不覆盖已存在Fixture，已修好初始Bug也不能通过冻结前检查。GID负例没有为测试请求提权或修改真实服务组。

```bash
uv sync --frozen
uv run python -m scripts.check_uat_preflight
# 仅在新的独立Fixture上检查；输出含主机路径，仅留本地：
uv run python -m scripts.uat.check_environment U04 /absolute/new-fixture
```

检查是时点快照，不能证明冻结后永无竞争；正式Patch仍执行原有每次哈希、元数据、Receipt及发布前后重检。
