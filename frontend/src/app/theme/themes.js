// Pure theme data and geometry; asset URLs live in assets.js so this stays importable under node --test.
export const storageKey='group-watch-theme'
export const themes=[
  {id:'chunxi',name:'春熙',effect:'sunlight',sparkleDurationScale:.65,effectLabel:'春光',tone:'light',meta:'#eef1dc',swatch:['#faf0f8','#a2b355','#a45db9'],line:'天上飞琼，寄人间春红'},
  {id:'feihua',name:'浮梦',effect:'petals',effectLabel:'飞花',tone:'light',meta:'#d6e6f1',swatch:['#98c4dd','#c46d88','#d8c5db'],line:'借你一梦，看尽浮世悲欢'},
  {id:'shuizhong',name:'澄漪',effect:'petals',effectLabel:'流光',tone:'dark',meta:'#1c1740',swatch:['#526c9e','#28204e','#a9a3d8'],line:'把琴唱幽兰，梦乡重，岁月便轻'},
  {id:'mengxue',name:'梦雪',effect:'snow',effectLabel:'飞雪',tone:'light',meta:'#e4e6f3',swatch:['#c9d9f0','#e07a9e','#b4a6dc'],line:'我自凌空踏沧浪，借梦一场'},
  {id:'huaiye',name:'徊夜',effect:'meteors',effectLabel:'流星',tone:'dark',meta:'#121a3e',swatch:['#3d5aa8','#121a3e','#f0a6d2'],line:'我却是一个，一个软弱的胆小鬼'},
  {id:'lianmeng',name:'莲梦',effect:'ripples',sunbeam:true,effectLabel:'涟漪',tone:'light',meta:'#d4ecf1',swatch:['#9fd8e6','#b23d8f','#f0b6dc'],line:'月落星沉，风息水静'},
]
export function resolveTheme(id){return themes.find(theme=>theme.id===id)||themes[0]}

// Farthest-corner distance so a circular reveal from (x,y) always covers the viewport.
export function revealRadius(x,y,width,height){return Math.ceil(Math.hypot(Math.max(x,width-x),Math.max(y,height-y)))}

function random(seed){
  let state=seed>>>0||1
  return ()=>(state=(state*1664525+1013904223)>>>0)/4294967296
}

// Deterministic sunlight glints and bokeh, biased toward the light source in the top-left corner.
export function sparkleField(count,seed=11){
  const next=random(seed)
  return Array.from({length:count},(_,index)=>{
    const bokeh=index%4===3,grain=next()
    return {
      id:index,
      kind:bokeh?'bokeh':'glint',
      left:+(next()**1.35*96+2).toFixed(2),
      top:+(next()**1.25*86+4).toFixed(2),
      size:+(bokeh?28+grain*46:12+grain*16).toFixed(1),
      duration:+(bokeh?13+next()*9:3.4+next()*3.4).toFixed(2),
      delay:-+(next()*13).toFixed(2),
      rise:Math.round(24+next()*80),
    }
  })
}

// Deterministic petal field: stable between renders and testable, varied enough to read as natural.
export function petalField(count,seed=7){
  const next=random(seed)
  return Array.from({length:count},(_,index)=>{
    const depth=next(),size=7+depth*15
    return {
      id:index,
      left:+(next()*112-6).toFixed(2),
      size:+size.toFixed(1),
      fall:+(26-depth*12+next()*6).toFixed(2),
      delay:-+(next()*28).toFixed(2),
      drift:Math.round((next()-.35)*260),
      sway:+(2.6+next()*3.4).toFixed(2),
      spin:Math.round(next()*360),
      opacity:+(.45+depth*.5).toFixed(2),
      blur:depth>.86?+((depth-.86)*14).toFixed(1):0,
      tint:index%3,
    }
  })
}

