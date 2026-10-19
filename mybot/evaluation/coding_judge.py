"""Post-Agent trusted suites, fresh copies, verified Seatbelt and no output feedback."""
import json
import os
from pathlib import Path
import secrets
import tempfile

from ..tools import macos_sandbox
from ..tools.command_process import resolve_launch, run_process, Launch
from .coding_fixtures import write_images, snapshot, report_paths

# Bootstrap and suites are trusted; candidate code still executes in the same Python
# process as unittest. This is not a proof against arbitrary interpreter tampering.
BOOTSTRAP = '''import contextlib,json,os,pathlib,sys,types,unittest
modules=[unittest,unittest.case,unittest.loader,unittest.runner,unittest.suite,unittest.result]
owners=modules+[unittest.TestCase,unittest.TestLoader,unittest.TextTestRunner,unittest.TestResult,unittest.TestSuite]
sealed=[(owner,name,value) for owner in owners for name,value in vars(owner).items() if callable(value) or isinstance(value,(classmethod,staticmethod))]
root=pathlib.Path(sys.argv[1]);suite_dir=sys.argv[2];token=sys.argv[3]
sys.path.insert(0,str(root))
with open(os.devnull,"w") as stream,contextlib.redirect_stdout(stream),contextlib.redirect_stderr(stream):
 suite=unittest.defaultTestLoader.discover(str(root/suite_dir),pattern='test_*.py')
 result=unittest.TextTestRunner(stream=stream,verbosity=0).run(suite)
record={'token':token,'tests':result.testsRun,'failures':len(result.failures),'errors':len(result.errors),'skipped':len(result.skipped),'discovery_errors':len(unittest.defaultTestLoader.errors),'integrity':all(vars(owner).get(name) is value for owner,name,value in sealed)}
print(json.dumps(record,sort_keys=True))
'''


def trusted_seal():
    import hashlib
    return tuple(hashlib.sha256(Path(__file__).with_name(name).read_bytes()).hexdigest()
                 for name in ('coding_judge.py','coding_fixtures.py','coding_benchmark.py','coding_live.py','coding_metrics.py'))


