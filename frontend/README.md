# Digital Lin Daiyu Frontend

Node/Vite frontend for the separated Web UI.

```bash
npm install
npm run dev
npm run build
```

The dev server proxies `/api`, `/health`, `/assets`, and `/favicon.ico` to
`VITE_API_PROXY_TARGET` or `http://127.0.0.1:8000`.
