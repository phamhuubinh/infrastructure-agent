# Running Orion locally

Install and start the complete local web application:

```bash
./install.sh
orion
```

Orion opens in your default browser when it is healthy. `orion web` has the same behavior.
The only other public commands are:

```bash
orion log
orion help
```

## Frontend development only

The production application does not need a frontend development server. Contributors working
on the UI may use:

```bash
cd ui
npm run dev
```

Stop Orion with Ctrl-C. Its local data survives normal restarts.
