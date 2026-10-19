"""Trusted benchmark assets and bounded, symlink-free disposable fixture copies."""
from dataclasses import dataclass
import ast
import hashlib
import json
import os
from pathlib import Path
import stat

from ..config import PROJECT_DIR
from ..tools.patch import version
from .runner import safe_path
from .git_workflow import fixture_git

BENCHMARK = PROJECT_DIR / 'evals/coding_benchmark'
PUBLIC_TEST = ('python', '-m', 'unittest', 'discover', '-s', 'tests', '-v')


@dataclass(frozen=True, repr=False)
class Image:
    data: bytes
    mode: int


@dataclass(frozen=True)
class RuntimeCase:
    id: str
    difficulty: str
    prompt: str
    public_test: tuple = PUBLIC_TEST


@dataclass(frozen=True, repr=False)
class Case:
    runtime: RuntimeCase
    public: dict
    hidden: dict
    reference: dict
    allowed: frozenset
    protected: frozenset
    public_count: int
    hidden_count: int


@dataclass(repr=False)
class Benchmark:
    cases: tuple
    sha256: str
    root: Path
    assets: dict

    def unchanged(self):
        try: return snapshot(self.root, exclude_git=False) == self.assets
        except (OSError, ValueError): return False


def snapshot(root, *, exclude_git=True):
    root = Path(root)
    if root.is_symlink() or not root.is_dir(): raise ValueError('unsafe_snapshot')
    result = {}; size = 0; directory_count = 0
    for folder, directories, files in os.walk(root, followlinks=False):
        parent = Path(folder)
        directory_count += 1
        if directory_count>512 or len(parent.relative_to(root).parts)>16: raise ValueError('snapshot_limit')
        if exclude_git and parent == root and '.git' in directories: directories.remove('.git')
        for name in directories:
            if (parent/name).is_symlink(): raise ValueError('unsafe_snapshot')
        if len(directories) + len(files) > 512: raise ValueError('snapshot_limit')
        for name in files:
            path = parent/name; relative = path.relative_to(root).as_posix()
            if exclude_git and relative == '.git': raise ValueError('unsafe_snapshot')
            if len(result) >= 512: raise ValueError('snapshot_limit')
            parent_fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
            try:
                for part in Path(relative).parts[:-1]:
                    next_fd=os.open(part,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=parent_fd)
                    os.close(parent_fd);parent_fd=next_fd
                fd=os.open(name,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK,dir_fd=parent_fd)
            finally: os.close(parent_fd)
            try:
                info = os.fstat(fd)
                if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_size > 131072:
                    raise ValueError('unsafe_snapshot')
                data = bytearray()
                while len(data) <= 131072:
                    chunk = os.read(fd, min(8192, 131073 - len(data)))
                    if not chunk: break
                    data.extend(chunk)
                size += len(data)
                if size > 2097152 or len(data)>131072 or version(info)!=version(os.fstat(fd)):
                    raise ValueError('snapshot_limit')
                result[relative] = Image(bytes(data), stat.S_IMODE(info.st_mode))
            finally: os.close(fd)
    return result


def write_images(root, images):
    root = Path(root); root.mkdir(parents=True, exist_ok=False)
    for name, image in images.items():
        safe_path(name)
        target = root/name; target.parent.mkdir(parents=True, exist_ok=True)
        with target.open('xb') as stream: stream.write(image.data)
        target.chmod(image.mode & 0o777)
    return root


def count_tests(images):
    count = 0
    for name, image in images.items():
        if name.endswith('.py'):
            tree = ast.parse(image.data)
            count += sum(isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name.startswith('test_')
                         for node in ast.walk(tree))
    return count


