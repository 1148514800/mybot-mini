#!/bin/bash
set -euo pipefail
export COPYFILE_DISABLE=1
cd "$(dirname "$0")/.."
source scripts/phase_common.sh
[[ $# == 1 || $# == 2 ]] || die 'Usage: restore_phase.sh NUMBER [rN]'
phase_id "$1"
revision=${2:-}
if [[ -z $revision && -f docs/phases/$tag.md ]]; then
    revision=$(sed -nE 's/^archive-revision: (r[1-9][0-9]{0,5})$/\1/p' "docs/phases/$tag.md")
fi
phase_revision "$revision"
dest="$(dirname "$PWD")/mybot-mini-learning/$tag"
[[ ! -e $dest && ! -L $dest ]] || die "Learning directory already exists: $dest"
tmp=$(mktemp -d)
trap 'find "$tmp" -depth -delete' EXIT
if git rev-parse -q --verify "refs/tags/$tag" >/dev/null; then
    git archive --format=zip --output="$tmp/phase.zip" "$tag"
    zip="$tmp/phase.zip"
else
    zip="$(dirname "$PWD")/mybot-mini-snapshots/$tag.zip"
    [[ -f $zip ]] || die "Neither tag nor ZIP exists: $tag"
fi
uv run --no-project python scripts/phase_zip.py "$zip" "$base_tag" "$tmp/source"
mkdir -p "$(dirname "$dest")"
# Copy into a new directory; never checkout/reset the development branch.
uv run --no-project python - "$tmp/source" "$dest" <<'PYTHON'
import shutil, sys
shutil.copytree(sys.argv[1], sys.argv[2], copy_function=shutil.copyfile)
PYTHON
printf 'Restored: %s\ncd "%s"\nuv sync --frozen\ncp config/config.example.json config/config.json\n# Fill API credentials locally, then:\nuv run python mybot/main.py\n' "$dest" "$dest"
