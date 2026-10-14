"""Opt-in, bounded synthetic outputs; never dump workspaces or tool transcripts."""
import hashlib
import re
import uuid
from pathlib import Path


LIMIT = 100000


def redact(text, secrets):
    for secret in secrets:
        if secret:
            text = text.replace(secret,'[REDACTED]')
    return re.sub(r'sk-[A-Za-z0-9_-]{20,}|gh[pousr]_[A-Za-z0-9]{20,}|-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----.*?-----END (?:RSA |EC |OPENSSH )?PRIVATE KEY-----',
                  '[REDACTED]',text,flags=re.DOTALL)


def retain_outputs(case, reply, workspace, directory, secrets=()):
    destination = Path(directory)/uuid.uuid4().hex
    destination.mkdir(parents=True,exist_ok=False)
    retained, skipped = [], []
    def save(name,text,source=None):
        if len(text.encode('utf-8'))>LIMIT:
            skipped.append({'file':name,'reason':'size_limit'})
            return
        clean = redact(text,secrets)
        with (destination/name).open('x',encoding='utf-8') as stream:
            stream.write(clean)
        retained.append({'file':name,'source':source,'redacted':clean!=text,'sha256':hashlib.sha256(clean.encode()).hexdigest()})
    save('final-response.txt',reply)
    paths = set(case['expect'].get('files',{}))
    if 'document' in case['expect']:
        paths.add(case['expect']['document']['path'])
    for index,path in enumerate(sorted(paths)):
        target = workspace/path
        if target.is_symlink() or not target.resolve().is_relative_to(workspace.resolve()) or not target.is_file():
            skipped.append({'file':f'artifact-{index}','reason':'missing_or_unsafe'})
            continue
        if target.stat().st_size>LIMIT:
            skipped.append({'file':f'artifact-{index}','reason':'size_limit'})
            continue
        try:
            save(f'artifact-{index}.txt',target.read_text(encoding='utf-8'),path)
        except UnicodeError:
            skipped.append({'file':f'artifact-{index}','reason':'invalid_utf8'})
    return {'status':'saved','directory':str(destination.resolve()),'files':retained,'skipped':skipped}
