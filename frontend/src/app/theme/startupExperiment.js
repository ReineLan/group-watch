// Keep the two startup comparisons independent of production theme behavior.
export function startupExperiment(search){
  const params=new URLSearchParams(search),mode=params.get('theme-debug')
  if(mode==='image-startup')return {mode,images:['feihua','mengxue'],prepareImages:params.get('image-preparation')==='decoded',videoEnabled:false}
  if(mode==='video-startup')return {mode,images:['feihua','shuizhong'],prepareImages:true,videoEnabled:params.get('video-enabled')!=='0'}
  return null
}
