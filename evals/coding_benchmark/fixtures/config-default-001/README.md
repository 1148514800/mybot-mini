# config-default-001

修复布尔配置读取：显式False必须覆盖True默认值；缺省使用默认；非bool值应抛ValueError。

Run: python -m unittest discover -s tests -v

修改范围：仅修改已有app/下非__init__.py生产模块；不增删文件，不修改测试、README、notes或包初始化文件。运行公开unittest验证。
