// Preparation never holds input; the scene already has a thumbnail fallback.
export function latestSelection(current, prepare, commit) {
  return id => {
    if (id === current()) return
    try { Promise.resolve(prepare(id)).catch(() => {}) } catch { /* Keep the fallback. */ }
    return commit(id)
  }
}
