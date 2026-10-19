# error-retry-001

修复重试调用链：retries表示首次之外重试次数（0仍调用一次）；只重试OSError，其他错误立即原样传播；耗尽后抛最后一个OSError。

Run: python -m unittest discover -s tests -v

修改范围：仅修改已有app/下非__init__.py生产模块；不增删文件，不修改测试、README、notes或包初始化文件。运行公开unittest验证。
