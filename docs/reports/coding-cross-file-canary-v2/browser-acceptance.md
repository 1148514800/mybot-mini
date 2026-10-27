# Actual headed Chrome synthetic acceptance

Chrome 152.0.7977.83, new 0700 profiles, chromium sandbox enabled, initially empty Cookie Jar. A/B same nonproduction local origin probe confirms Cookie and LocalStorage isolation in both directions; both probe profiles and temporary HTTP service cleaned. UAT creates another fresh profile; no user profile or 8765 operation.

Two fresh Mock services on 127.0.0.1:8904 were operated by real Playwright DOM: new conversation, one frozen task submission, actual native file reads, visible Patch Preview/Receipt, command approval dialog/full effective argv inspection, one Mock-only SYNTHETIC_APPROVAL click. Final states verified Revision1 (one dual-file commit) and verified Revision2 (two separate commits). Public8/Host18 pass on both; UI revision visible; refresh plus SSE reconnect adds no requests or tools. Original Cookie/CSRF/CSP/Origin implementation unchanged.

Each service returned wait exit0, port absent, SDK closed, Lease released and SQLite consistent. Each context closed exactly once while its Playwright event loop remained alive, own browser processes exited, profile automatically removed. Strict Success false because no real human approval; synthetic_workflow_pass true.

Sanitized screenshots mask private timeline/contract/pins and full approval details; no Receipt/nonce/Cookie/key/full request or private SQLite is published. See screenshots and browser-evidence.json. Browser results do not prove real provider behavior.


A third fresh headed Chrome Mock run deliberately interrupts the SDK stream. Native delivery reports provider_error, Revision0 and no strict/synthetic success; the persistent ledger HALT remains protocol_failure. Despite HALT, its actual Uvicorn process exits0, port is released, SDK closes, Lease releases, DB is consistent, context closes once and own Profile is removed. See halt-cleanup-evidence.json. This controlled negative fixture is separate from the future frozen batch and is not a Live attempt.
