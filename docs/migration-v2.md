# Migrating a server to bg-mcpcore 2.0 (FastMCP 4)

bg-mcpcore 2.0 moves the framework from FastMCP 3.4.x to **FastMCP 4.0**, which
rebuilds on MCP Python SDK v2, adds the sessionless `2026-07-28` protocol, and
replaces `httpx` with `httpx2` across its whole HTTP stack.

**Most servers need one line changed.** Scaffolded servers pin bg-mcpcore by git
tag, so nothing upgrades on its own — you migrate one repo at a time, on your
own schedule, and a repo that stays on `v1.6.1` keeps working exactly as it did.

---

## Do I have to do anything?

Work down this list. If every answer is "no", your migration is
[step 1](#step-1-bump-the-pin) and nothing else.

```bash
# Run these from your server repo. Any output means that step applies to you.
grep -rn "import httpx\|except httpx\.\|httpx\.Response"  --include=*.py .
grep -rn "task=True\|TaskConfig"                          --include=*.py .
grep -rn "ctx\.elicit\|ctx\.sample\|ctx\.list_roots"      --include=*.py .
grep -rn "pydantic"                                        pyproject.toml
grep -rn "\-32002"                                        --include=*.py .
# Step 6 needs AUTH_MODE=oidc AND OIDC_DISCOVERY_URL AND OIDC_ISSUER set,
# with OIDC_ISSUER != PUBLIC_BASE_URL. All four - see the runbook.
grep -rnE "AUTH_MODE|OIDC_DISCOVERY_URL|OIDC_ISSUER"      .env* 2>/dev/null
```

A typical server is a four-line `main.py`, a `profile.json`, and maybe a
`my_tools.py` using `ctx.request`. That shape is unaffected by everything below
except step 1.

---

## Step 1 — Bump the pin

In your `pyproject.toml`:

```diff
 dependencies = [
-  "bg-mcpcore[openapi,oauth-providers,redis] @ git+https://github.com/bauer-group/LIB-BG-MCPCore.git@v1.6.1",
+  "bg-mcpcore[openapi,oauth-providers,redis] @ git+https://github.com/bauer-group/LIB-BG-MCPCore.git@v2.0.0",
 ]
```

Then reinstall and run your tests:

```bash
uv pip install -e ".[dev]" --upgrade
pytest -q
```

If you pin `pydantic` yourself, raise the floor to `>=2.12` — FastMCP 4 requires
it, and an older pin fails as an unsatisfiable resolution rather than a silent
bump. You do **not** need to add `httpx2` to your dependencies; bg-mcpcore
brings it.

---

## Step 2 — HTTP types move to `bg_mcpcore.http`

**This is the one change that reaches tool code, and the only one that can fail
silently.** Everything else fails loudly or not at all.

`ToolContext.request()` now returns an `httpx2.Response`. The types are
re-exported from `bg_mcpcore.http` so your code never names an HTTP library
again:

```diff
-import httpx
+from bg_mcpcore.http import HTTPStatusError, Response

 @mcp.tool
 async def get_widget(widget_id: str) -> dict:
-    resp: httpx.Response = await ctx.request("GET", f"/widgets/{widget_id}")
+    resp: Response = await ctx.request("GET", f"/widgets/{widget_id}")
     try:
         resp.raise_for_status()
-    except httpx.HTTPStatusError as exc:
+    except HTTPStatusError as exc:
         ...
```

Available names: `Response`, `Request`, `HTTPError`, `HTTPStatusError`,
`RequestError`, `TransportError`, `ConnectError`, `ConnectTimeout`,
`TimeoutException`. They also resolve from the top level
(`from bg_mcpcore import Response`).

> **Why this one is dangerous.** `httpx` almost certainly stays installed in
> your environment as a transitive dependency of something else. So
> `except httpx.ConnectError:` still imports, still type-checks, still passes
> review — and never matches again, because the error raised is now
> `httpx2.ConnectError`. The handler becomes dead code with no error anywhere.
> Grep for `except httpx.` and fix every hit.

A codemod does the mechanical part:

The codemod ships in the framework repo (`scripts/migrate_v2.py`). Run it
against your server checkout:

```bash
curl -fsSLO https://raw.githubusercontent.com/bauer-group/LIB-BG-MCPCore/v2.0.0/scripts/migrate_v2.py

python migrate_v2.py .            # report what it would change
python migrate_v2.py . --write    # apply
```

Review its diff — it rewrites imports and handlers, but cannot judge a case
where you deliberately used `httpx` for your own outbound calls unrelated to
`ctx.request`. Those are yours and are unaffected: `httpx` still works, it is
simply no longer what bg-mcpcore raises.

### Two runtime behaviours that come with httpx2

- **TLS trust now uses the operating system store** (via `truststore`, honouring
  `SSL_CERT_FILE` / `SSL_CERT_DIR`) instead of a bundled certifi bundle. If your
  upstream sits behind an internal CA, verify one real call before rolling out.
  `verify_tls` in the profile is unchanged.
- **Logger names changed** to `httpx2` / `httpcore2`. bg-mcpcore quiets both
  (and the old names); update any log filter of your own that selects by name.

### Testing against an httpx2 client

`respx` cannot patch httpx2 on its own. Use the testkit helpers — they wrap the
two quirks (patch `httpcore2`; respx models its *mocked* responses with `httpx`
v1 objects even though your client receives a real `httpx2.Response`):

```python
from bg_mcpcore.testing import mock_upstream, upstream_response

async def test_widget():
    with mock_upstream() as router:
        router.get("https://api.test/widgets/1").mock(
            return_value=upstream_response(200, json={"id": "1"})
        )
        ...
```

There is also a `mock_upstream` pytest fixture if you install
`bg-mcpcore[testkit]`. For a route's `side_effect` **exception**, raise the real
type from `bg_mcpcore.http` (e.g. `ConnectError`) — those pass through
unchanged.

---

## Step 3 — Background tasks need the extension registered

FastMCP 4 moved background tasks out of the core spec into the
`io.modelcontextprotocol/tasks` extension. **A `task=True` tool without the
extension makes the server refuse to start** — loudly, at boot, not on first
call.

If you use the profile's `export` tool source, bg-mcpcore registers it for you
and there is nothing to do. If you declare a task tool by hand:

```diff
 from fastmcp import FastMCP
+from fastmcp_tasks import TasksExtension

 mcp = FastMCP("MyServer")
+mcp.add_extension(TasksExtension())

 @mcp.tool(task=True)
 async def slow_export() -> str:
     ...
```

Make sure the `tasks` extra is installed (`bg-mcpcore[tasks]`). Two more
changes: `task=` is now **tools only** — passing it to `@mcp.resource` or
`@mcp.prompt` raises `TypeError` — and `TaskConfig` moved to
`fastmcp.utilities.tasks`.

On the client side, `call_tool(..., task=True)` raises `TypeError`; a plain
`call_tool` now handles a tasked call transparently.

---

## Step 4 — `ctx.elicit` / `ctx.sample` / `ctx.list_roots`

Only relevant if a hand-written tool calls back into the client mid-request.
The sessionless protocol has no back-channel for that.

| You call | What happens in FastMCP 4 | Do this instead |
| --- | --- | --- |
| `ctx.sample(...)` / `ctx.sample_step(...)` | **Removed** — `AttributeError` | Call an LLM from your server with your own key |
| `ctx.list_roots(...)` | **Removed** — `AttributeError` | Take the paths as tool arguments |
| `ctx.elicit(...)` | Compiles, but **raises at runtime** on a modern connection | Return an `InputRequiredResult` (guard pattern), or branch on `ctx.request_context.protocol_version` |

`ctx.elicit()` is the trap: it still exists, and a default client now negotiates
the modern protocol, so a tool that worked in 3.x fails with
`ToolError: elicitation via server-initiated requests is unavailable on
2026-07-28 connections`. As a stopgap you can pin that server's callers with
`Client(url, mode="legacy")`, but there is no server-side switch to force it.

`ctx.info` and the other logging calls are unaffected on every protocol era.

---

## Step 5 — Behaviour changes to check

**Access gates now allow discovery.** A caller whose tenant or role is not on
the allowlist can complete `server/discover` / `initialize`, and is denied
everything after it — including `tools/list`, so the tool surface stays hidden.
Previously such a caller was refused at connection time. If you assert on that
in your tests, update the expectation; if you relied on connection-time refusal
as a security boundary, note that the denial is now per operation.

**Resource templates are path-screened.** A template parameter that is exactly
`..`, an absolute path, or contains a null byte is refused before your handler
runs, returning a non-leaky "resource not found". Only a *standalone* `..`
counts: `a..b`, `HEAD~3..HEAD`, `v1.2.3` and `.env` all still work, so realistic
REST identifiers are unaffected.

**Resource-not-found changed error code** from `-32002` to `-32602`. Only
matters if a client of yours matches on the number.

**Middleware of your own sees more traffic.** `on_message` now observes every
inbound message, including notifications and requests that fail validation.
`on_request` still sees only requests. `on_initialize` never runs on a modern
connection, and `ctx.set_state` does not persist between calls — if you gated
access in `on_initialize` or kept per-session state, move to per-request checks
and [session state](#what-you-get-for-it).

**`McpError` construction** is keyword-only now:
`McpError(code=-32000, message="...")`. Catching it is unchanged.

---

## Step 6 — OAuth re-authorization (runbook)

Applies to a **narrow, precisely-defined** set of deployments. Most servers,
including every Entra and Google deployment, are not affected. Work the decision
below before scheduling anything.

### Are you affected?

FastMCP 4 corrects a spec violation: the `issuer` published in authorization
server metadata, and the `iss` claim on every token the server **mints**, now
come from `issuer_url` instead of `base_url`. In bg-mcpcore exactly one line can
set `issuer_url` — [`auth/generic_oidc.py`](https://github.com/bauer-group/LIB-BG-MCPCore/blob/main/src/bg_mcpcore/auth/generic_oidc.py) —
and it is reached only on the OIDC **discovery** path. So **all four** of these
must hold at once:

| # | Condition | Why |
| --- | --- | --- |
| 1 | `AUTH_MODE=oidc` | No other auth mode ever passes `issuer_url` |
| 2 | `OIDC_DISCOVERY_URL` is **set** | Only the discovery path (`OIDCProxy`) forwards it |
| 3 | `OIDC_ISSUER` is set and non-empty | The value is applied behind a truthiness guard |
| 4 | `OIDC_ISSUER` differs from `PUBLIC_BASE_URL` | Equal values produce byte-identical metadata |

Run this against a deployment's environment — it answers the question outright:

```bash
python - <<'EOF'
import os
from pydantic import AnyHttpUrl
mode   = os.getenv("AUTH_MODE", "")
disc   = os.getenv("OIDC_DISCOVERY_URL", "")
issuer = os.getenv("OIDC_ISSUER", "")
base   = os.getenv("PUBLIC_BASE_URL", "")
norm   = lambda u: str(AnyHttpUrl(u)) if u else ""
affected = bool(mode == "oidc" and disc and issuer and norm(issuer) != norm(base))
print(f"AUTH_MODE={mode!r} DISCOVERY={'set' if disc else 'unset'}")
print(f"issuer={norm(issuer)!r}
base  ={norm(base)!r}")
print("AFFECTED - schedule a re-auth window" if affected else "NOT AFFECTED - upgrade normally")
EOF
```

Two independent cross-checks, in case you cannot read the environment directly:

```bash
# BEFORE the upgrade — ask the running server what it publishes today.
# If "issuer" already equals your public base URL, nothing changes for you.
curl -s https://mcp.example.com/.well-known/oauth-authorization-server | jq .issuer

# AFTER the upgrade — FastMCP logs this line ONLY when the two differ:
#   "OAuth endpoints at <base_url>, issuer at <issuer_url>."
# Its absence from a start-up log is positive confirmation you were not affected.
```

### Cases that look affected but are not

- **`AUTH_MODE` is anything but `oidc`.** `entra-single`, `entra-multi`,
  `google` and all twelve spec-driven providers construct their provider without
  `issuer_url`; there is no profile or environment route to it.
- **`AUTH_MODE=oidc` with `OIDC_DISCOVERY_URL` unset** — the explicit-endpoint
  path — **regardless of `OIDC_ISSUER`.** This is the important non-obvious one.
  There, `OIDC_ISSUER` configures the `JWTVerifier`'s *expected* issuer for
  tokens the server **receives** from the IdP. That is a different thing from
  `issuer_url`, which is the identity the server **publishes and mints under**.
  The explicit path never passes `issuer_url` at all.
- **An `auth.oidc_issuer_derived` warning in your logs.** That is the explicit
  path guessing the *verifier's* expected issuer from `OIDC_AUTH_URI`. It is
  worth fixing on its own (the guess is wrong for Keycloak), but it has nothing
  to do with this migration.
- **A trailing-slash difference on a bare origin.** `https://mcp.example.com`
  and `https://mcp.example.com/` normalize to the same URL. On a base URL that
  carries a *path* the trailing slash is significant — `…/mcp` and `…/mcp/` do
  not compare equal.

### What breaks, and for how long

Both **access and refresh** tokens carry the `iss` claim, and the verifier
compares it as an exact string — no normalization, no legacy-issuer allowlist,
no grace period. A refresh token minted under the old issuer is rejected before
any exchange logic runs, so **clients cannot refresh their way across the
upgrade**. The only recovery is a full authorization-code round trip.

| Client | Impact |
| --- | --- |
| Interactive (IDE, desktop, browser) | Re-prompted at the consent screen, recovers unattended |
| Headless service holding a long-lived refresh token | **Stays broken until a human re-authorizes it** |
| Dynamically-registered (DCR) clients | Registration survives — re-authorize only, no re-registration |

Client registrations live in the OAuth state store and carry no `iss`, so
nothing needs re-registering and the store needs no migration or purge.

One extra credential to check in the same window: if
`OIDC_IDENTITY_ASSERTION_ISSUERS` is configured, SEP-990 ID-JAG assertions do
**not** survive — their expected audience defaults to the published issuer.
Repoint their `aud` at the IdP, or set `OIDC_IDENTITY_ASSERTION_AUDIENCE` to pin
it, which also makes any future issuer change free.

### Procedure

**Before**

1. Run the check above across every deployment and list the affected ones. Being
   on the affected list is the exception; if everything comes back NOT AFFECTED,
   skip the rest of this step entirely.
2. For each affected server, enumerate its headless clients — those are the ones
   that need a person. Interactive users need warning, not action.
3. Pick a window when a re-consent prompt is acceptable. Announce it.
4. Decide about `OIDC_ISSUER` while you are here. If it is set only because a
   config template carried it over and it *should* equal the base URL, aligning
   the two values before the upgrade both removes the problem and simplifies the
   deployment. Changing it is itself a re-auth event, so do it in the same window.

**During**

5. Deploy the bg-mcpcore 2.0 build.
6. Confirm the published issuer is what you intend:
   `curl -s $PUBLIC_BASE_URL/.well-known/oauth-authorization-server | jq .issuer`
7. Complete one interactive login end to end and call one tool. A `401` with
   `Invalid token issuer` at this point means a client is still presenting an
   old token — expected until it re-authorizes, not a failed deploy.

**After**

8. Re-authorize the headless clients from step 2.
9. Watch for `401`s over the following day; each one is a client that has not
   been through the flow yet.

**Rolling back**

Reverting to 1.x flips `iss` back to the base URL and forces a **second** full
re-authorization — every client that re-authorized after the upgrade breaks
again. Rollback is therefore not free here, which is an argument for validating
on one low-traffic server first rather than planning to undo a fleet-wide change.

## Step 7 — Verify

```bash
pytest -q
FASTMCP_MCP_CAMELCASE_COMPAT=false pytest -q   # surfaces leftover camelCase reads
```

SDK v2 renamed model fields to snake_case (`inputSchema` → `input_schema`,
`isError` → `is_error`, `mimeType` → `mime_type`, ...). Reads of the old names
still work through a compatibility bridge that warns; the second run above turns
those into hard `AttributeError`s so you can find them before the bridge is
removed. Constructing a model with either spelling works today, but write
snake_case in new code.

Then start the server and call one real tool against the live upstream. The two
things worth confirming by hand are the TLS trust change (step 2) and, if it
applies, the OAuth re-authorization (step 6).

---

## What you get for it

Optional, all off by default — an existing profile behaves exactly as before.

**Response caching** — a caching client can skip a round trip:

```json
"cache": { "ttl": 300, "scope": "public" }
```

Applies to `tools/list`, `prompts/list`, `resources/list`,
`resources/templates/list`, `server/discover` and `resources/read` — never to
tool calls. Keep the `"private"` default for anything that varies by caller;
`"public"` allows a *shared* cache to hold the entry.

**Client-credentials outbound auth** — for an upstream that issues service
tokens instead of accepting a static key. Caches and re-mints automatically:

```json
"auth": { "outbound": {
  "type": "client_credentials",
  "token_url": "https://idp.example/oauth/token",
  "client_id_env": "UPSTREAM_CLIENT_ID",
  "client_secret_env": "UPSTREAM_CLIENT_SECRET",
  "scopes": ["api.read"]
}}
```

**Native Entra on-behalf-of** — replaces `per_user_token` on the Entra auth
modes with a supported API (azure-identity's `OnBehalfOfCredential`), and can
request scopes the caller's own token never carried:

```json
"auth": { "outbound": {
  "type": "entra_obo",
  "scopes": ["https://graph.microsoft.com/.default"]
}}
```

Every scope must also appear in the provider's `additional_authorize_scopes`
with admin consent granted. Like `per_user_token`, this is per-call, so it needs
a `python` / `ctx.request` tool surface — the OpenAPI source is not covered.

**Session state** — `MCP_SESSION_STATE_ENABLED=true` points FastMCP's
`UserSession` / `SessionId` at the same encrypted store your OAuth state uses,
so state survives a restart and works behind a load balancer. Requires
authentication.

**Identity assertion (SEP-990)** — lets a corporate IdP assert an employee's
identity to the server without a browser flow:

```bash
OIDC_IDENTITY_ASSERTION_ISSUERS=https://login.acme-corp.com
```

Available on `AUTH_MODE=oidc` only. FastMCP 4.0's `AzureProvider` accepts no
`identity_assertion` argument, so an Entra deployment that wants ID-JAG runs
`AUTH_MODE=oidc` pointed at its Entra endpoints. Marked **beta** by FastMCP —
the API may change in a minor release.

---

## If you cannot migrate yet

Stay on the `v1.6.1` tag. It is frozen, not maintained: there is no 1.x
maintenance branch, so it receives no further fixes, security ones included.
Treat that as a reason to schedule the migration, not to defer it indefinitely.

One case genuinely cannot move: a server whose *purpose* is to borrow the
caller's model via `ctx.sample()`. FastMCP's own guidance is to stay on 3.x
until that server can call an LLM with its own key.

## Rolling out across the fleet

FastMCP 4.0 is young. Migrate one or two low-traffic servers first, let them run
for a few days, then do the rest. Because every repo pins its own tag, a problem
found on the first one costs nothing to the others.

Questions or a case this guide does not cover:
[open an issue](https://github.com/bauer-group/LIB-BG-MCPCore/issues).
