---
type: Backlog
---

# A draft thread fetches a conversation that does not exist yet

**What I did.** Opened `/plasmodb/conversation` in the web app (a new draft thread) and sent the first message.

**What I got.** Before the first message created the row, the web requested `GET /api/v1/conversations/<draft id>` and `GET /api/v1/conversations/<draft id>/events/snapshot`; both answered 404 (two per draft in the api log, measured on two drafts) and the browser console logged two "Failed to load resource: 404" errors each time.

**Why that's wrong.** Every new chat opens with two console errors, which hides real ones from a tester and costs two round trips that can only fail.

**Why it happens.** The draft route mints a conversation id client-side, and the thread's data hooks fetch the conversation and its snapshot for any id in the URL, existing or not.

**Fix.** The conversation and snapshot queries are enabled only once the thread exists (the first message's response, or the route carrying a persisted id); a draft renders from local state. Red first: a jsdom test that a draft route makes no conversation fetch.

**What you'd get.** A new chat opens with no failed requests.
