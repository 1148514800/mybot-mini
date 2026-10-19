# serialization-001

修复Record到JSON字典转换：只省略None，必须保留False、0、空字符串；保持字段名称。

Run: python -m unittest discover -s tests -v

修改范围：仅修改已有app/下非__init__.py生产模块；不增删文件，不修改测试、README、notes或包初始化文件。运行公开unittest验证。
