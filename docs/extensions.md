---
icon: material/puzzle
---

# Extensions

**Extensions** are the config-driven prompts + resources layer that sits *on top of* the tool surface. They let an operator add two more MCP primitives — reusable **prompt templates** and read-only **resources / resource templates** — declaratively from a JSON catalogue, **without writing any tool code**.

Where [tool sources](tools.md) expose *actions* (OpenAPI operations, Python functions, registry tools), extensions expose:

- **Prompts** — reusable, parameterised prompt templates (`${name}` placeholders) the AI client can fill in and replay.
- **Resources** — read-only `GET` calls against your backend, surfaced as MCP resources (static URI) or resource templates (parameterised URI).

!!! note "What extensions are *not*"
    Extensions are intentionally limited to **declarative prompts and read-only GET resources**. They are not a place for write operations, bespoke bulk exporters, or business logic — those belong in a [Python tool source](tools.md). Remote catalogue sources are also unsupported by design: the catalogue is server-side trust (baked into the image or a mounted volume), never pulled from the network.

---

## :material-help-circle:  When to use them

| Goal | Use |
| --- | --- |
| Ship a reusable, fill-in-the-blanks prompt to clients | **Prompt** extension |
| Expose a read-only upstream `GET` (e.g. a record, a summary) as an addressable resource | **Resource** extension |
| Expose a *family* of read-only records keyed by an id (`item/123`, `item/456`) | **Resource template** (parameterised URI) |
| Perform a write, compose multiple calls, or run custom logic | A [Python tool source](tools.md) — **not** an extension |

The whole point is that prompts and resources are common enough that hand-writing a tool for each is wasteful. A catalogue file covers them with validation and no code.

---

## :material-cable-data:  Wiring

### The profile `extensions` block

A profile opts into extensions with an optional `extensions` block (`ExtensionsRef`). It has exactly two fields and is strict (`extra="forbid"` — a typo fails at boot):

| Field | Type | Default | Meaning |
| --- | --- | --- | --- |
| `source` | string | *(required)* | `file://` URL **or** a bare path to the catalogue JSON |
| `required` | boolean | `false` | If `true`, a missing/unreadable catalogue is a fatal boot error |

```jsonc
{
  "id": "petstore",
  "display_name": "BG Petstore",
  "backend": { "base_url": "https://petstore.example.com" },
  "tools": { "source": "openapi", "spec": { "source": "petstore-mini.json" } },
  "extensions": {
    "source": "file:///etc/mcp/extensions.json",
    "required": false
  }
}
```

The `source` accepts a `file://` URL or a bare filesystem path; both forms are resolved on the local filesystem. Any other scheme is rejected.

### What `build_app_from_profile` does

After the tool surface is registered, the assembler layers extensions on top by calling `load_extensions` with the **same outbound HTTP client** that the tools use:

```python
if profile.extensions is not None:
    from .extensions import load_extensions

    load_extensions(
        mcp,
        config_source=profile.extensions.source,
        client=client,
        required=profile.extensions.required,
    )
```

`load_extensions` reads + validates the catalogue, registers every prompt, and — if a `client` exists — registers every resource and resource template. It returns counters:

```python
{"prompts": <int>, "resources": <int>, "templates": <int>}
```

where `resources` counts static-URI entries and `templates` counts parameterised-URI entries.

!!! tip "Resources reuse the same outbound auth as your tools"
    Resource `GET`s are issued through the profile's `UpstreamClient` — the exact same client (with its `base_url`, `api_base_path`, timeouts, retry/backoff, and **outbound auth resolver**) that serves the tool surface. For a `static_header` (or `bearer_env`) outbound backend, the credential is folded into the client's default headers, so resource calls are authenticated automatically. You configure outbound auth once in the profile; extensions inherit it. See [authentication](authentication.md) for the outbound-auth types.

!!! warning "Resources require a backend"
    Prompts need no backend and are always registered. Resources call upstream, so they need a client. If the catalogue declares `resources` but the profile has **no `backend`** (hence no client), `load_extensions` raises `ExtensionsConfigError`. A catalogue of prompts only works on a backend-less server.

---

## :material-message-text:  Prompts

A prompt entry (`PromptConfig`) becomes a FastMCP prompt whose body is the result of `string.Template(template).substitute(**kwargs)`. The function signature is synthesised at registration so FastMCP can introspect the arguments (no `exec()` is used).

### Prompt catalogue entry

| Field | Type | Required | Notes |
| --- | --- | --- | --- |
| `name` | string | yes | Prompt name shown to the client. Must be a valid identifier (`^[a-zA-Z_][a-zA-Z0-9_]*$`). |
| `template` | string | yes | Body with `${name}` placeholders. |
| `arguments` | list | no | Declared arguments (see below). Default: empty. |
| `title` | string | no | Optional display title. |
| `description` | string | no | Optional description. |
| `tags` | list of string | no | Optional tags. |

Each entry in `arguments` (`PromptArgumentConfig`):

