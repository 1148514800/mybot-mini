# cache-sync-001

修复API写入后的缓存同步：已缓存键写入新值后立即读到新值；仅失效对应键，多次覆盖保持一致。

Run: python -m unittest discover -s tests -v

修改范围：仅修改已有app/下非__init__.py生产模块；不增删文件，不修改测试、README、notes或包初始化文件。运行公开unittest验证。
