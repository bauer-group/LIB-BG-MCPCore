---
icon: material/wrench
---

# Tool sources

An MCP server built with `bg-mcpcore` exposes **tools** — the callable
operations an MCP client (Claude, an agent, an IDE) can invoke. Where those
tools come from is decided entirely by the profile's `tools` block: you declare
a **tool source**, and the assembler turns it into a live FastMCP surface.

There are three built-in sources — `openapi`, `python`, and `registry` — and you
can compose several of them in one server. This page explains each source, how
they combine, and every declarative knob for shaping the generated surface.

!!! info "Where this fits"
    Tool sources are the heart of the [three tiers](tiers.md): Tier 1 is a pure
    `openapi` server, Tier 2 mixes `openapi` with a `python` source, and a
    registry-only server needs no backend at all. The full `tools` schema lives
    in the [profile reference](profiles.md); environment wiring is covered in
    [configuration](usage.md).

## :material-format-list-bulleted-square:  The three sources at a glance

| Source | Use it when | Needs a backend? | Python required? |
| ------ | ----------- | ---------------- | ---------------- |
| `openapi` | The backend already publishes an OpenAPI 3 spec — generate the whole surface from it | **Yes** (`profile.backend`) | No — config only |
| `python` | You need hand-written, composite, or opinionated tools that no spec describes | Optional (client may be `None`) | Yes — a register callable |
| `registry` | You want ready-made, reusable tools mounted by name (`bg.ping`, `bg.health`) | Optional | No — config only |

Two of these only ever **add** tools to an existing FastMCP instance; one of
them **builds** the instance itself. That distinction is the construct-vs-register
fork, modelled by two protocols in `tools/protocol.py`:

- **`ToolProvider`** — `async register(mcp, ctx) -> int`. Mutates an existing
  FastMCP instance and returns how many tools it added. Both `python` and
  `registry` are of this kind.
- **`ConstructingToolProvider`** — `async construct(...) -> FastMCP`. Builds the
  FastMCP instance from a spec. Only `openapi` is of this kind, and a server may
  have **at most one** constructing source.

### The ToolContext

Every source's callable receives a `ToolContext` (`tools/protocol.py`), carrying
the dependencies a tool needs at registration time:

| Field | What it is |
| ----- | ---------- |
| `settings` | The typed settings object (with its `SecretStr` fields) — or `None` |
| `client` | An authenticated `UpstreamClient`, or `None` for a backend-less server |
| `logger` | A structured logger bound to the server |

It also offers a convenience method for upstream calls:

```python
await ctx.request("GET", "/short-urls", params={"page": 1})
```

`ctx.request(...)` routes an authenticated call through the outbound resolver.

!!! warning "Backend-less servers"
    `client` is `None` when the profile declares no `backend` (e.g. a
    registry-only server). Calling `ctx.request(...)` on such a context raises
    `RuntimeError: This server has no upstream backend configured`. The built-in
    `bg.health` tool handles this gracefully and reports `{"status": "no-backend"}`.

### :material-shield-account: Least privilege: who gets `settings` { #least-privilege-who-gets-settings }

This is a security guardrail, not a convention. The assembler (`app.py`) builds
**two** contexts and hands each source exactly the one it is entitled to:

