# Vendored ROSS source

ROSS Studio uses the upstream **ROSS — Rotordynamic Open-Source Software** project from Petrobras.

- Upstream: https://github.com/petrobras/ross
- Pinned commit: `631a249adbae414d5f5f986479b58f1a4c47935e`
- License: Apache License 2.0 (see `vendor/ross/LICENSE.md` after submodule checkout)
- Purpose: keep the scientific solver source versioned with the frontend and make regression tests reproducible.

Clone with submodules:

```bash
git clone --recurse-submodules <ross_frontend repository>
```

Existing clone:

```bash
git submodule update --init --recursive
```

ROSS Studio prefers `vendor/ross` when it is present and falls back to the installed `ross` package only when the submodule is unavailable.
