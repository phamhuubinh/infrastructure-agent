const test = require("node:test");
const assert = require("node:assert/strict");

const {
  ORION_DOCKER_ORIGIN,
  getOrionDockerHost,
  getOrionDockerTarget,
} = require("../orion-docker");

test("Desktop proxies API calls through the packaged Docker reverse proxy", () => {
  assert.equal(ORION_DOCKER_ORIGIN, "http://127.0.0.1:80");
  assert.equal(
    getOrionDockerTarget("/api/rag/projects", "?limit=20"),
    "http://127.0.0.1/api/rag/projects?limit=20",
  );
  assert.equal(getOrionDockerHost(), "127.0.0.1");
});
