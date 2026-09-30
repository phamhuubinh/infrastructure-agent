# Running Orion locally

Install and start the complete local web application:

```bash
./install.sh
orion
```

Orion opens in your default browser when it is healthy. `orion web` has the same behavior.
When the imported Python package is this repository's editable checkout, `orion web` builds
`ui/dist/client` and replaces the repository's `.orion-ui` before serving it. After UI source
changes, restart `orion web`; no manual build or copy into `.orion-ui` is needed. A failed
development build stops startup with an error instead of serving an old bundle.
Installed Orion continues to serve its packaged static UI without invoking npm at runtime.
The only other public commands are:

```bash
orion log
orion auth hash-password
orion help
```

For browser access from another device, see [Remote browser access](REMOTE_ACCESS.md).

## Optional Vite frontend development

The production application does not need a frontend development server. Contributors working
on the UI may use:

```bash
cd ui
npm run dev
```

Stop Orion with Ctrl-C. Its local data survives normal restarts.
