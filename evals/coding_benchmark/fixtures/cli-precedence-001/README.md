# cli-precedence-001

修复CLI与配置优先级：显式CLI优先，未指定时用配置，再用默认retries=3/verbose=False；retries=0是有效值。

Run: python -m unittest discover -s tests -v

修改范围：仅修改已有app/下非__init__.py生产模块；不增删文件，不修改测试、README、notes或包初始化文件。运行公开unittest验证。
