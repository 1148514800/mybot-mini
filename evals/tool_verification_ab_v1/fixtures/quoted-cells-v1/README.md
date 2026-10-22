修复parse_row(text)：text必须为str，否则ValueError；任何CR/LF字符均拒绝为ValueError。空字符串返回[]。其他输入严格按Python标准库csv.reader([text], delimiter=";", quotechar=双引号, doublequote=True, strict=True, skipinitialspace=False)的单行语义解析；保留空字段及空白，双引号内分号不是分隔符，成对双引号转义；csv语法错误统一转为ValueError。

python -m unittest discover -s tests -v
