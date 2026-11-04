// Keep the poster until the first presented frame. After that, the browser
// retains the last frame during buffering and loop seeks; do not uncover the
// unrelated still image on a transient `waiting` event.
export function playSceneVideo(video, ready, visible = () => !document.hidden) {
  let stopped = false, frame
  ready(false)
  const show = () => {
    if (stopped || !visible() || frame !== undefined) return
    if (video.requestVideoFrameCallback) {
      frame = video.requestVideoFrameCallback(() => {
        frame = undefined
        if (!stopped && visible()) ready(true)
      })
    } else if (video.readyState >= 2) ready(true)
  }
  const hide = () => {
    if (stopped) return
    if (frame !== undefined) video.cancelVideoFrameCallback?.(frame)
    frame = undefined
    ready(false)
  }
  video.addEventListener('playing', show)
  video.addEventListener('error', hide)
  Promise.resolve(video.play()).then(show).catch(hide)
  return () => {
    stopped = true
    if (frame !== undefined) video.cancelVideoFrameCallback?.(frame)
    video.removeEventListener('playing', show)
    video.removeEventListener('error', hide)
    video.pause()
  }
}
