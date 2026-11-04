// Newly mounted CSS animations join a shared scene clock once. No DOM pairing
// or per-frame phase synchronization, and no changes to opacity transitions.
export function joinSceneClock(node,startTime){
  for(const animation of node.getAnimations({subtree:true})){
    if(animation.animationName)animation.startTime=startTime
  }
}
