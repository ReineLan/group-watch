import test from 'node:test'
import assert from 'node:assert/strict'
import {effectScope, nextTick, ref} from 'vue'
import {createApi} from '../src/shared/api/client.js'
import {blankFilters, buildRecordPayload, filterRecords, sameMember, recordRemarks} from '../src/entities/evidence/model/records.js'
import {csvText} from '../src/shared/lib/format.js'
import {useCases,caseDraft} from '../src/pages/events/model/cases.js'
import {useQuery} from '../src/pages/evidence/model/query.js'
import {backdropDismiss} from '../src/shared/lib/backdrop.js'
import {readFileSync} from 'node:fs'
import {compile} from '@vue/compiler-dom'
import * as Vue from 'vue'

test('file-picker cancel stays in the dialog while Escape closes it',()=>{
 const source=readFileSync(new URL('../src/shared/ui/ModalDialog.vue',import.meta.url),'utf8')
 const template=source.match(/<template>([\s\S]*?)<\/template>/)[1]
 const render=new Function('Vue',compile(template,{mode:'function'}).code)({...Vue,renderSlot:()=>[]})
 let closed=0,prevented=0
 const node=render({id:'fixture',label:'fixture',open:true,$slots:{},backdrop:{},emit:()=>closed++},[])
 const dialog={}
 node.props.onCancel({target:{},currentTarget:dialog,preventDefault:()=>prevented++})
 assert.equal(closed,0);assert.equal(prevented,0)
 node.props.onCancel({target:dialog,currentTarget:dialog,preventDefault:()=>prevented++})
 assert.equal(closed,1);assert.equal(prevented,1)
})

test('only a completed backdrop press dismisses a dialog, never a text-selection drag',()=>{
 const dialog={getBoundingClientRect:()=>({left:100,right:400,top:100,bottom:400})};let closed=0
 const handler=backdropDismiss(()=>dialog,()=>closed++)
 const outside={target:dialog,button:0,pointerId:1,clientX:10,clientY:10}
 handler.down({...outside,target:{},clientX:200,clientY:200});handler.click(outside);assert.equal(closed,0)
 handler.down(outside);handler.click({...outside,pointerId:2});assert.equal(closed,0)
 handler.down(outside);handler.cancel();handler.click(outside);assert.equal(closed,0)
 handler.down(outside);handler.click({...outside,clientX:200,clientY:200});assert.equal(closed,0)
 handler.down(outside);handler.click(outside);assert.equal(closed,1)
})

test('evidence writes keep the existing API method, CSRF and cookie path',async()=>{
  let sent
  const api=createApi('csrf',async(path,options)=>{sent={path,...options};return Response.json({ok:true})})
  await api('/api/records/id',{}, {method:'DELETE',evidence:true})
  assert.equal(sent.path,'/evidence/api/records/id')
  assert.equal(sent.method,'DELETE');assert.equal(sent.headers['X-CSRF-Token'],'csrf')
  await api('/api/status');assert.equal(sent.method,undefined);assert.equal(sent.body,undefined)
})
test('expired sessions and rejected writes remain actionable errors',async()=>{
  await assert.rejects(createApi('',async()=>Response.json({}, {status:401}))('/api/status'),/会话已过期/)
  await assert.rejects(createApi('',async()=>Response.json({error:'档案不存在'}, {status:404}))('/api/records'),/档案不存在/)
  await assert.rejects(createApi('',async()=>Response.json({detail:'Not Found'}, {status:404}))('/api/maintenance/backup',{}),/重启工作台/)
})
test('editing a record preserves its original penalty until the user changes the decision',()=>{
  const form={id:'a',decision_detail:'禁言3天',penalty_text:'禁言3天',duration:'3天'}
  const body=buildRecordPayload(form,[{url:'/uploads/a.png',preview:'data:private',name:'证据'}],'禁言3天')
  assert.equal(body.duration,undefined);assert.equal(body.images[0].preview,undefined)
  assert.equal(body.decision_detail,undefined);assert.equal(form.decision_detail,'禁言3天')
  const changed=buildRecordPayload({...form,decision_detail:'禁言7天'},[],'禁言3天')
  assert.equal(changed.penalty_text,'禁言7天');assert.equal(changed.duration,undefined)
})
test('batch entry shares event evidence but keeps each member distinct and enforces 50 limit',()=>{
  const payload=buildRecordPayload({id:'old',reason:'事件'},[], '', '10001 昵称一\n１０００２，昵称二')
  assert.deepEqual(payload.records.map(r=>[r.id,r.member_id,r.nickname]),[['','10001','昵称一'],['','１０００２','昵称二']])
  assert.throws(()=>buildRecordPayload({},[],'',''),/名单/)
  assert.throws(()=>buildRecordPayload({},[],'',Array(51).fill('10001').join('\n')),/50/)
})

