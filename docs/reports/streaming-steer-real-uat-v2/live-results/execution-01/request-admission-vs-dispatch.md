# Independent Steer layers

T01 Web message POST 202 and Steer POST 200, one each. Real DOM buttons were used; no API mutation substitutes. Source event, Session and Turn IDs and the frozen text hash are recorded in tool-and-steer-evidence.json.

1. queued: native event stored from real user Web action, exact text matched.
2. admitted: native_on_dispatch occurred at the next model boundary; this is what UI applied means.
3. reservation: subsequent physical reservations 2 and 3 persisted independently before SDK work.
4. HTTP dispatched: each later request has one actual HTTP-hook record, wire hash equals SDK request and wire messages match SDK messages.
5. provider response: each later request returned a real SDK stream and legal complete response. No inference of remote understanding from HTTP alone.
6. model obeyed: README priority/no examples/identifier/purpose pass; complete-answer two-sentence constraint fails.

In-flight request remains unchanged at acceptance and stream close. Source references in both subsequent SDK requests identify the same real user Steer event, correct Session/Turn and original exact frozen text; no model-authored user event or Pin was inserted. Source IDs/hashes are public evidence; full messages/arguments are not.

The UI visibly says “已在下一模型步骤应用（不代表模型遵从）”; cropped browser screenshot confirms it. T02's not_applied UI was not reached in this Live run; prior Mock evidence remains Mock only.
