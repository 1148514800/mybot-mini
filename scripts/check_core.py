"""Small offline development suite. Full validation remains scripts.check_phase."""
import unittest

# Reuse complete existing suites, not copies or individual-test allowlists.
SUITES = (
    'scripts.check_session',
    'scripts.check_provider_chain',
    'scripts.check_tool_authority',
    'scripts.check_patch_preview_receipt',
    'scripts.check_session_event_store',
    'scripts.check_web_ui',
    'scripts.check_model_streaming',
    'scripts.check_core_refactor',
    'scripts.check_lean_refactor',
    'scripts.check_lean_core_v2',
)


def main():
    suite = unittest.defaultTestLoader.loadTestsFromNames(SUITES)
    result = unittest.TextTestRunner(verbosity=1).run(suite)
    return 0 if result.wasSuccessful() else 1


if __name__ == '__main__': raise SystemExit(main())
