import {norm} from '../../../entities/evidence/model/records.js'

const accountColumn=name=>/^(member_id|user_id|account|qq|成员账号|成员QQ|用户QQ|QQ号|账号)$/i.test(name)
const recordColumn=name=>/^(record_id|id|档案编号|记录编号)$/i.test(name)
const names={member:'成员',member_id:'QQ',user_id:'QQ',record_id:'档案编号',group_name:'群聊',group_id:'群号',n:'次数',count:'次数',first_date:'首次日期',last_date:'最近日期',reasons:'违规行为',groups:'涉及群聊',event_date:'处理日期',reason:'违规行为',punishment:'处理结果',operator:'处理人',resolution:'人工处理',state:'复核结果',created:'发现时间'}
export const columnLabel=name=>names[name]||name
export function rowTarget(columns,row,records){
 for(let i=0;i<columns.length;i++)if(recordColumn(columns[i])){const record=records.find(r=>r.id===String(row[i]??''));if(record)return {kind:'record',id:record.id,record}}
 for(let i=0;i<columns.length;i++)if(accountColumn(columns[i])&&row[i]){const record=records.find(r=>r.member_id&&norm(r.member_id)===norm(row[i]));if(record)return {kind:'member',id:record.id,record}}
 return null
}
export function cellLabel(columns,row,index,records,displayName){
 const value=row[index],name=columns[index]
 if(value===null)return '—'
 if(accountColumn(name)){
  const record=records.find(r=>r.member_id&&norm(r.member_id)===norm(value))
  if(record){const nickname=displayName(record);return norm(nickname)!==norm(value)?`${nickname} (${value})`:String(value)}
 }
 return String(value??'')
}
