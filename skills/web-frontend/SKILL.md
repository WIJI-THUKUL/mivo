---
name: web-frontend
description: Build responsive HTML/CSS/JS pages that work well on phones. Use for websites, landing pages, UI and small web apps.
triggers: html, css, website, landing, frontend
---
# Web frontend
- Start with semantic HTML5 and `<meta name="viewport" content="width=device-width, initial-scale=1">`.
- Mobile first: flexbox/grid, relative units (rem, %), `max-width: 100%` on images, tap targets >= 44px.
- CSS variables for colors/spacing; support dark mode with `prefers-color-scheme`.
- JS: vanilla by default, no build step needed; separate `index.html`, `style.css`, `script.js`.
- Accessibility: alt text, labels on inputs, sufficient contrast, keyboard focus visible.
- Test by serving: `python -m http.server 8000` and open http://localhost:8000.
