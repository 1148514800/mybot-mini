# Revision and cumulative ownership

Only csvmini/parser.py and csvmini/report.py are mutable. All workspace images, modes, original Git HEAD, full Index and Git metadata are fingerprinted. Every native tool boundary and every SDK/HTTP admission rechecks this record; frozen verification anchors protected bytes and the original fixture HEAD/metadata to prepared.json.

Each accepted commit stores revision, full two-file before_hashes/after_hashes, actual changed_files delta, cumulative_owned, native Journal summary and receipt_commit_success/preview_to_commit_consistent. Per-file native before/after hashes must match actual bytes. Revision increases exactly once per commit. Delta must be nonempty and a subset of allowed paths. Unchanged allowed files remain in both maps.

A native Journal is cumulative: after separate commits its files contains both targets, while the second revision delta contains only report.py. Each cumulative file's original hash is anchored to the fixture baseline, final hash to that revision's after map; current_matches, revision ranges, journal_valid and git_metadata_unchanged are required. Final bytes must match the last map; actual Git Diff must match changed baseline hashes. Both paths must be legally owned and actually different at final scoring.

A one-Receipt two-file commit is Revision 1; two distinct Receipt commits are Revision 2. Later legal edits within three write attempts are accepted but invalidate old test evidence. Unknown drift, malformed chains/file sets, Git changes or publication uncertainty HALT; no reset/checkout/repair/reprepare. Native Journal is sampled after each successful patch because runtime legitimately destroys the in-memory capsule at turn close. Persisted summaries are host evidence, not model self-attestation or adversarial-host signatures.

Publication is per-file POSIX replacement with native best-effort recovery. Fault injection on the second publish and on Journal commit proves no false success and fail-closed behavior. This is not unconditional cross-file crash atomicity; uncertain original state remains preserved for investigation.
