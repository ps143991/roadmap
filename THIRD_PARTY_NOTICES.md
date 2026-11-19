# Third-party software

Thesis Roadmap includes the following local browser libraries. Their original
licenses are included with the files and remain applicable to those libraries.

| Library | Version | License file | Project |
| --- | --- | --- | --- |
| D3 | 7.9.0 | `vendor/D3-LICENSE` | https://d3js.org |
| KaTeX | 0.19.0 | `vendor/katex/LICENSE` | https://katex.org |
| Marked | 18.1.1 | `vendor/marked/LICENSE` | https://marked.js.org |
| DOMPurify | 3.4.17 | `vendor/dompurify/LICENSE` | https://github.com/cure53/DOMPurify |

`vendor/notes-libraries.json` records the source archives and integrity hashes for
the Notes preview libraries. Math fonts are included locally; the application
does not load its frontend libraries from a CDN.

Python, GTK, PyGObject, and WebKitGTK are runtime dependencies supplied by the
operating system, under their respective licenses. They are not bundled into
the installer archive.
