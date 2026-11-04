export const norm = value => {const s=String(value||'').normalize('NFKC').replace(/\s+/g,'').toLowerCase();return /^\d+$/.test(s)?s.replace(/^0+(?=\d)/,''):s}
export const sameMember = (a,b) => a.member_id&&b.member_id?norm(a.member_id)===norm(b.member_id):false
export const punishmentKind = value => ({'警告':'warning','禁言':'mute','移出群聊':'remove'}[value]||'')
export function filterRecords(records, profiles, filters, view, groups=[]) {
  const {search,group,type,start,end,status,image}=filters,query=search.trim().toLowerCase()
  const result=records.filter(r=>{
    const profile=profiles[r.id]||{},nickname=norm(profile.member_id)===norm(r.member_id)?profile.nickname:''
    return (view!=='bans'||r.ban)&&(!query||[r.nickname,r.card,nickname,r.member_id,r.group_id,r.reason,r.notes,r.operator,r.penalty_text].some(v=>String(v||'').toLowerCase().includes(query))||r.member_id&&norm(r.member_id).includes(norm(query)))&&(!group||String(r.group_id)===String(group))&&(view==='bans'||!type||r.punishment===type)&&(!start||r.event_date>=start)&&(!end||r.event_date<=end)&&(view!=='bans'||!status||(status==='active'?['进行中','永久禁言'].includes(r.ban.status):r.ban.status===status))&&(!image||(image==='has'?r.images.length:!r.images.length))
  })
  if(view==='bans'){const rank={'进行中':0,'永久禁言':1,'未注明结束':2,'待核实':3,'未开始':4,'已结束':5};result.sort((a,b)=>rank[a.ban.status]-rank[b.ban.status]||(a.ban.end||'9999').localeCompare(b.ban.end||'9999'))}
  return result
}
export const blankFilters = () => ({search:'',group:'',type:'',start:'',end:'',status:'',image:''})
export const recordRemarks = (record={}) => String(record.notes??'').trim()
export function parsePeople(text){return text.split(/\r?\n/).map(x=>x.trim()).filter(Boolean).map(line=>{const [account,...name]=line.split(/[\s,，\t]+/);return {member_id:account,nickname:name.length?name.join(' '):null}})}
export function buildRecordPayload(form, uploads, initialDecision, batchText) {
  const fields=['id','member_id','group_id','nickname','card','event_date','reason','punishment','penalty_text','operator','notes','occurrence']
  const body=Object.fromEntries(fields.filter(key=>key in form).map(key=>[key,form[key]]));body.images=uploads.map(({preview,...item})=>item)
  body.group_id=Number(body.group_id)
  if(form.decision_detail!==initialDecision){body.penalty_text=form.decision_detail}delete body.decision_detail
  if(batchText===undefined)return body
  const people=parsePeople(batchText);if(!people.length)throw new Error('请填写批量成员名单');if(people.length>50)throw new Error('最多一次登记 50 人')
  return {records:people.map(person=>({...body,...person,id:''}))}
}
