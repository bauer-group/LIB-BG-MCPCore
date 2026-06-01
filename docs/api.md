---
icon: material/api
---

# API reference

This reference is generated directly from the source docstrings, so it can never
drift from the code. It documents the public surface re-exported from
`bg_mcpcore` (everything in `bg_mcpcore.__all__`). For the conceptual model
behind these symbols, start with [core concepts](concepts.md).

```python
from bg_mcpcore import build_app_from_profile, load_profile, make_cli
```

## :material-cog:  Application assembly

::: bg_mcpcore.app.build_app_from_profile

::: bg_mcpcore.cli.make_cli

## :material-file-cog:  Profiles

::: bg_mcpcore.profile.loader.load_profile

::: bg_mcpcore.profile.loader.ProfileError

::: bg_mcpcore.profile.models.Profile

## :material-tune:  Settings

::: bg_mcpcore.settings.base.BaseMcpSettings

::: bg_mcpcore.settings.factory.get_settings

::: bg_mcpcore.settings.enums.Environment

### Settings helpers

::: bg_mcpcore.settings.helpers.validate_persistence

::: bg_mcpcore.settings.helpers.validate_fernet_key

::: bg_mcpcore.settings.helpers.split_csv

::: bg_mcpcore.settings.helpers.has_value

## :material-wrench:  Tools

::: bg_mcpcore.tools.protocol.ToolContext

::: bg_mcpcore.tools.protocol.ToolProvider

::: bg_mcpcore.tools.protocol.ConstructingToolProvider

::: bg_mcpcore.tools.registry.register_tool

::: bg_mcpcore.tools.registry.available_tools

::: bg_mcpcore.plugins.build_tool_provider

## :material-key:  Authentication

### Inbound providers

::: bg_mcpcore.plugins.build_auth_provider

::: bg_mcpcore.plugins.build_auth_middleware

::: bg_mcpcore.auth.generic_oidc.build_generic_oidc_provider

::: bg_mcpcore.auth.generic_oidc.discover_endpoints

::: bg_mcpcore.auth.generic_oidc.OIDCDiscoveryError

### Outbound resolvers

::: bg_mcpcore.plugins.build_outbound_resolver

::: bg_mcpcore.auth.resolvers.AuthHeaderSource

::: bg_mcpcore.auth.resolvers.StaticHeaderResolver

::: bg_mcpcore.auth.resolvers.BearerEnvResolver

::: bg_mcpcore.auth.resolvers.NoAuthResolver

### OAuth-state storage

::: bg_mcpcore.auth.storage.build_client_storage

## :material-web:  Upstream HTTP client

::: bg_mcpcore.http.client.UpstreamClient

## :material-server:  Server runtime

::: bg_mcpcore.server.runner.run_transport

::: bg_mcpcore.server.runner.patch_dual_stack_socket

::: bg_mcpcore.server.middleware.build_rate_limit_middleware

::: bg_mcpcore.server.middleware.resolve_client_id

::: bg_mcpcore.server.routes.register_healthz_route

::: bg_mcpcore.server.routes.register_logo_route

::: bg_mcpcore.server.routes.register_index_route

## :material-chart-line:  Observability

::: bg_mcpcore.observability.setup_logging

::: bg_mcpcore.observability.get_logger

::: bg_mcpcore.observability.init_sentry

::: bg_mcpcore.observability.print_banner
