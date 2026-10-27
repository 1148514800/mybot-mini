# C02 csvmini contract

CSV uses an exact ordered id,category,amount header, DictReader strict quoting, and skips empty lines. Missing/extra fields and malformed quoting raise ValueError. id is preserved exactly; category is stripped without case folding (empty category is allowed). Amount surrounding whitespace is stripped. ASCII signed decimal notation (including .50 and 2.) is accepted, but exponents, underscores, nonfinite values, and lexical scale >2 (even trailing zeros) are rejected. Summation must remain exact for large amounts. No deduplication. No input mutation.

The six public files form a separate clean buggy Git repository without a remote. parser uses naive comma splitting, float and unstripped categories; report independently parses raw lines, loses repeated records and sorts categories. Fixing only one file fails isolated host acceptance. Both allowed files must actually differ from their original bytes through native Receipt commits. This two-file requirement belongs to C02, not a general production rule.

Public interface parse_records returns ordered dictionaries with exactly id/category/amount, id unchanged and amount Decimal. category_totals calls that parser, sums Decimal without float or deduplication and returns first-seen categories with fixed-two-place amounts. Extremely long valid fixed-point amounts are summed exactly under a sufficiently large local Decimal context. Header-only returns []. Input is immutable text. No installation, network or dependencies.

All samples, expected results, Reference and public/host suite bytes are fixed in fixture.py and included in source/prepared hashes. Host tests never reside in the model workspace; the README exposes the format ambiguities before coding. These are bounded synthetic cases, not a universal CSV conformance proof.

