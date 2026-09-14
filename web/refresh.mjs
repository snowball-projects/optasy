// One same-origin check at a time. Failures back off without discarding the UI.
export function createRefreshController({
  request,
  onData,
  onState,
  now = Date.now,
}) {
  let busy = false,
    lastCheck = 0,
    failures = 0,
    previous = null;
  const state = (value) => onState({ ...value, lastCheck, failures });
  return {
    due(hidden = false) {
      return (
        !hidden &&
        !busy &&
        now() - lastCheck >= Math.min(300000 * 2 ** failures, 3600000)
      );
    },
    async refresh(mode = "live") {
      if (busy) return false;
      busy = true;
      state({ phase: "loading" });
      try {
        const next = await request(mode);
        if (
          previous?.mode === next.mode &&
          Date.parse(next.generated_at) < Date.parse(previous.generated_at)
        )
          throw new Error(
            "An older shared collection was returned; the current view was kept.",
          );
        const changed = JSON.stringify(previous) !== JSON.stringify(next);
        if (changed) onData(next);
        previous = next;
        failures = 0;
        lastCheck = now();
        state({ phase: changed ? "updated" : "unchanged" });
        return true;
      } catch (error) {
        failures = Math.min(failures + 1, 4);
        lastCheck = now();
        state({
          phase: "error",
          error:
            error.name === "TimeoutError"
              ? "The request timed out."
              : error.message,
        });
        return false;
      } finally {
        busy = false;
      }
    },
  };
}

export function canApplyRefresh({ popoverOpen, searchOpen, focusedControl }) {
  return !popoverOpen && !searchOpen && !focusedControl;
}