test('one remarks field preserves distinct facts and a changed duration clears old explicit times',()=>{
 assert.equal(recordRemarks({notes:'历史导入：人工核对内容'}),'历史导入：人工核对内容')
 assert.equal(recordRemarks({reason:'原文细节',category:'分类',notes:'人工补充\n历史导入：昵称、群名和处理人未记载；处理日期由证据编号推定。'}),'人工补充\n历史导入：昵称、群名和处理人未记载；处理日期由证据编号推定。')
 assert.equal(recordRemarks({notes:'历史导入：人工核对内容'}),'历史导入：人工核对内容')
 assert.equal(recordRemarks({reason:'原文细节',notes:'原文细节'}),'原文细节')
 const result=buildRecordPayload({category:'分类',notes:'人工补充',reason:'旧事实',decision_detail:'七天',ban_start:'2026-01-01T12:00',ban_end:'2026-01-02T12:00'},[],'三天')
 assert.equal(result.reason,'旧事实');assert.equal(result.notes,'人工补充');assert.equal(result.penalty_text,'七天')
 assert.equal(result.ban_start,undefined);assert.equal(result.ban_end,undefined)
})
test('member history spans groups only for the same normalized QQ identifier',()=>{
  assert.ok(sameMember({group_id:1,member_id:'００１２３'},{group_id:1,member_id:'123'}))
  assert.ok(sameMember({group_id:1,member_id:'123'},{group_id:2,member_id:'123'}))
  assert.ok(!sameMember({group_id:1,member:'同名'},{group_id:2,member:'同名'}))
  assert.ok(!sameMember({group_id:1,member_id:'123',member:'同名'},{group_id:1,member:'同名'}))
})

test('query rows open exact records or normalized accounts and label only known account columns',async()=>{
 const {rowTarget,cellLabel}=await import('../src/pages/evidence/model/queryPresentation.js')
 const records=[{id:'r1',member_id:'123',member:'留档昵称'}],name=r=>r.member
 assert.equal(rowTarget(['member_id','n'],['００１２３',2],records).kind,'member')
 assert.equal(rowTarget(['record_id','member_id'],['r1','123'],records).kind,'record')
 assert.equal(rowTarget(['n'],[123],records),null)
 assert.equal(cellLabel(['member_id'],['123'],0,records,name),'留档昵称 (123)')
 assert.equal(cellLabel(['n'],[123],0,records,name),'123')
})
test('record search uses only account-matched snapshots and combines image/group filters',()=>{
  const records=[{id:'a',member_id:'123',group_id:1,member:'123',images:[],incident:'1'},{id:'b',member_id:'456',group_id:2,member:'456',images:[{}]}]
  const filters={...blankFilters(),search:'新昵称'}
  assert.equal(filterRecords(records,{a:{member_id:'999',nickname:'新昵称'}},filters,'records').length,0)
  assert.equal(filterRecords(records,{a:{member_id:'００１２３',nickname:'新昵称'}},filters,'records').length,1)
  assert.equal(filterRecords(records,{}, {...blankFilters(),group:'1',image:'missing'},'records')[0].id,'a')
})
test('case conversion carries source and only this member’s selected evidence into the draft',()=>{
  const draft=caseDraft({id:'case',rule:'flood',user_id:123,group_id:100000001,created:1,evidence:['m1','m2'],context:[{message_id:'m1',user_id:123,name:'成员',text:'目标证据',time:1},{message_id:'m2',user_id:456,text:'旁人上下文',time:1}]},{flood:['刷屏']})
  assert.equal(draft.source,undefined);assert.equal(draft.member_id,'123')
  assert.match(draft.reason,/目标证据/);assert.doesNotMatch(draft.notes,/旁人上下文/)
})
test('a superseded case request cannot overwrite newer filters',async()=>{
  const requests=[],scope=effectScope();let cases
  scope.run(()=>{cases=useCases((path,body,options)=>new Promise(resolve=>requests.push({path,resolve,signal:options.signal})),()=>true,()=>{})})
  const first=cases.load();cases.filters.group='100000001';await nextTick()
  assert.equal(requests[0].signal.aborted,true);assert.match(requests[1].path,/group=100000001/)
  requests[1].resolve([{id:'new'}]);await nextTick();requests[0].resolve([{id:'old'}]);await first
  assert.equal(cases.rows.value[0].id,'new');scope.stop()
})
test('query cancellation clears busy state and suppresses later results',async()=>{
  const scope=effectScope();let query
  scope.run(()=>{query=useQuery((path,body,{signal})=>new Promise((resolve,reject)=>signal.addEventListener('abort',()=>reject(new Error('aborted')))))})
  query.question.value='SELECT 1';const pending=query.submit();assert.ok(query.busy.value)
  query.cancel();await pending;assert.equal(query.busy.value,false);assert.equal(query.result.value,null);assert.match(query.status.value,/已停止/);scope.stop()
})
test('CSV retains Unicode and neutralizes spreadsheet formulas',()=>{
  assert.equal(csvText([['昵称','=1+1','a"b']]),'\ufeff"昵称","\'=1+1","a""b"')
})


