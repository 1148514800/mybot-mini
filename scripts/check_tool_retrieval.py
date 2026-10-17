"""Deterministic ranking and metric correctness; no MCP network or model API."""
import json
import math
import unittest
from dataclasses import replace
from types import SimpleNamespace as N
from unittest.mock import patch
from mcp import types
from mybot.config import GatewayConfig
from mybot.tools import ToolRegistry
from mybot.mcp_client.adapter import MCPToolAdapter
from mybot.mcp_client.discovery import MCPToolCatalog,validate_discovery
from mybot.mcp_client.retrieval import BM25Index,tokenize,expand_query
from mybot.mcp_client.retrieval_aliases import MAX_EXPANDED_TERMS
from mybot.evaluation.tool_retrieval import synthetic_catalog,metrics,summarize,evaluate,load_cases


class RetrievalChecks(unittest.TestCase):
    def names(self,mode,q):return [m['name'] for m in json.loads(synthetic_catalog(mode).search(q).output)['matches']]

    def test_01_literal_default_shape(self):
        self.assertNotIn('retrieval_mode',validate_discovery({}))
        self.assertEqual(self.names('literal','project tasks')[0],'mcp__catalog__list_project_tasks')
        self.assertEqual(self.names('literal','项目任务'),[])

    def test_02_modes_strict(self):
        for mode in ('literal','bm25','hybrid'):self.assertEqual(validate_discovery({'retrieval_mode':mode})['retrieval_mode'],mode)
        for mode in (None,True,[],{},1,'BM25','vector'):
            with self.subTest(mode=mode),self.assertRaises(ValueError):validate_discovery({'retrieval_mode':mode})
        with self.assertRaises(ValueError):validate_discovery({'retrieval':'bm25'})

    def test_03_idf(self):
        index=BM25Index({'a':('rare common','',''),'b':('common','',''),'c':('other','','')})
        self.assertAlmostEqual(index.idf('rare'),math.log(1+(3-1+.5)/(1+.5)))
        self.assertGreater(index.idf('rare'),index.idf('common'));self.assertEqual(index.idf('missing'),0)

    def test_04_tf_saturation(self):
        index=BM25Index({'a':('x x z','',''),'b':('x z z','','')})
        scores=index.scores(['x'])
        self.assertGreater(scores['a'],scores['b']);self.assertLess(scores['a'],2*scores['b'])
        expected=6*index.idf('x')*2*2.2/(2+1.2)
        self.assertAlmostEqual(scores['a'],expected)

    def test_05_length_normalization(self):
        i=BM25Index({'short':('','', 'target'),'long':('','','target filler filler filler')})
        self.assertGreater(i.scores(['target'])['short'],i.scores(['target'])['long'])

    def test_06_field_weights(self):
        i=BM25Index({'a':('target','none','none'),'b':('none','target','none'),'c':('none','none','target')})
        s=i.scores(['target']);self.assertAlmostEqual(s['a'],6*s['c']);self.assertAlmostEqual(s['b'],3*s['c'])

    def test_07_tie_order_and_empty(self):
        i=BM25Index({'z':('same','',''),'a':('same','','')})
        self.assertEqual(i.rank('SAME'),['a','z']);self.assertEqual(i.rank('missing'),[])
        self.assertEqual(BM25Index({}).rank('target'),[])

    def test_08_tokens(self):
        self.assertEqual(tokenize('Code_MODULE-list words'),['code','module','list','words'])
        self.assertIn('任务',tokenize('项目任务'));self.assertIn('项',tokenize('项目任务'))
        self.assertIn('strasse',tokenize('Straße'))

    def test_09_continuous_chinese(self):
        terms=expand_query('查询项目未完成任务')
        self.assertTrue({'project','pending','tasks'}<=set(terms))
        self.assertIn('mcp__catalog__list_project_tasks',self.names('hybrid','查询项目未完成任务'))

    def test_10_mixed(self):
        self.assertEqual(self.names('hybrid','搜索 architecture 文档')[0],'mcp__catalog__search_documents')

    def test_11_alias_cap_no_target_names(self):
        self.assertLessEqual(len(expand_query('项目任务文档查找统计日程代码数据'*100)),MAX_EXPANDED_TERMS)
        self.assertTrue(all('mcp__' not in word for word in expand_query('查询项目任务')))
        i=BM25Index({'exact':('lookup','',''),'alias':('search','','')})
        self.assertEqual(i.rank('lookup',True)[0],'exact')

    def test_12_no_match_no_fallback(self):
        for mode in ('literal','bm25','hybrid'):self.assertEqual(self.names(mode,'quantum teleportation'),[])

    def test_13_permissions_and_no_io(self):
        registry=ToolRegistry()
        manager=N(servers={'s':{'allowed_tools':['ok','denied'],'tool_policies':{'denied':'deny'}}})
        for name in ('ok','denied','outside'):
            registry.register(MCPToolAdapter(manager,'s',types.Tool(name=name,description='project tasks',inputSchema={'type':'object'})))
        for mode in ('literal','bm25','hybrid'):
            catalog=MCPToolCatalog(registry,{'enabled':True,'retrieval_mode':mode})
            self.assertEqual(set(catalog.entries),{'mcp__s__ok'})
            self.assertEqual(len(catalog.index.fields),1)
            self.assertEqual(json.loads(catalog.search('project').output)['matches'][0]['name'],'mcp__s__ok')
            self.assertFalse(catalog.activate(['mcp__s__denied']).success)
            self.assertFalse(catalog.activate(['mcp__s__outside']).success)

    def test_14_bounded_safe_projection(self):
        for mode in ('literal','bm25','hybrid'):
            c=synthetic_catalog(mode,3);text=c.search('catalog project').output
            matches=json.loads(text)['matches'];self.assertLessEqual(len(matches),3)
            self.assertTrue(all(set(m)=={'name','server','description'} for m in matches))
            self.assertNotIn('parameters',text);self.assertNotIn('tool_policies',text)
            self.assertFalse(c.search('a'*257).success)

    def test_15_multi_relevant_metrics(self):
        m=metrics(['b','x','a'],['a','b'],3)
        self.assertEqual(m['hit'],1);self.assertEqual(m['recall'],1);self.assertEqual(m['mrr'],1)
        self.assertAlmostEqual(m['ndcg'],(1+1/math.log2(4))/(1+1/math.log2(3)))
        m=metrics(['x','b'],['a','b'],1);self.assertEqual(m,dict(hit=0,recall=0,mrr=0,ndcg=0))
        self.assertEqual(metrics(['x','b'],['a','b'],3)['mrr'],.5)

    def test_16_negative_denominators(self):
        rows=[{'relevant_count':1,'returned':['a'],'metrics':{str(k):metrics(['a'],['a'],k) for k in (1,3,5)}},
              {'relevant_count':0,'returned':[],'metrics':{str(k):None for k in (1,3,5)}}]
        s=summarize(rows);self.assertEqual(s['positive_denominator'],1);self.assertEqual(s['negative_denominator'],1)
        self.assertEqual(s['recall@5'],1);self.assertEqual(s['no_match_accuracy'],1)
        self.assertIsNone(summarize(rows[1:])['mrr@5'])

    def test_17_reproducible_cases_and_holdout(self):
        a=evaluate();self.assertEqual(a,evaluate());self.assertEqual(a['results']['literal']['overall']['cases'],36)
        self.assertEqual(a['results']['hybrid']['overall']['positive_denominator'],32)
        self.assertTrue(any(c['split']=='heldout' for c in load_cases()))
        self.assertFalse(a['agent_success_measured'])
        # Deliberately imperfect results: never make a universal multilingual claim.
        self.assertLess(a['results']['hybrid']['overall']['hit@5'],1)


def check_tool_retrieval():
    result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(RetrievalChecks))
    if not result.wasSuccessful():raise SystemExit(1)


if __name__=='__main__':check_tool_retrieval()
