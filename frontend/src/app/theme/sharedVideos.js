import {playSceneVideo} from '../ui/background/playback.js'

// One video element and playback per URL, shared by overlapping Vue scenes.
export function sharedVideos({createVideo=()=>document.createElement('video'),play=playSceneVideo}={}){
  const entries=new Map()
  let visible=true
  function sync(entry){
    if(entry.refs&&visible){if(!entry.stop)entry.stop=play(entry.video,()=>{},()=>visible)}
    else if(entry.stop){entry.stop();entry.stop=null}
  }
  return {
    acquire(url){
      let entry=entries.get(url)
      if(!entry){
        const video=createVideo();video.muted=true;video.loop=true;video.playsInline=true;video.preload='auto';video.src=url
        entry={video,refs:0,stop:null};entries.set(url,entry)
      }
      entry.refs++;sync(entry)
      let released=false
      return {video:entry.video,release(){if(released)return;released=true;entry.refs--;sync(entry)}}
    },
    setVisible(value){visible=value;entries.forEach(sync)},
  }
}
