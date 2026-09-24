---
type: Backlog
---

# An e2e spec reads the site another spec left behind

`e2e/feature/conversations.spec.ts` ("create new conversation via button persists to
DB") failed once in a full container run with `(await afterResp.json()).length` equal to
`undefined`: the conversations list it read was not an array. In the same two minutes the
api answered 15 `GET /api/v1/conversations` with 404 `Unknown site: giardiadb` for a site
the six-site e2e config does not serve. The spec passed alone against the same stack.

The e2e `apiClient` fixture (`e2e/fixtures/test.ts`, `api-client.ts`) sends the browser
context's cookies and takes its base url from the page's current url, so a spec that runs
after another spec in the same worker inherits that spec's site state. Nothing in `e2e/`
names giardiadb: the site comes from the app's own site list when a spec walks every
site.

Fix in the suite, not the app: the fixture reads the list through the site the spec
opened (`entrySiteId` or `currentSiteId(page)`), and asserts the response is an array
before reading its length so a problem body fails with its status and detail instead of
`undefined`. Then find the spec that walks the app's site list and pin it to the sites
the e2e config serves.