def load_benchmark(root=BENCHMARK):
    root = Path(root)
    if root.is_symlink(): raise ValueError('unsafe_benchmark_root')
    root = root.resolve(); assets = snapshot(root, exclude_git=False)
    try:
        document = json.loads(assets['manifest.json'].data)
        if set(document) != {'version','grading_version','cases'} or type(document['version']) is not int or document['version'] != 1 or type(document['grading_version']) is not int or document['grading_version'] != 1:
            raise ValueError('invalid_benchmark')
        rows = document['cases']
        if not isinstance(rows,list) or not 1 <= len(rows) <= 24: raise ValueError('invalid_benchmark')
        seen = set(); cases = []
        fields = {'id','difficulty','prompt','fixture','hidden_suite','reference','allowed_paths','protected_paths','public_test'}
        for row in rows:
            if set(row) != fields: raise ValueError('invalid_benchmark')
            id = row['id']
            import re
            if not isinstance(id,str) or not re.fullmatch('[a-z][a-z0-9-]{1,63}',id) or id in seen:
                raise ValueError('invalid_case_id')
            seen.add(id)
            if row['difficulty'] not in ('easy','medium','hard') or not isinstance(row['prompt'],str) or not 1 <= len(row['prompt']) <= 4000:
                raise ValueError('invalid_benchmark')
            if tuple(row['public_test']) != PUBLIC_TEST: raise ValueError('invalid_public_test')
            sections = []
            for key, prefix in [('fixture','fixtures'),('hidden_suite','hidden'),('reference','reference')]:
                if row[key] != prefix+'/'+id: raise ValueError('invalid_asset_path')
                base = row[key]+'/'
                images = {p[len(base):]:image for p,image in assets.items() if p.startswith(base)}
                if not images: raise ValueError('missing_case_assets')
                for p in images:
                    safe_path(p)
                    if any(part.startswith('.') or part in ('__pycache__','credentials') for part in Path(p).parts):
                        raise ValueError('unsafe_asset_path')
                sections.append(images)
            public,hidden,reference = sections
            allowed = row['allowed_paths']; protected = row['protected_paths']
            if not isinstance(allowed,list) or not isinstance(protected,list): raise ValueError('invalid_case_paths')
            if len(set(allowed))!=len(allowed) or len(set(protected))!=len(protected): raise ValueError('invalid_case_paths')
            for path in allowed + protected: safe_path(path)
            if not allowed or set(allowed)&set(protected) or set(allowed)|set(protected)!=set(public):
                raise ValueError('invalid_case_paths')
            if any(not p.startswith('app/') or not p.endswith('.py') or p=='app/__init__.py' for p in allowed):
                raise ValueError('invalid_editable_path')
            if not set(reference)<=set(allowed) or not set(hidden)=={'test_hidden.py'} or 'tests/test_public.py' not in protected:
                raise ValueError('invalid_private_assets')
            pc = count_tests({p:i for p,i in public.items() if p.startswith('tests/')}); hc = count_tests(hidden)
            if pc < 1 or hc < 1: raise ValueError('zero_tests')
            cases.append(Case(RuntimeCase(id,row['difficulty'],row['prompt']),public,hidden,reference,
                              frozenset(allowed),frozenset(protected),pc,hc))
        used = {'manifest.json'} | {section+'/'+c.runtime.id+'/'+p for c in cases
            for section,images in [('fixtures',c.public),('hidden',c.hidden),('reference',c.reference)] for p in images}
        if used != set(assets): raise ValueError('unexpected_benchmark_asset')
        digest = hashlib.sha256()
        for p,image in sorted(assets.items()):
            digest.update(p.encode()+b'\0'+hashlib.sha256(image.data).digest()+str(image.mode).encode()+b'\0')
        return Benchmark(tuple(cases),digest.hexdigest(),root,assets)
    except (KeyError,TypeError,UnicodeError,SyntaxError) as exc:
        raise ValueError('invalid_benchmark') from None


def create_repository(root, runtime_images):
    root = write_images(root, runtime_images)
    fixture_git(root,'init','-q','--initial-branch=benchmark')
    fixture_git(root,'add','.')
    fixture_git(root,'-c','user.name=Synthetic Benchmark','-c','user.email=benchmark@example.invalid','commit','-qm','Synthetic baseline')
    return root


def report_paths(paths, public):
    """Only known fixture names are printable; model-created names are digests."""
    return [p if p in public else '<unlisted-file:'+hashlib.sha256(p.encode()).hexdigest()[:20]+'>' for p in sorted(paths)]
