# Zabbix tool

## Purpose

Let the model query a configured Zabbix instance as one automatic data source.

The current repository contains modules for:

```text
hosts
events
history
templates
triggers
```

The exact callable surface comes from the registered tool implementation.

## Usage

The model can choose Zabbix when it needs monitoring information. Users do not enable it per chat.

## Combination

A single task may combine:

```text
Project runbook
+ Zabbix active problems
+ Linux host state
+ Grafana metrics
→ diagnosis
```

## Configuration

Zabbix endpoint/authentication is local integration configuration and must not be placed into model-visible arguments when unnecessary.
