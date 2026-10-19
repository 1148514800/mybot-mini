# cache-ttl-001

修复TTL缓存：now等于过期时刻即失效；零TTL立即失效；负TTL抛ValueError；未到期可读。

Run: python -m unittest discover -s tests -v

修改范围：仅修改已有app/下非__init__.py生产模块；不增删文件，不修改测试、README、notes或包初始化文件。运行公开unittest验证。
