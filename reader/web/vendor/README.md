# Mermaid browser bundle

- Package: `mermaid` 11.12.2
- File: `mermaid.min.js`, the complete browser bundle (no external dynamic imports)
- Upstream: https://github.com/mermaid-js/mermaid
- Distribution: https://cdn.jsdelivr.net/npm/mermaid@11.12.2/dist/mermaid.min.js
- License: MIT; copied from https://cdn.jsdelivr.net/npm/mermaid@11.12.2/LICENSE into `MERMAID-LICENSE.txt`
- API reference: https://mermaid.js.org/config/usage.html

The bundle is checked into the application folder for offline use. It requires no npm install or network connection at runtime. Its upstream version is pinned; upgrades must be verified with `tests/builders_smoke.py`, especially SVG sanitization, configuration directives, mixed Persian/English text, and WebEngine compatibility.
