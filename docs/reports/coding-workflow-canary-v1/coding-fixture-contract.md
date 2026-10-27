# notesearch-mini Fixture合同

本项目是本轮新建的可丢弃标准库Python项目，不使用用户真实项目、不安装依赖或setup脚本。仅README.md、notesearch/__init__.py、notesearch/search.py、tests/test_search.py、.gitignore五个公开文件；初始化独立Git仓库及干净Bug提交，无remote。初始化由可信操作员执行，Agent没有Commit/Push工具。

初始实现使用大小写敏感的title包含判断、set去重及排序，未strip查询、未匹配body，空查询误命中。公开测试5项和独立Host测试10项均在实际Seatbelt隔离进程中验证：Bug基线fail，可信Reference通过。模型必须读取真实文件SHA，不能用输出固定字符串替代业务验证。

唯一可修改文件notesearch/search.py；匹配title或body、去首尾空白、casefold Unicode大小写、空查询[]、原始顺序、保留重复id、不修改输入。公开测试、README、__init__、gitignore、Git元数据、隐藏验收和宿主实现不可修改。合法Patch可改变search.py inode/字节，不要求恢复初始hash；必须有原生Receipt和Journal可核验归属。

Fixture构造后仅对新创建且UID属于当前用户的文件/目录设置当前effective GID，避免/private/tmp继承wheel导致原生Patch unsupported_ownership。没有放宽Patch ownership/ACL/xattr安全门，也不更改任何既有用户文件。初始失败日志hash保留；原T01/T02/T03/N01/N02结果不改。
