const ORION_DOCKER_ORIGIN = "http://127.0.0.1:80";

function getOrionDockerTarget(pathname, search = "") {
  return new URL(`${pathname}${search}`, ORION_DOCKER_ORIGIN).toString();
}

function getOrionDockerHost() {
  return new URL(ORION_DOCKER_ORIGIN).host;
}

module.exports = {
  ORION_DOCKER_ORIGIN,
  getOrionDockerHost,
  getOrionDockerTarget,
};
