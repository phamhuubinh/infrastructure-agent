# Linux tool

## Purpose

Expose the Linux capabilities implemented/configured by Orion to the model.

The current repository contains Linux capability modules covering areas such as:

```text
CPU
disk
memory
network
package
process
security
service
system
```

The exact callable contract is defined by the registered implementation.

## Automatic use

Linux capabilities are available automatically when the Linux tool is configured.

The user should be able to ask naturally:

```text
"Check memory and the top processes on this host."
```

The model chooses the relevant Linux operations.

## Targets and credentials

Target/SSH configuration is application configuration, not prompt text.

Credentials must stay outside model context.

## Results

Normalize command/tool results into structured data where possible and preserve error/target metadata useful to the model.
