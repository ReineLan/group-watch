// Reuse the one live video's presented frames in visual layers. No extra
// <video>, decoder, range request or playback clock is created per circle.
export function mirrorVideo(video,canvas,{requestFrame=globalThis.requestAnimationFrame,cancelFrame=globalThis.cancelAnimationFrame,timings}={}) {
  let stopped=false,pending
  if(timings){timings.startedAt=performance.now();timings.drawCount=0;timings.drawTotalMs=0;timings.drawMaxMs=0;timings.firstFrameAfterInitMs=null;timings.firstDraws=[]}
  const videoFrames=typeof video.requestVideoFrameCallback==='function'
  const context=canvas.getContext('2d')
  function draw(){
    if(stopped)return
    const before=timings?performance.now():0
    let drawn=false
    if(video.readyState>=2&&video.videoWidth&&context){
      if(canvas.width!==video.videoWidth)canvas.width=video.videoWidth
      if(canvas.height!==video.videoHeight)canvas.height=video.videoHeight
      try{context.drawImage(video,0,0);canvas.classList.add('is-ready');drawn=true}catch{/* Keep the poster. */}
    }
    if(timings){
      const elapsed=performance.now()-before
      if(drawn){
        timings.drawCount++;timings.drawTotalMs+=elapsed;timings.drawMaxMs=Math.max(timings.drawMaxMs,elapsed)
        if(timings.firstFrameAfterInitMs==null)timings.firstFrameAfterInitMs=performance.now()-timings.startedAt
      }
      if(timings.firstDraws.length<4)timings.firstDraws.push({startedAt:before,durationMs:elapsed,drawn,readyState:video.readyState})
    }
    pending=videoFrames?video.requestVideoFrameCallback(draw):requestFrame(draw)
  }
  draw()
  return ()=>{stopped=true;if(videoFrames)video.cancelVideoFrameCallback(pending);else cancelFrame(pending)}
}
