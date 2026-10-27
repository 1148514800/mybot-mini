# Real isolated browser evidence

Fresh headed native Chrome 152.0.7977.83 / Playwright 1.64.1; sandbox true, no weakened browser security. Two fresh 0700 non-symlink profiles A/B access the same non-production origin: neither sees the other's Cookie or LocalStorage in either direction. Initial stores empty; test profiles removed and probe server closed. Third new fresh private profile used only for this UAT on 127.0.0.1:8901; actual launch user_data_dir and current UID verified, initial Cookie jar empty.

T01 real DOM new Session, message and Steer actions completed. Frozen first-chunk barrier gave the operator the registered intervention window; no model data changed. Safe activity-panel screenshot masks timeline/Pin/contract regions. Supplemental read-only Playwright Locator screenshot observation captured the admission warning and only wrote visibility/text-match booleans; it did not alter timing barriers, requests, page state or frozen files. Operator script itself was outside the repository; its hash is in evidence-hashes.json.

T02 stopped during server startup, before browser navigation/Session/message/Steer. T03 not executed. No same-profile port-based isolation assumption was used. No user Chrome/8765 page, cookie, settings or private messages accessed.

On the failure path Playwright's context manager had already stopped its loop before the outer finally attempted ctx.close(), causing a second error. Its Chrome process was gone, but profile removal did not run automatically. Operator independently verified zero matching profile processes and the known fresh owned directory identity, then removed only that directory. No process was killed. This cleanup defect is preserved; overall automated cleanup is FAIL even though final resource audit is clear.
