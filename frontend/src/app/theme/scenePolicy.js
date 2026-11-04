// Touch devices and compact windows use a still scene from the first render.
// Do not create a video and then pause it: some Android browsers take over
// playback as soon as its source is attached, despite playsinline.
export const compactSceneQuery='(max-width: 800px), (hover: none), (pointer: coarse)'
export const reducedSceneQuery='(prefers-reduced-motion: reduce)'
export function useStillScene(compact,reduced){return compact.matches||reduced.matches}
