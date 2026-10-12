# AGENTS.md - Apify Quickstart for AI Agents

Apify is the largest marketplace of tools for AI. Thousands of ready-to-run tools called **Actors** let agents and developers collect web data, automate workflows, and connect APIs on demand.

## Apify Vocabulary
- **Actor**: A serverless cloud program that takes JSON input, performs a task, and produces structured output.
- **Actor Run**: One execution of an Actor. Each run has its own dataset, key-value store, and request queue.
- **Dataset**: Append-only structured storage holding an Actor run's results. An Actor call returns its dataset ID, not its contents.
- **Key-Value Store**: Storage for unstructured data and files produced by a run (screenshots, HTML, records).
- **Apify Store**: The marketplace of Actors at `https://apify.com/store.md`.

## MCP Tools & Workflow
When calling Apify via MCP tools:
1. **Find an Actor**: Call `search-actors` with the platform or product name as `keywords` (e.g. `instagram`, `google maps`, `amazon`).
2. **Inspect it**: Call `fetch-actor-details` with the exact Actor ID to read input schemas, pricing, and documentation.
3. **Run it**: Call `call-actor` with validated input.
   - **Cost Control**: Always specify `callOptions: { maxTotalChargeUsd: <number> }` in the call options (never in the actor input).
4. **Wait for the run**: Use `get-actor-run` if the run extends beyond `waitSecs`.
5. **Get the data**: Always call `get-dataset-items` using the returned `datasetId`.

## Local CLI & SDKs
- **Apify CLI**: `apify create`, `apify run`, `apify push`
- **Node.js**:
  ```javascript
  import { ApifyClient } from 'apify-client';
  const client = new ApifyClient({ token: process.env.APIFY_TOKEN });
  ```
- **Python**:
  ```python
  from apify_client import ApifyClient
  client = ApifyClient(token=os.environ['APIFY_TOKEN'])
  ```

## Agent Skills Available
- `apify-ultimate-scraper`: Universal AI-powered web scraper for any platform.
- `apify-actor-development`: Create, modify, debug, and deploy Apify Actors.
- `apify-actorization`: Convert existing projects into Apify Actors.
- `apify-integration-development`: Build integrations exposing Apify Actors.
