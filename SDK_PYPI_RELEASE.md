# SDK Release to PyPI

This guide publishes the `relancify-sdk` package to PyPI.

## 1) Prerequisites

- PyPI account
- Python 3.9+
- Either a PyPI API token or Trusted Publishing (recommended)

## 2) Install build tools

```bash
python3 -m pip install --upgrade build twine
```

## 3) Check the version

Current version must match in:

- `pyproject.toml` -> `project.version`
- `relancify_sdk/__init__.py` -> `__version__`

Both values must be identical.

## 4) Build the package

From the repository root:

```bash
python3 -m build
```

Artifacts generated in `dist/`:

- `relancify_sdk-<version>-py3-none-any.whl`
- `relancify_sdk-<version>.tar.gz`

## 5) Validate artifacts before upload

```bash
python3 -m twine check dist/*
```

## 6) Publish to PyPI

```bash
python3 -m twine upload dist/*
```

Authentication:

- Username: `__token__`
- Password: your PyPI token (`pypi-...`)

## 6b) Publish without manual tokens (recommended)

The repository includes this workflow:

- `.github/workflows/publish-sdk-pypi.yml`

Process:

1. Configure **Trusted Publishing** in PyPI (`relancify-sdk`) for this GitHub repo.
2. Push a release tag:

```bash
git tag sdk-v0.1.0
git push origin sdk-v0.1.0
```

3. GitHub Actions builds and publishes automatically to PyPI (OIDC, no PyPI token in GitHub secrets).

## 7) Installation test

```bash
python3 -m pip install --upgrade relancify-sdk
python3 -c "import relancify_sdk; print(relancify_sdk.__version__)"
```

## 8) Next release

1. Bump version in:
   - `pyproject.toml`
   - `relancify_sdk/__init__.py`
2. Rebuild and publish.

## Local build troubleshooting

If your environment cannot reach the internet to create isolated build envs:

```bash
python3 -m build --no-isolation
```

## Security checklist

- Never commit `.pypirc` or tokens to git.
- Use Trusted Publishing whenever possible.
- Protect release tags and main branch in GitHub.
- Enable PyPI 2FA for project maintainers.
