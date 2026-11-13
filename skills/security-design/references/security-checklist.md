# Security checklist

Use when no project security skill covers the topic. Apply only the sections the change touches, and record the threats you considered in the plan.

## Quick threat model (STRIDE)
For each new entry point, data flow or trust boundary, ask: **S**poofing, **T**ampering, **R**epudiation, **I**nformation disclosure, **D**enial of service, **E**levation of privilege. Keep the threats that are plausible and give each a mitigation.

## Input and output
- Validate type, length, format and range at the trust boundary; reject rather than sanitize when possible.
- Parameterized queries only (no string-built SQL, LDAP, XPath or NoSQL queries).
- No shell command built from user input; if unavoidable, pass arguments as a list without a shell.
- Path handling: normalize and check against an allowed root (path traversal); never trust file names from users.
- Encode output for its context (HTML, JSON, CSV, logs) to prevent injection.
- Safe deserialization only (no pickle, BinaryFormatter or YAML full loaders on untrusted data).
- Outbound requests built from user input: allow-list hosts to prevent SSRF.

## Identity and access
- Authenticate every entry point; authorize every operation on the server side, per resource (no IDOR).
- Least privilege for services, tokens and database accounts.

## Secrets and data
- No secrets in code, configuration files, logs, error messages or test fixtures; use the project's secret store.
- Classify the data touched (personal, financial, health, credentials) and minimize collection, retention and exposure.
- Use well-known cryptographic libraries and current algorithms; never roll your own crypto.

## Dependencies and supply chain
- New dependency: maintained, licensed compatibly, no known critical vulnerability, pinned version.

## Logging and audit
- Log security-relevant events (authentication, authorization failures, admin actions) without sensitive data.
