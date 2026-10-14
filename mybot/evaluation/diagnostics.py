"""Safe explanations: no response snippets, actual values or original errors."""
import json
import re
from pathlib import Path


REVIEW_FIELDS = ('file','function','evidence','trigger','impact','fix')


def json_diagnostic(text):
    try:
        return json.loads(text), {'status':'valid_json'}
    except json.JSONDecodeError as exc:
        detail = {'status':'empty' if not text.strip() else 'invalid_json',
                  'line':exc.lineno,'column':exc.colno}
        fence = re.fullmatch(r'\s*```(?:json)?\s*\n(.*?)\n```\s*',text,re.DOTALL|re.IGNORECASE)
        if fence:
            try:
                json.loads(fence[1])
                detail['status']='fenced_json'
            except json.JSONDecodeError:
                detail['status']='invalid_fenced_json'
        if detail['status']=='invalid_json':
            decoder = json.JSONDecoder()
            for start in [m.start() for m in re.finditer(r'\{',text)][:32]:
                try:
                    candidate,_ = decoder.raw_decode(text[start:])
                except json.JSONDecodeError:
                    continue
                if isinstance(candidate,dict) and 'findings' in candidate:
                    detail['status']='json_with_surrounding_text'
                    break
        return None, detail


def review_diagnostic(document, detail, annotations):
    if detail['status'] != 'valid_json':
        return False, [], detail | {'scorable':False}
    if not isinstance(document,dict):
        return False, [], detail | {'status':'non_object','scorable':False}
    if 'findings' not in document:
        return False, [], detail | {'status':'missing_findings','scorable':False}
    findings = document['findings']
    if not isinstance(findings,list):
        return False, [], detail | {'status':'findings_not_list','scorable':False}
    issues, matches, hits = [], [], set()
    for index,f in enumerate(findings):
        if not isinstance(f,dict):
            issues.append({'index':index,'issue':'non_object'})
            continue
        missing = [k for k in REVIEW_FIELDS if k not in f]
        invalid = [k for k in REVIEW_FIELDS if k in f and (not isinstance(f[k],str) or not f[k].strip())]
        if missing or invalid:
            issues.append({'index':index,'missing_fields':missing,'invalid_fields':invalid})
        candidates = [a for a in annotations if f.get('file')==a['file'] and f.get('function')==a['function']]
        evidence = f.get('evidence','')
        evidence = evidence.casefold() if isinstance(evidence,str) else ''
        evaluated = [(a,[i for i,terms in enumerate(a['evidence']) if not any(t.casefold() in evidence for t in terms)]) for a in candidates]
        matched = next((a for a,groups in evaluated if not groups),None)
        if matched:
            hits.add(matched['id'])
            matches.append({'index':index,'status':'matched','annotation_id':matched['id']})
        elif candidates:
            matches.append({'index':index,'status':'evidence_not_matched',
                            'candidates':[{'annotation_id':a['id'],'missing_evidence_groups':g} for a,g in evaluated]})
        else:
            matches.append({'index':index,'status':'unannotated_location'})
    valid = not issues
    return valid, findings, detail | {'status':'valid_review' if valid else 'invalid_fields','scorable':valid,
                                     'field_issues':issues,'finding_matches':matches,
                                     'unmatched_annotation_ids':[a['id'] for a in annotations if a['id'] not in hits],
                                     'note':'Unmatched evidence or unannotated locations require manual review; not proof of semantic error.'}


def normalized(value):
    return ' '.join(value.casefold().split()) if isinstance(value,str) else value


def document_diagnostic(artifact, detail, expected):
    fields = {}
    if not isinstance(artifact,dict):
        return detail | {'status':detail['status'] if detail['status']!='valid_json' else 'non_object','fields':fields}
    for key,value in expected.items():
        actual = artifact.get(key)
        if key not in artifact:
            fields[key]={'status':'missing_field'}
        elif type(actual) is not type(value):
            fields[key]={'status':'type_mismatch','expected_type':type(value).__name__,'actual_type':type(actual).__name__}
        elif isinstance(value,list):
            exact = all(isinstance(v,str) for v in actual) and sorted(actual)==sorted(value)
            comparable = all(isinstance(v,str) for v in actual)
            equivalent = comparable and sorted(normalized(v) for v in actual)==sorted(normalized(v) for v in value)
            fields[key]={'status':'matched' if exact else ('normalization_only_difference' if equivalent else 'items_not_matched'),
                         'missing_expected_items':[v for v in value if v not in actual],
                         'unmatched_actual_item_count':sum(v not in value for v in actual),
                         'normalized_equivalent':equivalent}
        else:
            fields[key]={'status':'matched' if actual==value else ('normalization_only_difference' if normalized(actual)==normalized(value) else 'value_not_matched')}
    return detail | {'fields':fields,'unexpected_field_count':len(set(artifact)-set(expected)),
                     'note':'Exact matching is unchanged. Unmatched wording requires manual review; actual values are not logged.'}
