export const time = value => value ? new Intl.DateTimeFormat('zh-CN',{timeZone:'Asia/Shanghai',month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',second:'2-digit',hour12:false}).format(new Date(value*1000)) : '尚未收到'
export const count = value => Number(value || 0).toLocaleString('zh-CN')
export const localDate = () => new Date().toLocaleDateString('sv-SE',{timeZone:'Asia/Shanghai'})
export const fmt = value => {
  if(!value)return '未记载'
  const text=String(value)
  if(/(?:Z|[+-]\d{2}:?\d{2})$/.test(text)){
    const date=new Date(text)
    if(!Number.isNaN(date.valueOf()))return date.toLocaleString('sv-SE',{timeZone:'Asia/Shanghai',year:'numeric',month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',hour12:false})
  }
  return text.replace('T',' ').slice(0,16)
}
export const localUrl = url => typeof url === 'string' && url.startsWith('/') && !url.startsWith('/api/') && !url.startsWith('/evidence/') ? '/evidence'+url : url
export const states = {pending:'等待复核',violation:'DS 认为违规',unsure:'证据不足',clear:'未见违规'}
export function csvText(rows) {
  const cell = value => '"'+String(value??'').replace(/^(\s*[=+@\-]|[\t\r])/u,"'$&").replaceAll('"','""')+'"'
  return '\ufeff'+rows.map(row=>row.map(cell).join(',')).join('\r\n')
}
export function downloadCsv(rows, name) {
  const url=URL.createObjectURL(new Blob([csvText(rows)],{type:'text/csv;charset=utf-8'}))
  const anchor=document.createElement('a');anchor.href=url;anchor.download=name;anchor.click()
  setTimeout(()=>URL.revokeObjectURL(url),5000)
}
