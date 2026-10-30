"""Diagnostic-only tests; no real API or normal workspace content."""
import json
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace as N

from mybot.config import GatewayConfig, PROJECT_DIR
from mybot.evaluation.runner import evaluate, load_cases, OfflineClient
from mybot.evaluation.diagnostics import json_diagnostic, review_diagnostic, document_diagnostic
from mybot.evaluation.artifacts import retain_outputs


class DiagnosticChecks(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.cases={c['id']:c for c in load_cases()}
        self.config=GatewayConfig(skills_enabled=False,skills_path=PROJECT_DIR/'skills',
                                  context_enabled=True,debug=False,max_react_steps=16,
                                  api_key='PRIVATE_KEY_SENTINEL')

    async def run_case(self,case,**kwargs):
        return await evaluate([case],groups=('off',),base_config=self.config,**kwargs)

    async def test_parse_failure_separate_no_fake_missed_defects(self):
        case=deepcopy(self.cases['complex-code-review'])
        case['offline']['reply']='```json\n'+case['offline']['reply']+'\n```'
        report=await self.run_case(case);r=report['results'][0]
        self.assertFalse(r['task_success'])
        self.assertIsNone(r['review_findings'])
        self.assertEqual(r['diagnostics']['review']['status'],'fenced_json')
        self.assertEqual(report['overall']['off']['review_unscorable_cases'],1)
        self.assertNotIn('review_quality',report['overall']['off'])
        self.assertEqual(r['grading_reasons'],['task:review_format'])

    async def test_schema_status_and_private_body_not_reported(self):
        for text,status in (('','empty'),('SECRET_BODY','invalid_json'),('[]','non_object'),('{}','missing_findings'),('{"findings":{}}','findings_not_list'),('Analysis then {"findings":[]} done','json_with_surrounding_text')):
            document,detail=json_diagnostic(text)
            valid,_,diag=review_diagnostic(document,detail,[])
            self.assertFalse(valid);self.assertEqual(diag['status'],status)
            self.assertNotIn('SECRET_BODY',json.dumps(diag))
        case=deepcopy(self.cases['complex-code-review'])
        value=json.loads(case['offline']['reply']);value['findings'][0].pop('fix')
        case['offline']['reply']=json.dumps(value)
        r=(await self.run_case(case))['results'][0]
        self.assertEqual(r['diagnostics']['review']['field_issues'][0]['missing_fields'],['fix'])
        self.assertIsNone(r['review_findings'])

    async def test_evidence_diagnoses_location_and_specific_group(self):
        case=deepcopy(self.cases['complex-code-review'])
        value=json.loads(case['offline']['reply']);value['findings'][0]['evidence']='private arbitrary text'
        value['findings'][1]['file']='unknown-secret-file.py'
        case['offline']['reply']=json.dumps(value)
        r=(await self.run_case(case))['results'][0];diag=r['diagnostics']['review']
        self.assertEqual(diag['finding_matches'][0]['status'],'evidence_not_matched')
        self.assertEqual(diag['finding_matches'][0]['candidates'][0]['missing_evidence_groups'],[0,1,2])
        self.assertEqual(diag['finding_matches'][1]['status'],'unannotated_location')
        self.assertNotIn('private arbitrary',json.dumps(r));self.assertNotIn('unknown-secret-file',json.dumps(r))

    async def test_array_normalization_diagnostic_keeps_strict_score(self):
        case=deepcopy(self.cases['complex-document-summary'])
        v=json.loads(case['offline']['actions'][-1]['args']['content']);v['constraints']=[s.upper()+'  ' for s in v['constraints']]
        case['offline']['actions'][-1]['args']['content']=json.dumps(v)
        r=(await self.run_case(case))['results'][0]
        self.assertFalse(r['task_success'])
        self.assertEqual(document_diagnostic(v, {'status':'valid_json'}, case['expect']['document']['values'])['fields']['constraints']['status'],'normalization_only_difference')
        v['constraints']=['PRIVATE_BODY'];case['offline']['actions'][-1]['args']['content']=json.dumps(v)
        r=(await self.run_case(case))['results'][0]
        diag=document_diagnostic(v, {'status':'valid_json'}, case['expect']['document']['values'])['fields']['constraints']
        self.assertEqual(diag['unmatched_actual_item_count'],1)
        self.assertEqual(len(diag['missing_expected_items']),2)
        self.assertNotIn('PRIVATE_BODY',json.dumps(r))

    async def test_retention_opt_in_isolated_and_redacted(self):
        case=self.cases['complex-code-review']
        class Client(OfflineClient):
            async def create(client,**kwargs):
                r=await super(Client,client).create(**kwargs)
                if not r.choices[0].message.tool_calls:r.choices[0].message.content='PRIVATE_KEY_SENTINEL'
                return r
        with tempfile.TemporaryDirectory() as directory:
            r=(await self.run_case(case,retain_artifacts=directory,client_factory=lambda cfg,c:Client(c,'off')))['results'][0]
            artifact=r['retained_artifacts'];self.assertEqual(artifact['status'],'saved')
            text=(Path(artifact['directory'])/'final-response.txt').read_text()
            self.assertEqual(text,'[REDACTED]')
            self.assertTrue(artifact['files'][0]['redacted'])
            custom=deepcopy(case);custom['prompt']+=' custom'
            r=(await self.run_case(custom,retain_artifacts=directory))['results'][0]
            self.assertEqual(r['retained_artifacts']['status'],'refused')
        r=(await self.run_case(case))['results'][0]
        self.assertEqual(r['retained_artifacts']['status'],'disabled')

    async def test_retention_whitelist_size_and_symlink(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);workspace=root/'workspace';workspace.mkdir();dest=root/'out'
            (workspace/'secret.txt').write_text('NOT_TO_COPY')
            (workspace/'project-summary.json').symlink_to(workspace/'secret.txt')
            output=retain_outputs(self.cases['complex-document-summary'],'R'*100001,workspace,dest)
            self.assertFalse(output['files']);self.assertEqual(len(output['skipped']),2)
            self.assertEqual(list(Path(output['directory']).iterdir()),[])

    async def test_response_limit_and_runtime_metadata(self):
        class Client(OfflineClient):
            async def create(client,**kwargs):
                r=await super(Client,client).create(**kwargs);r.choices[0].finish_reason='length';return r
        r=(await self.run_case(self.cases['greeting'],client_factory=lambda cfg,c:Client(c,'off')))['results'][0]
        self.assertTrue(r['diagnostics']['runtime']['output_limit_reached'])
        self.assertEqual(r['diagnostics']['runtime']['request_timeout_seconds'],self.config.request_timeout_seconds)


def check_diagnostics():
    r=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(DiagnosticChecks))
    if not r.wasSuccessful():raise SystemExit(1)


if __name__=='__main__':check_diagnostics()
