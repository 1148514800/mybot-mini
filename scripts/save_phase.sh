#!/bin/bash
set -euo pipefail
export COPYFILE_DISABLE=1
cd "$(dirname "$0")/.."
source scripts/phase_common.sh
[[ $# == 2 && -n $2 ]] || die 'Usage: save_phase.sh NUMBER "Stage name"'
phase_id "$1"
git status --short
git log -5 --oneline
git tag -l
[[ -z $(git status --porcelain --untracked-files=all) ]] || die 'Commit related work first; working tree must be clean.'
! git rev-parse -q --verify "refs/tags/$tag" >/dev/null || die "Tag already exists: $tag"
out="$(dirname "$PWD")/mybot-mini-snapshots/$tag.zip"
[[ ! -e $out && ! -L $out ]] || die "ZIP already exists: $out"
doc="docs/phases/$tag.md"
git show "HEAD:$doc" | grep -qx 'archive-ready: true' || die 'Phase document must record completed validation (archive-ready: true).'
git diff-tree --root --no-commit-id --name-only -r HEAD | grep -Fxq "$doc" || die 'HEAD must include the current Phase document.'
git show HEAD:docs/phases/README.md | grep -Fq "$tag" || die 'Phase index is missing.'
tmp=$(mktemp -d)
trap 'find "$tmp" -depth -delete' EXIT
sha=$(git rev-parse HEAD)
git archive --format=zip --output="$tmp/phase.zip" "$sha"
uv run --no-project python scripts/phase_zip.py "$tmp/phase.zip" "$tag" "$tmp/source"
(cd "$tmp/source" && uv sync --frozen && uv run python -m compileall -q mybot && uv run python -m scripts.check_phase)
mkdir -p "$(dirname "$out")"
# Publish without overwriting, then tag the exact verified commit.
uv run --no-project python - "$tmp/phase.zip" "$out" <<'PYTHON'
import shutil, sys
with open(sys.argv[1], 'rb') as src, open(sys.argv[2], 'xb') as dst:
    shutil.copyfileobj(src, dst)
PYTHON
git tag -a "$tag" "$sha" -m "$tag: $2"
printf 'Tag: %s\nCommit: %s\nZIP: %s\n' "$tag" "$sha" "$out"