// Path midpoints (viewport %) and heading (degrees clockwise from 12 o'clock) of the comets that
// fall beside the 徊夜 figure, mirroring the painted streaks while keeping clear of her face.
export const cometPaths=[[58,28,114],[64,10,120],[74,46,126],[82,18,110]]
// Share of a comet cycle spent travelling; dust and the end flare are timed against it.
export const cometTravel=.17
const round=(value,digits=2)=>+value.toFixed(digits)
const toRad=degrees=>degrees*Math.PI/180

// Deterministic 徊夜 sky: comets slide along gentle arcs beside the figure, shed glitter and burst
// into a four-point flare; thin meteors cross the open sky toward the sun, stars twinkle and warm motes drift up from the sunrise.
export function meteorField(count,seed=13){
  const next=random(seed),full=count>=14
  const plan=[...Array(full?4:2).fill('comet'),...Array(full?2:1).fill('meteor'),...Array(full?5:2).fill('mote')]
  return Array.from({length:count},(_,index)=>{
    const kind=plan[index]||'star'
    if(kind==='comet'){
      const [left,top,heading]=cometPaths[index],radius=520+next()*240,sweep=30+next()*12,duration=10+next()*6,start=heading-sweep/2
      const delay=next()*duration,point=(angle,offset=0)=>({x:round((radius+offset)*Math.sin(toRad(angle)),1),y:round(-(radius+offset)*Math.cos(toRad(angle)),1)})
      const dust=Array.from({length:7},(_,step)=>{
        const share=(step+1)/8
        return {...point(start+sweep*share,(next()-.5)*22),size:round(2+next()*3.5,1),spark:step%3===1,delay:-round(delay-share*cometTravel*duration)}
      })
      return {id:index,kind,left,top,radius:Math.round(radius),...(({x,y})=>({ox:-x,oy:-y}))(point(heading)),from:round(start-80),to:round(start+sweep-80),tail:round(20+next()*10),duration:round(duration),delay:-round(delay),dust,flare:{...point(start+sweep),size:Math.round(64+next()*36),delay:-round(delay-cometTravel*.9*duration)}}
    }
    if(kind==='meteor')return {id:index,kind,left:round(52+next()*30),top:round(next()*24),size:round(140+next()*120,1),angle:round(16+next()*14),duration:round(9+next()*8),delay:-round(next()*16)}
    if(kind==='mote')return {id:index,kind,left:round(66+next()*30),top:round(62+next()*34),size:round(4+next()*6,1),drift:-Math.round(60+next()*110),rise:-Math.round(90+next()*150),duration:round(9+next()*7),delay:-round(next()*14)}
    const nebula=next()<.3
    return {id:index,kind,left:round(nebula?3+next()*18:58+next()*39),top:round(nebula?3+next()*26:3+next()*55),size:round(9+next()*13,1),duration:round(2.8+next()*3.8),delay:-round(next()*18)}
  })
}

// Deterministic lotus pond: even items are ripples on the water in the lower third,
// odd items are large drifting bokeh kept off the central third; drifting toward the central figure is damped.
export function rippleField(count,seed=17){
  const next=random(seed)
  return Array.from({length:count},(_,index)=>{
    const ripple=index%2===0,side=next()*64
    const left=ripple?6+side/64*88:side<32?side:side+36
    const values={top:ripple?62+next()*32:6+next()*70,size:ripple?180+next()*160:90+next()*90,duration:ripple?6+next()*4:15+next()*8,delay:next()*(ripple?10:28),sway:(next()-.5)*680,rise:150+next()*270}
    return {
      id:index,
      kind:ripple?'ripple':'bokeh',
      left:+left.toFixed(2),
      top:+values.top.toFixed(2),
      size:+values.size.toFixed(1),
      duration:+values.duration.toFixed(2),
      delay:-+values.delay.toFixed(2),
      drift:ripple?0:Math.round((left<50)===(values.sway<0)?values.sway:values.sway*.6),
      rise:ripple?0:Math.round(values.rise),
      tint:(index>>1)%3,
    }
  })
}
