# Publishing

## Local Verification

```bash
python -m pytest -q
python -m contextprime_domain --json list-packs
```

## GitHub Push

From the repository root:

```bash
git add .
git commit -m "Initial standalone release of contextprime-domain"
git remote add origin <your-github-repo-url>
git push -u origin main
```

## Optional Package Publish

```bash
python -m build
twine upload dist/*
```

## Notes

- This repository ships with the MIT license in `LICENSE`.
- If you publish to PyPI, keep the distribution name as `contextprime-domain`
  and the import package as `contextprime_domain`.