| Field | Type | Default | Notes |
| --- | --- | --- | --- |
| `name` | string | *(required)* | Argument name *and* `${name}` placeholder. Must be a valid identifier. |
| `type` | `"string"` \| `"integer"` \| `"number"` \| `"boolean"` | `"string"` | Python annotation used in the synthesised signature. |
| `required` | boolean | `false` | If `false` and no `default`, a zero-value default (e.g. `""`, `0`) is supplied. |
| `default` | string \| int \| float \| bool \| null | `null` | If set, must match `type` (a `bool` is *not* accepted for `integer`). |
| `description` | string | `""` | Optional. |

!!! note "Substituted values are stringified"
    At call time every supplied argument is converted with `str(...)` before substitution, so the `type` is an interface/introspection hint for the client — the rendered template is always text.

### Placeholder ↔ arguments validation

The catalogue is validated strictly so a mistake fails loudly at boot rather than producing a broken prompt:

- **Every placeholder in `template` must be declared in `arguments`.** An undeclared placeholder is rejected.
- **Every declared argument must be used in `template`.** A declared-but-unused argument is rejected.
- Both `${name}` and bare `$name` forms are recognised as placeholders.
- **`$$` is a literal-`$` escape** (as in `string.Template`). It is stripped before scanning, so `cost is $$5 for ${item}` renders `cost is $5 for <item>` and is **not** misread as a `$5` / `item` placeholder pair.

| Template | `arguments` | Result |
| --- | --- | --- |
| `Hello ${who}` | `[who]` | OK |
| `Hi ${missing}` | `[]` | Rejected — undeclared placeholder `missing` |
| `Hi there` | `[who]` | Rejected — `who` declared but never used |
| `cost is $$5 for ${item}` | `[item]` | OK — `$$` is a literal `$`, not a placeholder |

### Full prompt example

```jsonc
{
  "prompts": [
    {
      "name": "triage_ticket",
      "title": "Triage a support ticket",
      "description": "Draft a triage summary and a suggested priority.",
      "arguments": [
        { "name": "subject",  "type": "string",  "required": true,
          "description": "The ticket subject line." },
        { "name": "priority", "type": "string",  "required": false,
          "default": "normal",
          "description": "Suggested priority (low|normal|high)." }
      ],
      "template": "You are a support agent. Triage the ticket titled \"${subject}\".\nProposed priority: ${priority}.\nReturn a one-paragraph summary and the next action.",
      "tags": ["support", "triage"]
    }
  ]
}
```

