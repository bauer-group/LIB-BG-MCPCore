<!-- AUTO-GENERATED FILE. DO NOT EDIT. Edit docs/SECURITY.template.MD instead. -->
<!-- Generated on 2026-06-01 12:53:35 UTC -->

# Security Policy

## 🚨 Reporting Security Vulnerabilities

We take the security of bg-mcpcore seriously. As the shared foundation for
BAUER GROUP's REST-API MCP servers, a vulnerability here can affect every
downstream server (bg-zammad-mcp, bg-shlink-mcp, …). Please report responsibly.

### 🎯 Preferred Reporting Method

Report via **GitHub Security Advisories** — a secure, private channel:

1. 🔗 Go to the [Security tab](../../security) of this repository
2. 🖱️ Click "Report a vulnerability"
3. 📝 Fill out the advisory form with detailed information

### 📧 Alternative

- **📬 Email**: security@bauer-group.com
- **🐛 Issues**: for non-sensitive matters only (use your discretion)

### 📋 What to Include

1. **📄 Description** of the vulnerability
2. **💥 Impact** and severity assessment
3. **🔄 Reproduction** steps
4. **🖥️ Environment**: affected versions / configuration
5. **🧪 Proof of Concept** (minimal example, if applicable)
6. **🔧 Suggested Fix** (if you have one)

### ⏱️ Response Timeline

- **⚡ Initial Response**: within 48 hours
- **📊 Status Updates**: weekly during investigation
- **🎯 Resolution**: Critical 1-7d · High 1-14d · Medium 1-30d · Low 1-90d

## 🔐 Supported Versions

| Version | Support Status | Security Updates |
|---------|---------------|------------------|
| v0.0.0 (current) | ✅ Full Support | ✅ Yes |

We provide security updates for supported versions only.

## 🛡️ Security Model (framework-specific)

bg-mcpcore enforces several invariants that downstream servers inherit and
cannot relax:

- **Fail-closed auth**: `AUTH_MODE=none` is forbidden in production, and a JWT
  signing key is mandatory for any active auth mode (`BaseMcpSettings`).
- **Closed-set auth modes**: an unknown `AUTH_MODE` raises at boot rather than
  silently serving an unauthenticated endpoint.
- **Secrets never in profiles**: declarative profiles reference secrets only via
  `value_from_env` / `${env:VAR}`; a missing variable fails closed at boot.
- **Encrypted OAuth state at rest**: DCR/token state is Fernet-encrypted; the
  storage key should be a dedicated `AUTH_STORAGE_ENCRYPTION_KEY` distinct from
  the JWT signing key (a boot warning fires when they are reused).
- **PII/secret log redaction**: a structured-logging processor masks values
  under sensitive-looking keys; servers extend the fragment list additively.
- **Outbound-auth fail-closed**: per-call (on-behalf-of) resolvers must raise
  when no credential is available rather than inheriting a static default.

### 🤖 Automated Scanning

CI runs gitleaks/GitGuardian secret scanning and ruff; dependencies are tracked
via Dependabot. Contributors should run `ruff`, `mypy --strict`, and `pytest`
locally before opening a PR.

## 📚 Best Practices for Operators

1. **🔄 Keep updated** — pin a compatible range (`bg-mcpcore>=X,<X+1`) and let
   Dependabot propose bumps.
2. **🗝️ Secrets** — store credentials in a secret manager / env vars; never in
   profiles or code. Use a dedicated `AUTH_STORAGE_ENCRYPTION_KEY`.
3. **🌐 TLS** — keep `verify_tls` enabled against production upstreams.
4. **🔒 Least privilege** — scope upstream API keys as narrowly as the workflow
   allows; expose only the tools you need.

## 📞 Contact

- **🛡️ Security Team**: via GitHub Security Advisories
- **📧 Primary**: security@bauer-group.com

---

**Current Version**: v0.0.0
**Last Updated**: 2026-06-01 12:53:35 UTC
**Next Review**: June 2027
**Policy Version**: 1.0.0

---

*🤝 Security is everyone's responsibility.*
