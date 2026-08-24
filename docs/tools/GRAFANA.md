# Grafana tool

## Purpose

Let the model query configured Grafana information automatically when it needs dashboards, datasource data, alerts, annotations, or other capabilities exposed by the implementation.

The current repository includes Grafana modules for dashboards, datasources, alerts, and annotations.

## Usage

There is no Grafana mode or per-message toggle.

Example:

```text
User: "Does the current latency violate the requirement in this project?"

Model:
1. retrieves project requirement;
2. queries Grafana;
3. compares the results;
4. answers.
```

## Configuration

Grafana endpoint/authentication remains integration configuration outside model context.

## Output

Preserve source identity, query/time range where relevant, normalized values, and explicit upstream errors.
