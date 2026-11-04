// Keep offscreen chats out of the initial batch of profile/image requests.
export function whenNearViewport(element, load, Observer = globalThis.IntersectionObserver) {
  if (!Observer) { load(); return () => {} }
  let started = false
  const observer = new Observer(entries => {
    if (started || !entries.some(entry => entry.isIntersecting)) return
    started = true
    observer.disconnect()
    load()
  }, {rootMargin:'400px'})
  observer.observe(element)
  return () => { started = true; observer.disconnect() }
}
