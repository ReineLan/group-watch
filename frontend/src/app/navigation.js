export const pages = [
  {key:'overview', label:'工作总览', icon:'grid'},
  {key:'events', label:'待办线索', icon:'inbox'},
  {key:'bans', label:'禁言跟踪', icon:'clock'},
  {key:'risks', label:'黑名单与预警', icon:'shield'},
  {key:'records', label:'处罚档案', icon:'folder'},
  {key:'rules', label:'监控规则', icon:'sliders', settings:true},
  {key:'policies', label:'处理办法', icon:'book'},
  {key:'notifications', label:'通知', icon:'bell'},
  {key:'maintenance', label:'运行与恢复', icon:'database'},
]
export function resolvePage(hash) {
  const key=hash.replace(/^#/, '').split('/')[0]
  if(key==='query') return 'records'
  if(key==='archive') return 'maintenance'
  return pages.some(page=>page.key===key)?key:'overview'
}
export const evidencePages = ['records', 'bans', 'risks', 'policies']
export function greeting(hour) {
  if(hour>=5&&hour<11) return '早上好'
  if(hour>=11&&hour<13) return '中午好'
  if(hour>=13&&hour<18) return '下午好'
  if(hour>=18&&hour<23) return '晚上好'
  return '夜深了'
}
