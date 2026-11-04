// Give navigation its own paint before starting the next page's first data batch.
export function afterPaint(schedule=globalThis.requestAnimationFrame) {
  if(!schedule)return Promise.resolve()
  return new Promise(resolve=>schedule(()=>schedule(resolve)))
}
