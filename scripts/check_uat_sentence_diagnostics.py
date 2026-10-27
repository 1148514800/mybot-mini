import unittest
from scripts.streaming_steer_recovery_v3.sentence_diagnostics import diagnose

class SentenceChecks(unittest.TestCase):
 def test_adjacent_chinese(self):self.assertEqual(diagnose('第一句话。第二句话。',2)['format_check'],'PASS')
 def test_chinese_questions(self):self.assertEqual(diagnose('好吗？很好！')['deterministic_sentence_count'],2)
 def test_english(self):self.assertEqual(diagnose('One. Two? Three!')['deterministic_sentence_count'],3)
 def test_mixed(self):self.assertEqual(diagnose('第一句。Next sentence. 最后一句！')['deterministic_sentence_count'],3)
 def test_whitespace(self):self.assertEqual(diagnose('  一。\n\n 二。 ',2)['format_check'],'PASS')
 def test_markdown_heading(self):self.assertEqual(diagnose('# Title\nText.')['format_check'],'FORMAT_REVIEW_REQUIRED')
 def test_code(self):
  r=diagnose('```python\na.b()\n```\n一句。');self.assertEqual(r['deterministic_sentence_count'],1);self.assertIn('markdown_structure',r['review_reasons'])
 def test_lists(self):self.assertEqual(diagnose('- One.\n- Two.')['format_check'],'FORMAT_REVIEW_REQUIRED')
 def test_decimal(self):self.assertEqual(diagnose('数值3.14。第二句。',2)['format_check'],'PASS')
 def test_abbreviation(self):self.assertEqual(diagnose('Dr. Wu arrived. Done.')['format_check'],'FORMAT_REVIEW_REQUIRED')
 def test_eg(self):self.assertIn('abbreviation',diagnose('Try e.g. text.')['review_reasons'])
 def test_ellipsis(self):self.assertEqual(diagnose('等等……再说。')['format_check'],'FORMAT_REVIEW_REQUIRED')
 def test_quotes(self):self.assertEqual(diagnose('他说“好。”然后走了。')['format_check'],'FORMAT_REVIEW_REQUIRED')
 def test_colon_preface(self):self.assertEqual(diagnose('以下是说明：\n项目本地运行。它检索文档。',2)['format_check'],'PASS')
 def test_status_three_sentences(self):
  r=diagnose('已按顺序读取README，未修改文件。\n以下基于真实结果：\n项目本地运行。标识为公开测试值。',2);self.assertEqual(r['deterministic_sentence_count'],3);self.assertEqual(r['format_check'],'FAIL');self.assertEqual(r['independent_semantic_review'],'NOT_PERFORMED')
 def test_punctuation_cluster(self):self.assertEqual(diagnose('真的吗？！是的。')['deterministic_sentence_count'],2)
 def test_no_rewrite(self):self.assertFalse(diagnose('原句。')['rewritten'])
 def test_no_semantic_claim(self):self.assertEqual(diagnose('永久保留。',1)['independent_semantic_review'],'NOT_PERFORMED')
if __name__=='__main__':unittest.main()
