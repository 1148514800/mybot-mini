# pagination-001

修复1起始页码分页：每页最多size项，不能丢最后一项；page/size须为正整数，bool也无效。

Run: python -m unittest discover -s tests -v

修改范围：仅修改已有app/下非__init__.py生产模块；不增删文件，不修改测试、README、notes或包初始化文件。运行公开unittest验证。
