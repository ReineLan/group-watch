const usable=value=>typeof value==='string'&&value.length>0&&value!=='__CSRF__'

// Static preview HTML bypasses the backend's token substitution. Read the
// same-origin server-rendered entry before mounting any API consumers.
export async function resolveCsrfToken(current,{fetcher=fetch,parse=html=>new DOMParser().parseFromString(html,'text/html').querySelector('meta[name="csrf-token"]')?.content}={}){
  if(usable(current))return current
  for(const path of ['/work/','/']){
    try{
      const response=await fetcher(path,{credentials:'same-origin',cache:'no-store',signal:AbortSignal.timeout(10000)})
      if(!response.ok)continue
      const value=parse(await response.text())
      if(usable(value))return value
    }catch{}
  }
  throw new Error('无法初始化页面请求令牌，请刷新页面或打开正式工作台。')
}
