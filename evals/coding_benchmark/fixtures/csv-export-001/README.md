# csv-export-001

修复CSV导出：使用标准CSV引号规则，支持逗号、双引号和字段内换行；每行以LF结束，可由csv.reader无损读取。

Run: python -m unittest discover -s tests -v

修改范围：仅修改已有app/下非__init__.py生产模块；不增删文件，不修改测试、README、notes或包初始化文件。运行公开unittest验证。
