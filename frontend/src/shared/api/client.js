export function createApi(token, fetcher = fetch) {
  return async (path, body, {method = 'POST', signal, evidence = false} = {}) => {
    const headers = {'Content-Type':'application/json', 'X-CSRF-Token':token}
    let response
    try {
      response = await fetcher((evidence ? '/evidence' : '') + path, {
        ...(body === undefined ? {} : {method, headers, body:JSON.stringify(body)}),
        signal: signal || AbortSignal.timeout(22000),
      })
    } catch(error) {
      if(signal?.aborted) throw error
      throw new Error('无法连接工作台，请检查本机服务后重试。')
    }
    let data
    try { data = await response.json() }
    catch { throw new Error(response.status === 403 ? '页面请求令牌已失效，请刷新页面。' : '服务响应异常，请稍后重试。') }
    if(response.status === 401) {
      if(typeof window!=='undefined') window.dispatchEvent(new Event('workspace-locked'))
      throw new Error('会话已过期，请重新输入密码')
    }
    if(response.status === 404 && (!data.error && (!data.detail || data.detail === 'Not Found'))) throw new Error('当前服务缺少此功能，请重启工作台后刷新页面。')
    if(!response.ok) throw new Error(typeof data.detail === 'string' ? data.detail : data.error || '请求失败，请稍后重试。')
    return data
  }
}
