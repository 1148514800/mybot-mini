# Shared argument handling (sourced by the two entry points).
die() { echo "$*" >&2; exit 1; }
phase_id() {
    [[ $1 =~ ^[0-9]{1,2}$ ]] || die 'Phase must be an integer from 1 to 99.'
    local n=$((10#$1))
    (( n >= 1 && n <= 99 )) || die 'Phase must be from 1 to 99.'
    printf -v tag 'phase-%02d' "$n"
}

# Explicit immutable revision suffix; base phase documentation remains phase-XX.md.
phase_revision() {
    base_tag=$tag
    local revision=${1:-}
    [[ -z $revision || $revision =~ ^r[1-9][0-9]{0,5}$ ]] || die 'Revision must be r1..r999999.'
    [[ -z $revision ]] || tag="$base_tag-$revision"
}