- **`python`** — the server's own trusted code — receives the **full** context,
  including `settings` (and thus the server's secrets).
- **`openapi`** and **`registry`** (and any third-party source) receive a
  **settings-less** context: `settings` is `None`, but the authenticated `client`
  is still available.

!!! danger "The boundary is enforced, not documented"
    OpenAPI- and registry-sourced tools never see `settings`. The assembler
    passes `ctx_scoped` (with `settings=None`) to everything except the `python`
    source. Do not design a registry tool that expects `ctx.settings` — it will
    be `None` by construction.

---

## :material-api:  openapi — generate the surface from a spec

The `openapi` source builds the entire FastMCP server from an OpenAPI 3 document
via `FastMCP.from_openapi`. It is a **constructing** source: it produces the
FastMCP instance rather than adding to one. This source lives behind the
`[openapi]` extra.

```bash
uv add "bg-mcpcore[openapi]"   # pulls in pyyaml for YAML specs
```

!!! note "Requires a backend"
    The `openapi` source drives the upstream API, so the profile **must** declare
    a `backend`. Without one the provider raises
    `ProfileError: tools.source 'openapi' requires a backend (profile.backend)`.

### The spec block

The minimum is a `spec.source`; everything else is optional shaping.

| Field | Meaning |
| ----- | ------- |
| `spec.source` | **Required.** Where to load the spec from (see below) |
| `spec.timeout` | Fetch timeout in seconds for remote specs (default `30`) |

`spec.source` accepts (per `openapi/loader.py`):

- a **bare filesystem path** — including a Windows path like `C:\specs\api.json`
- a **`file://` URL** — resolved cross-platform
- an **`http://` / `https://` URL** — fetched with `httpx` (redirects followed)

JSON is parsed with the standard library. **YAML** specs are detected
automatically and parsed lazily via `pyyaml` from the `[openapi]` extra; without
it a YAML spec raises a clear "install bg-mcpcore[openapi]" error. External
`$ref` pointers (modular, unbundled specs) are resolved at load time. A spec
that parses but yields **zero operations** (empty or unresolved `paths`) is
rejected with a `SpecLoadError`.

!!! note "Static outbound header is baked in"
    The provider hands `FastMCP.from_openapi` the `UpstreamClient`'s **raw httpx
    client** (`ctx.client.httpx_client`), whose default headers already carry the
    static outbound credential resolved from the profile's `auth.outbound`. Every
    generated tool therefore calls the backend pre-authenticated. See
    [authentication](authentication.md) for outbound-auth wiring.

### Shaping knobs

All of the following are read **declaratively** off the `tools` block. None
require Python.

#### `route_maps` — classify operations

Each entry maps a path **`pattern`** (regex) to an MCP component **`type`**.
Matched the way FastMCP route maps work; the first matching entry wins.

| `type` | Result |
| ------ | ------ |
| `tool` | Expose the operation as a callable tool (the default) |
| `resource` | Expose it as an MCP resource |
| `resource_template` | Expose it as a parameterised resource template |
| `exclude` | Drop the operation entirely |

```jsonc
"route_maps": [
  { "pattern": "^/short-urls/[^/]+$", "type": "resource_template" },
  { "pattern": "^/health$",           "type": "exclude" }
]
```

!!! warning "Malformed entries raise ProfileError"
    An entry without a `pattern` raises
    `ProfileError: Each tools.route_maps entry requires a 'pattern'`. An
    unrecognised `type` raises
    `ProfileError: Unknown route_map type '...'; expected one of ['exclude', 'resource', 'resource_template', 'tool']`.

#### `name_overrides` — rename tools

OpenAPI `operationId`s are often machine-ugly. Override them with readable names
keyed by **`"METHOD /path"`** — where `/path` is the path **after**
`strip_path_prefix` normalisation (see below):

```jsonc
"name_overrides": {
  "POST /short-urls":        "create_short_url",
  "GET /short-urls/{short}": "get_short_url"
}
```

Internally these are translated into FastMCP's `{operationId: name}` map by
matching method + normalised path against the spec.

#### `descriptions` — override tool descriptions

Replace the spec-derived description of a tool, keyed by its **final** name —
i.e. the name **after** any `name_overrides` rename:

```jsonc
"descriptions": {
  "create_short_url": "Create a short URL. Returns the short code and full URL."
}
```

#### `annotations` — safety hints by HTTP method

When `annotations` is set to `"by_http_method"` (the default), each generated
tool gets MCP `ToolAnnotations` derived from its HTTP verb. This is a
defense-in-depth signal — clients may surface it to gate auto-execution.

| Method | `readOnlyHint` | `destructiveHint` | `idempotentHint` |
| ------ | -------------- | ----------------- | ---------------- |
| `GET` | `true` | `false` | — |
| `POST` | `false` | `true` | `false` |
| `PUT` | `false` | `true` | `true` |
| `PATCH` | `false` | `true` | `true` |
| `DELETE` | `false` | `true` | `true` |

All five also set `openWorldHint: true`. In short: **GET is read-only;
POST/PUT/PATCH/DELETE are flagged destructive.** Set `annotations` to any other
value to disable this behaviour.

#### `normalize.strip_path_prefix` — trim versioned prefixes

Many APIs prefix every path with something like `/rest/v{version}`. Strip it so
your tool names and route patterns stay clean. The freed-up path parameter
(here `version`) is also removed from each operation's parameters.

```jsonc
"normalize": { "strip_path_prefix": "/rest/v{version}" }
```

The `{version}` placeholder matches a concrete version number too, so both
`/rest/v3/short-urls` and `/rest/v{version}/short-urls` normalise to
`/short-urls`. Remember: `name_overrides` and `route_maps` patterns operate on
the **normalised** path.

### A full annotated openapi profile

```jsonc
{
  "id": "shlink",
  "display_name": "Shlink URL Shortener",
  "instructions": "Create and analyse short URLs.",
  "backend": {
    "base_url": "https://go.example.com",
    "verify_tls": true
  },
  "auth": {
    "outbound": {
      "type": "static_header",
      "header": "X-Api-Key",
      "value_from_env": "SHLINK_API_KEY"   // secret stays in the env
    }
  },
  "tools": {
    "source": "openapi",
    "spec": {
      "source": "https://go.example.com/rest/v3/openapi.json",
      "timeout": 20
    },
    "normalize": { "strip_path_prefix": "/rest/v{version}" },
    "route_maps": [
      { "pattern": "^/short-urls/[^/]+/visits$", "type": "resource_template" },
      { "pattern": "^/mercure-info$",            "type": "exclude" }
    ],
    "name_overrides": {
      "POST /short-urls":        "create_short_url",
      "GET /short-urls":         "list_short_urls",
      "DELETE /short-urls/{shortCode}": "delete_short_url"
    },
    "descriptions": {
      "create_short_url": "Create a short URL and return its short code and full URL."
    },
    "annotations": "by_http_method"
  }
}
```

!!! tip "Adding a vanilla OpenAPI backend is a config-only job"
    No Python is written. The profile fully describes route classification,
    naming, descriptions, and safety annotations — the same shaping a hand-rolled
    server would otherwise hard-code.

---

## :material-language-python:  python — the escape hatch

When no spec can express what you need — composite tools that orchestrate several
upstream calls, tools with bespoke validation, or anything genuinely
hand-written — use the `python` source. It is a **registering** source: it adds
tools to the FastMCP instance.

You point it at a dotted path to a **register callable** via the `register` key:

```jsonc
"tools": {
  "source": "python",
  "register": "myserver.tools:register"
}
```

The callable's contract is `(mcp, ctx) -> int`:

- It receives the FastMCP instance and the **full** `ToolContext`.
- It may be **synchronous or asynchronous** — both are awaited correctly.
- It should **return the number of tools** it registered (a non-`int` return is
  treated as `0`).

!!! note "Only this source receives `settings`"
    The `python` source is the server's own trusted code, so it gets the full
    context: `ctx.settings`, the authenticated `ctx.client`, and `ctx.request(...)`.
    This is the **only** source that sees `settings` — see
    [Least privilege](#least-privilege-who-gets-settings) above.

=== "async register"

    ```python
    from fastmcp import FastMCP
    from bg_mcpcore.tools.protocol import ToolContext


    async def register(mcp: FastMCP, ctx: ToolContext) -> int:
        @mcp.tool
        async def create_and_tag(long_url: str, tag: str) -> dict:
            """Create a short URL and tag it in one step."""
            created = await ctx.request(
                "POST", "/short-urls", json={"longUrl": long_url}
            )
            short_code = created.json()["shortCode"]
            await ctx.request(
                "PATCH", f"/short-urls/{short_code}", json={"tags": [tag]}
            )
            return created.json()

        return 1
    ```

=== "sync register"

    ```python
    from fastmcp import FastMCP
    from bg_mcpcore.tools.protocol import ToolContext


    def register(mcp: FastMCP, ctx: ToolContext) -> int:
        @mcp.tool
        async def echo(text: str) -> str:
            """Return the input unchanged."""
            return text

        return 1
    ```

In the async example, `create_and_tag` is a **composite tool**: a single MCP
operation that fans out to two authenticated upstream calls via `ctx.request`.
That is exactly the kind of opinionated, multi-step tool no OpenAPI spec
produces on its own — the reason the escape hatch exists.

!!! tip "`register` is required"
    A `python` source without a `register` value raises
    `ProfileError: tools.source 'python' requires 'register' (dotted module:attr)`.
    The dotted path accepts both `module.path:attr` and `module.path.attr` forms.

---

## :material-format-list-bulleted:  registry — mount reusable tools by name

The `registry` source mounts **named, reusable tool factories** from a central
registry (`tools/registry.py`) onto your server. List the ones you want under
`include`:

```jsonc
"tools": {
  "source": "registry",
  "include": ["bg.ping", "bg.health"]
}
```

Two tools ship in core:

| Name | What it does |
| ---- | ------------ |
| `bg.ping` | Adds a `ping` tool that returns `"pong"` — a trivial liveness check |
| `bg.health` | Adds an `upstream_health` tool reporting whether the backend is reachable (`ok` / `degraded` / `unreachable`, or `no-backend` when the server has no client) |

!!! note "Settings-less, like openapi"
    Registry tools receive the **settings-less** context. They get the
    authenticated `ctx.client` (so `bg.health` can probe the backend) but never
    `ctx.settings`.

!!! warning "Unknown tools raise ProfileError"
    An `include` entry that names no registered tool raises a `ProfileError`
    listing what is available, e.g.
    `Unknown registry tool 'bg.pong'. Available: bg.health, bg.ping`.

### Publishing more registry tools

The registry is extensible without touching core. Register a factory in code
with `register_tool(name, factory)`, or — for pip-installable packages —
contribute it via the **`bg_mcpcore.tools` entry-point group**, which is
discovered lazily on first registry use. See [writing plugins](plugins.md) for
the full entry-point pattern.

---

## :material-vector-combine:  Multi-source composition

`tools` may be a **single object** or a **list**. As a list, sources compose:
the constructing source (if any) builds the instance, and every registering
source adds onto it.

```jsonc
"tools": [
  {
    "source": "openapi",
    "spec": { "source": "https://api.example.com/openapi.json" },
    "name_overrides": { "POST /things": "create_thing" }
  },
  {
    "source": "python",
    "register": "myserver.extra_tools:register"
  },
  {
    "source": "registry",
    "include": ["bg.health"]
  }
]
```

This is the **Tier-2 pattern**: a generated OpenAPI surface, augmented with a
handful of hand-written composite tools and a reusable health check. The
assembler resolves it like so (`app.py`):

1. The single `openapi` source **constructs** the FastMCP instance from the spec.
2. The `python` source then **registers** its tools onto that instance, with the
   full context (it sees `settings`).
3. The `registry` source registers `bg.health` with the settings-less context.

!!! warning "At most one constructing source"
    A server may declare only one constructing (`openapi`) source. Two raise
    `ProfileError: At most one constructing tool source (e.g. openapi) is allowed`.
    Registering sources (`python`, `registry`) have no such limit — list as many
    as you like.

!!! tip "Order and roles"
    Put the constructing source anywhere in the list; the assembler separates
    constructing from registering sources by capability, not position. A list of
    purely registering sources (e.g. `python` + `registry`) builds a bare FastMCP
    instance first, then layers each source onto it.

---

## :material-alert-circle:  Errors

Every misconfiguration in the `tools` block surfaces as a single, consistent
exception type — **`ProfileError`** — so a bad profile fails fast and loudly at
startup rather than booting a broken server.

| Trigger | Message (abridged) |
| ------- | ------------------ |
| Unknown `source` | `Unknown tools.source '...'. Known: python, registry, openapi` |
| Unknown registry tool in `include` | `Unknown registry tool '...'. Available: ...` |
| `route_maps` entry missing `pattern` | `Each tools.route_maps entry requires a 'pattern'` |
| `route_maps` entry with bad `type` | `Unknown route_map type '...'; expected one of [...]` |
| `python` source without `register` | `tools.source 'python' requires 'register' (...)` |
| `openapi` source without `spec.source` | `tools.source 'openapi' requires spec.source` |
| `openapi` source without a backend | `tools.source 'openapi' requires a backend (profile.backend)` |
| More than one constructing source | `At most one constructing tool source (e.g. openapi) is allowed` |

!!! info "See also"
    [The three tiers](tiers.md) · [Profile reference](profiles.md) ·
    [Writing plugins](plugins.md) · [Configuration](usage.md)
