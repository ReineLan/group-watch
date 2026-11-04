// A drag that starts inside the dialog must never become a backdrop click.
export function backdropDismiss(element, close) {
  let press = null
  const outside = event => {
    if (event.target !== element()) return false
    const r = element().getBoundingClientRect()
    return event.clientX < r.left || event.clientX > r.right || event.clientY < r.top || event.clientY > r.bottom
  }
  return {
    down(event) { press = event.button === 0 && outside(event) ? event.pointerId : null },
    cancel() { press = null },
    click(event) {
      const accepted = press !== null && (event.pointerId === undefined || press === event.pointerId) && outside(event)
      press = null
      if (accepted) close()
    },
  }
}