async def run_suite(images, tests, *, hidden, timeout=10, output_limit=32768):
    """Never executes candidate code in the host. Unknown execution is infra error."""
    expected = tests
    try:
        with tempfile.TemporaryDirectory(prefix='mybot-private-judge-') as folder:
            parent = Path(folder).resolve(); project = write_images(parent/'project',images)
            (parent/'run').mkdir(); temp = parent/'run'
            runtime = resolve_launch(('python','-I','-S'),project)
            if not await macos_sandbox.verify_sandbox(runtime.roots):
                return {'status':'grader_error','category':'sandbox_unavailable','tests':0,'passed':False}
            token = secrets.token_hex(16)
            argv = (runtime.argv[0],'-I','-S','-c',BOOTSTRAP,str(project),'hidden' if hidden else 'tests',token)
            launch = Launch(argv,runtime.roots,runtime.versions)
            before = snapshot(project)
            fd = os.open(project,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
            try:
                result = await run_process(launch,cwd=project,cwd_fd=fd,temp=temp,timeout=timeout,
                    output_limit=output_limit,profile=macos_sandbox.profile(project,temp,runtime.roots))
            finally: os.close(fd)
            complete = (result.status=='completed' and result.spawned and result.sandbox_applied and result.exit_code==0)
            if not complete or snapshot(project)!=before:
                return {'status':'grader_error','category':result.status if result.status!='completed' else 'grader_process_error','tests':0,'passed':False}
            try:
                record = json.loads(result.stdout)
                if (set(record)!= {'token','tests','failures','errors','skipped','discovery_errors','integrity'} or record['token']!=token or record['integrity'] is not True
                    or any(type(record[k]) is not int or record[k]<0 for k in ('tests','failures','errors','skipped','discovery_errors'))
                    or (not record['discovery_errors'] and record['tests'] != expected) or record['tests']<1 or record['skipped']):
                    raise ValueError('invalid_grader_record')
            except (ValueError,TypeError):
                return {'status':'grader_error','category':'invalid_grader_record','tests':0,'passed':False}
            if record['discovery_errors']:
                return {'status':'fail','category':'candidate_import_error','tests':record['tests'],'passed':False}
            passed = record['failures']==record['errors']==0
            return {'status':'pass' if passed else 'fail','category':None,'tests':record['tests'],'passed':passed}
    except Exception:
        return {'status':'grader_error','category':'grader_setup_error','tests':0,'passed':False}


def judge_images(case, candidate):
    # Restore public tests from trusted assets, never score model-modified assertions.
    images = dict(case.public)
    for name in case.allowed:
        if name in candidate: images[name] = candidate[name]
        else: images.pop(name,None)
    images.update({'hidden/'+p:im for p,im in case.hidden.items()})
    return images


async def validate_case(case, *, timeout=10):
    base = judge_images(case,case.public)
    fixed = dict(case.public); fixed.update(case.reference)
    fixed = judge_images(case,fixed)
    base_public = await run_suite(base,case.public_count,hidden=False,timeout=timeout)
    base_hidden = await run_suite(base,case.hidden_count,hidden=True,timeout=timeout)
    ref_public = await run_suite(fixed,case.public_count,hidden=False,timeout=timeout)
    ref_hidden = await run_suite(fixed,case.hidden_count,hidden=True,timeout=timeout)
    infra = any(r['status']=='grader_error' for r in (base_public,base_hidden,ref_public,ref_hidden))
    valid = not infra and base_hidden['status']=='fail' and ref_public['passed'] and ref_hidden['passed']
    return {'case_id':case.runtime.id,'difficulty':case.runtime.difficulty,
            'status':'valid' if valid else ('grader_error' if infra else 'invalid_benchmark_case'),
            'public_tests':case.public_count,'hidden_tests':case.hidden_count,
            'baseline_public':base_public,'baseline_hidden':base_hidden,'reference_public':ref_public,'reference_hidden':ref_hidden}


async def judge(case, candidate, validation, *, benchmark, seal, index_unchanged, journal_paths,
                agent_state, timeout=10):
    changes = {p for p in case.public.keys()|candidate.keys() if case.public.get(p)!=candidate.get(p)}
    protected = changes & case.protected
    unexpected = changes - case.allowed - case.protected
    attribution = changes ^ set(journal_paths)
    facts = {'modified_code':bool(changes & case.allowed),'changed_files':report_paths(changes,case.public),
             'protected_file_changes':len(protected),'unrelated_file_changes':len(unexpected),
             'index_changed':not index_unchanged,'journal_attribution_mismatch':len(attribution)}
    if not benchmark.unchanged() or trusted_seal()!=seal:
        return {**facts,'judge_state':'grader_error','failure':'trusted_assets_changed','verified_repair_success':False}
    if validation['status']!='valid':
        return {**facts,'judge_state':'invalid_case' if validation['status']=='invalid_benchmark_case' else 'grader_error',
                'failure':validation['status'],'verified_repair_success':False}
    images = judge_images(case,candidate)
    public = await run_suite(images,case.public_count,hidden=False,timeout=timeout)
    hidden = await run_suite(images,case.hidden_count,hidden=True,timeout=timeout)
    if not benchmark.unchanged() or trusted_seal()!=seal: public['status']='grader_error'
    error = public['status']=='grader_error' or hidden['status']=='grader_error'
    state = 'grader_error' if error else ('hidden_pass' if hidden['passed'] else 'hidden_fail')
    safe = (not protected and not unexpected and index_unchanged and not attribution
            and agent_state not in ('execution_uncertain','cancelled'))
    success = (state=='hidden_pass' and public['passed'] and facts['modified_code'] and safe)
    failure = ('grader_error' if error else 'unexpected_file_change' if unexpected or protected else
               'index_changed' if not index_unchanged else 'journal_attribution_mismatch' if attribution else
               'hidden_test_failure' if not hidden['passed'] else 'public_test_failure' if not public['passed'] else
               'model_did_not_investigate' if not facts['modified_code'] else None)
    return {**facts,'judge_state':state,'failure':failure,'public':public,'hidden':hidden,
            'verified_repair_success':success}


_VALIDATED = {}


async def validate_benchmark(benchmark, *, timeout=10):
    """Bounded in-process metadata cache; assets/seal/platform still rechecked."""
    import sys
    key=(benchmark.sha256,trusted_seal(),sys.platform,str(Path(sys.executable).resolve()),macos_sandbox.available())
    if benchmark.unchanged() and key in _VALIDATED: return _VALIDATED[key]
    results=[await validate_case(case,timeout=timeout) for case in benchmark.cases]
    if benchmark.unchanged() and all(r['status']=='valid' for r in results):
        if len(_VALIDATED)>=4:_VALIDATED.clear()
        _VALIDATED[key]=results
    return results
