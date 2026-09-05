import unittest

from mybot.tools.browser.errors import BrowserErrorType, classify_browser_error


class BrowserErrorTaxonomyTests(unittest.TestCase):
    def assert_classification(self, text, expected, recoverable):
        error_type, actual_recoverable = classify_browser_error(text)
        self.assertEqual(error_type, expected)
        self.assertEqual(actual_recoverable, recoverable)

    def test_recoverable_failures(self):
        self.assert_classification(
            "Ref e12 not found in current page snapshot",
            BrowserErrorType.STALE_TARGET,
            True,
        )
        self.assert_classification(
            "strict mode violation: resolved to 3 elements",
            BrowserErrorType.AMBIGUOUS_TARGET,
            True,
        )
        self.assert_classification(
            "TimeoutError: waiting for locator timed out",
            BrowserErrorType.PAGE_TIMEOUT,
            True,
        )
        self.assert_classification(
            "login required",
            BrowserErrorType.AUTH_REQUIRED,
            True,
        )
        self.assert_classification(
            "Element matching #save not found",
            BrowserErrorType.TARGET_NOT_FOUND,
            True,
        )
        error_type, recoverable = classify_browser_error(
            "net::ERR_CONNECTION_RESET",
            action="goto",
        )
        self.assertEqual(error_type, BrowserErrorType.NAVIGATION_FAILURE)
        self.assertTrue(recoverable)

    def test_non_recoverable_tool_syntax_failure(self):
        self.assert_classification(
            "SyntaxError: Unexpected token ')'",
            BrowserErrorType.TOOL_SYNTAX_ERROR,
            False,
        )

    def test_unknown_failure_is_not_assumed_recoverable(self):
        self.assert_classification(
            "browser daemon disappeared",
            BrowserErrorType.UNKNOWN,
            False,
        )


if __name__ == "__main__":
    unittest.main()
