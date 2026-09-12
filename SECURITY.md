# Security notes

This repository is a reference/portfolio implementation and should not be exposed to untrusted networks as-is.

Before production use, add authentication and authorization, secret management, TLS at the deployment boundary, request-size limits, downstream credential isolation, audit retention rules and dependency/security scanning.

Do not place credentials, API keys, customer data or production payloads in the repository. Runtime secrets should be injected through the deployment environment or an appropriate secret manager.

RPA platform adapters should use platform-managed credentials where possible and should never return secrets in execution details or logs.
