// Invert the reveal easing: a 40% radius is not 40% of its duration.
export function revealTimeForRadius(progress,duration=950){
  const target=Math.max(0,Math.min(1,progress))
  let lo=0,hi=1
  for(let i=0;i<40;i++){
    const t=(lo+hi)/2,y=3*(1-t)**2*t*.8+3*(1-t)*t*t+t**3
    if(y<target)lo=t;else hi=t
  }
  const t=(lo+hi)/2
  return duration*(3*(1-t)**2*t*.22+3*(1-t)*t*t*.2+t**3)
}
