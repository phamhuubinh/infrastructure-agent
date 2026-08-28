const PROJECT_LIST_INVALIDATED = "orion:project-list-invalidated";

/** Notify mounted Project list surfaces that canonical Project data has changed. */
export function invalidateProjectList() {
  window.dispatchEvent(new Event(PROJECT_LIST_INVALIDATED));
}

export function onProjectListInvalidated(listener: () => void) {
  window.addEventListener(PROJECT_LIST_INVALIDATED, listener);
  return () => window.removeEventListener(PROJECT_LIST_INVALIDATED, listener);
}
