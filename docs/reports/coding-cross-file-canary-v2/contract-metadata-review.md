# Auxiliary TaskContract review

Historical C01 rejection contract_proposal_rejected and its Strict PASS remain unchanged. Its exact invalid field is UNKNOWN; this report does not reverse-engineer a hidden rejected payload.

Native TaskContract requires arrays, at most 12 requirements, text length 1..320, proposal bytes <=16000 and cumulative requirement serialization <=9000. IDs R1..R99 are immutable. Sources/categories are strict enums. user_explicit must quote the exact current user input with current-user reference; project_documented must cite an observed, version-current native read (document-N) and exact returned excerpt. agent_suggestion/unresolved require an empty reference. Claims name existing IDs; evidence_links must reference actually observed test-N and an existing requirement, never arbitrary names or model PASS. Edits cannot redefine pre-edit requirements.

New synthetic legal proposal: exact user quote before edits, native tool success. New illegal proposal: unobserved-test evidence link, native rejection retained. Both run the ordinary native coding path; the rejected optional metadata call is not a code correctness failure, does not trigger repair/retry requests and does not weaken source validation. Valid sources do not prove requirement-level acceptance; independent_requirement_coverage and provenance_coverage remain UNKNOWN unless independently established.

Normal browser paths have zero contract calls/success/rejection. The dedicated negative fixture has two calls, one accepted and one rejected; dedicated legal fixture has one accepted call. Unit evidence and actual fixed rejection code distinguish this from the historical C01 event. No production Contract rules were modified.