!!! tip "One bad entry does not sink the rest"
    Within a **valid** catalogue, a single prompt that fails to register is logged and skipped — it does not abort the others. (A catalogue that is itself unreadable or schema-invalid is a different matter; see [Failure behavior](#failure-behavior).)

---

## :material-file-document:  Resources & resource templates

A resource entry (`ResourceConfig`) becomes either a **static resource** (URI has no `{placeholder}`) or a **resource template** (URI has one or more `{placeholder}` segments). At call time the `_runner` issues a `GET` to `backend.path` through the `UpstreamClient` and returns the body.

### Resource catalogue entry

| Field | Type | Required | Notes |
| --- | --- | --- | --- |
| `uri` | string | yes | `<scheme>://...` URI. `{name}` segments make it a **template**. |
| `name` | string | yes | Resource name. |
| `backend` | object | yes | The upstream call (see `BackendCall`). |
| `mime_type` | string | no | Default `application/json`. |
| `title` | string | no | Optional display title. |
| `description` | string | no | Optional. |
| `tags` | list of string | no | Optional. |

`backend` (`BackendCall`):

| Field | Type | Default | Notes |
| --- | --- | --- | --- |
| `method` | `"GET"` | `"GET"` | Resources are read-only; `GET` is the only allowed method. |
| `path` | string | *(required)* | Upstream path, **relative to** `backend.api_base_path`. Must start with `/`. May contain `{name}` placeholders. |

!!! warning "The URI must carry a scheme"
    `uri` must match `<scheme>://` (e.g. `petstore://`, `svc://`). A bare value like `no-scheme` is rejected. By convention servers use their profile id as the scheme, but any valid scheme is accepted.

### Static URI vs parameterised URI

- A URI **without** placeholders → a **static resource**. Counted under `resources`.
- A URI **with** `{name}` placeholders → a **resource template**. Counted under `templates`. Each placeholder becomes a keyword-only `str` parameter of the synthesised runner.

The placeholder sets on both sides must be **identical**: the set of `{name}` in `uri` must equal the set of `{name}` in `backend.path`. A mismatch (e.g. URI `{id}` but path `{pet_id}`) is rejected at load time.

```jsonc
// static resource: uri and path have no placeholders
{ "uri": "petstore://inventory", "name": "inventory",
  "backend": { "path": "/store/inventory" } }

// resource template: {id} appears in BOTH uri and backend.path
{ "uri": "petstore://pet/{id}", "name": "pet",
  "backend": { "path": "/pets/{id}" } }
```

### How the runner works (json vs text)

On invocation the runner:

1. Substitutes each `{name}` in `backend.path` with the supplied value.
2. Issues `GET <path>` via `client.request(...)` (so `api_base_path`, outbound auth, timeouts and retry/backoff all apply) and calls `raise_for_status()`.
3. Decodes the body: if the response `content-type` contains `json` **or** the entry's `mime_type` is `application/json`, it returns `response.json()`; otherwise it returns `response.text`.

!!! warning "Path params are percent-encoded — a value can't escape its segment"
    Each placeholder value is percent-encoded with `urllib.parse.quote(value, safe="")` before substitution, because `httpx` does not re-encode interpolated path strings. This means `/` and other reserved characters in a value are escaped (`abc/visits` → `abc%2Fvisits`), so a malicious or accidental value **cannot break out of its path segment** and traverse to another endpoint. This is a deliberate security property of resource templates.

### Full resource example

```jsonc
{
  "resources": [
    {
      "uri": "petstore://inventory",
      "name": "inventory",
      "title": "Store inventory",
      "description": "Current stock counts by status.",
      "mime_type": "application/json",
      "backend": { "method": "GET", "path": "/store/inventory" }
    },
    {
      "uri": "petstore://pet/{id}",
      "name": "pet",
      "title": "Pet by id",
      "description": "A single pet record.",
      "backend": { "path": "/pets/{id}" },
      "tags": ["catalog"]
    }
  ]
}
```

The first entry registers as a static **resource** (`resources: 1`); the second, with `{id}` in both `uri` and `path`, registers as a **resource template** (`templates: 1`).

---

## :material-format-list-bulleted-square:  Complete catalogue + profile

A full catalogue combining prompts, a static resource, and a resource template:

```jsonc
// /etc/mcp/extensions.json
{
  "$schema": "https://raw.githubusercontent.com/bauer-group/LIB-BG-MCPCore/main/src/bg_mcpcore/extensions/schema.json",
  "prompts": [
    {
      "name": "summarise_pet",
      "title": "Summarise a pet",
      "arguments": [
        { "name": "name",   "type": "string",  "required": true },
        { "name": "status", "type": "string",  "required": false, "default": "available" }
      ],
      "template": "Summarise the pet \"${name}\" (status: ${status}) for a customer.",
      "tags": ["catalog"]
    }
  ],
  "resources": [
    {
      "uri": "petstore://inventory",
      "name": "inventory",
      "description": "Current stock counts by status.",
      "backend": { "path": "/store/inventory" }
    },
    {
      "uri": "petstore://pet/{id}",
      "name": "pet",
      "description": "A single pet record by id.",
      "backend": { "path": "/pets/{id}" }
    }
  ]
}
```

!!! note "Uniqueness"
    Within one catalogue, `prompt` names must be unique and `resource` URIs must be unique; duplicates are rejected at load time.

The profile that references it (a backend is present, so resources can resolve):

```jsonc
{
  "$schema": "https://raw.githubusercontent.com/bauer-group/LIB-BG-MCPCore/main/src/bg_mcpcore/profile/schema.json",
  "id": "petstore",
  "display_name": "BG Petstore",
  "backend": { "base_url": "https://petstore.example.com", "api_base_path": "" },
  "auth": {
    "inbound":  { "mode": "none" },
    "outbound": { "type": "bearer_env", "value_from_env": "PETSTORE_TOKEN" }
  },
  "tools": { "source": "openapi", "spec": { "source": "petstore-mini.json" } },
  "extensions": {
    "source": "file:///etc/mcp/extensions.json",
    "required": true
  }
}
```

Loading this catalogue yields counts `{"prompts": 1, "resources": 1, "templates": 1}`.

---

## :material-alert-circle: Failure behavior { #failure-behavior }

The failure policy is **fail fast on the catalogue, tolerate one bad entry**:

| Situation | Behavior |
| --- | --- |
| `source` missing and `required: false` | Skipped — `{"prompts": 0, "resources": 0, "templates": 0}`, logged as `extensions.skipped_no_config`. |
| `source` missing and `required: true` | **Fatal** — raises `ExtensionsConfigError`. |
| Catalogue is not valid JSON | **Fatal** — raises `ExtensionsConfigError`. |
| Catalogue is valid JSON but fails schema validation (unknown field, bad placeholder match, missing scheme, duplicate id, …) | **Fatal** — raises `ExtensionsConfigError`. |
| Catalogue declares `resources` but the profile has no backend/client | **Fatal** — raises `ExtensionsConfigError`. |
| A single prompt or resource entry fails to *register* (valid catalogue) | Logged and **skipped**, the rest continue. |

!!! note "`required: true` for production"
    Set `required: true` when the catalogue is essential to the server's behavior, so a misplaced or unreadable file stops the boot instead of silently launching a server with missing prompts and resources. Leave it `false` for optional, environment-specific overlays.

---

## :material-link-variant:  See also

- [tool sources](tools.md) — the action surface extensions layer on top of
- [profile reference](profiles.md) — the full profile schema, including the `extensions` and `backend` blocks
- [configuration](usage.md) — outbound-auth types and environment-supplied secrets