test('avatar fallback retries on navigation and ignores errors for an old source',async()=>{
  const {useAvatar}=await import('../src/entities/evidence/model/avatar.js')
  const profile=ref({avatar_url:'/avatars/aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa.webp',avatar_at:'snapshot'}),view=ref('records'),scope=effectScope()
  let avatar;scope.run(()=>{avatar=useAvatar(profile,view)})
  assert.match(avatar.source.value,/^\/evidence\/avatars\/aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa.webp/)
  avatar.fail({target:{getAttribute:()=>avatar.source.value}});assert.equal(avatar.failed.value,true)
  view.value='query';view.value='records';assert.equal(avatar.failed.value,false)
  avatar.fail({target:{getAttribute:()=>avatar.source.value}})
  profile.value={...profile.value};assert.equal(avatar.failed.value,false)
  avatar.fail({target:{getAttribute:()=>'/evidence/avatars/old.png'}});assert.equal(avatar.failed.value,false)
  profile.value={avatar_url:'https://example.test/avatar.png'};assert.equal(avatar.source.value,'')
  scope.stop()
})

test('cached names match accounts, preserve human names and keep verified blank nicknames empty',async()=>{
 const {createEvidence}=await import('../src/entities/evidence/model/state.js')
 const scope=effectScope();let evidence
 scope.run(()=>{evidence=createEvidence(()=>{},()=>{})})
 const row={id:'r1',member_id:'12345',nickname:'12345'}
 evidence.profiles.value={r1:{member_id:'１２３４５',nickname:'留存昵称'}}
 assert.equal(evidence.displayName(row),'留存昵称')
 assert.equal(evidence.displayName({...row,nickname:'手工昵称'}),'留存昵称')
 evidence.profiles.value.r1={member_id:'12345',nickname:'',nickname_is_blank:true}
 assert.equal(evidence.displayName(row),'')
 evidence.profiles.value.r1.member_id='54321'
 assert.equal(evidence.displayName(row),'12345')
 scope.stop()
})


test('operation times use one Beijing minute format',async()=>{
 const {fmt}=await import('../src/shared/lib/format.js')
 assert.equal(fmt('2026-11-02T01:26:17+08:00'),'2026-11-02 01:26')
 assert.equal(fmt('2026-10-30 03:06:37'),'2026-10-30 03:06')
 assert.equal(fmt('2026-11-01T17:26:17Z'),'2026-11-02 01:26')
})
test('registration date respects manual then DS then today',async()=>{
 const {registrationDate}=await import('../src/entities/evidence/model/registrationDate.js')
 assert.equal(registrationDate('2026-10-01','2026-10-02','2026-11-02'),'2026-10-01')
 assert.equal(registrationDate('','2026-10-02','2026-11-02'),'2026-10-02')
 assert.equal(registrationDate('','','2026-11-02'),'2026-11-02')
})
