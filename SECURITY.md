# Security Guidelines

This repository includes SDK packaging and release automation. Follow these rules:

## Secrets

- Do not commit API keys, SMTP credentials, JWT secrets, or PyPI tokens.
- Do not commit `.env`, `.pypirc`, or private key files.
- Use environment variables or your CI secret store.

## PyPI publishing

- Prefer Trusted Publishing (OIDC) over API tokens.
- Keep `publish-sdk-pypi.yml` restricted to signed release tags (`sdk-v*`).
- Protect the `main` branch and release tags in GitHub settings.

## Credential hygiene

- Rotate compromised credentials immediately.
- Enable 2FA on GitHub and PyPI accounts.
- Scope tokens to the minimum permissions required.

## Reporting

If you discover a security issue, report it privately to the project maintainers before public disclosure.
