// Pure theme data and geometry; asset URLs live in assets.js so this stays importable under node --test.
export const storageKey='group-watch-theme'
export const themes=[
  {id:'chunxi',name:'春熙',effect:'sunlight',sparkleDurationScale:.65,effectLabel:'春光',tone:'light',meta:'#eef1dc',swatch:['#faf0f8','#a2b355','#a45db9'],line:'天上飞琼，寄人间春红'},
  {id:'feihua',name:'浮梦',effect:'petals',effectLabel:'飞花',tone:'light',meta:'#d6e6f1',swatch:['#98c4dd','#c46d88','#d8c5db'],line:'借你一梦，看尽浮世悲欢'},
  {id:'shuizhong',name:'澄漪',effect:'petals',effectLabel:'流光',tone:'dark',meta:'#1c1740',swatch:['#526c9e','#28204e','#a9a3d8'],line:'把琴唱幽兰，梦乡重，岁月便轻'},
  {id:'huadian',name:'晴庭',effect:'sunlight',effectLabel:'晴光',tone:'light',meta:'#b5e0d2',swatch:['#b5e0d2','#126c55','#fff1bf'],line:'天光漏过花窗，落了满庭晴绿'},
]
export function resolveTheme(id){return themes.find(theme=>theme.id===id)||themes[0]}

// Farthest-corner distance so a circular reveal from (x,y) always covers the viewport.
export function revealRadius(x,y,width,height){return Math.ceil(Math.hypot(Math.max(x,width-x),Math.max(y,height-y)))}

// Deterministic sunlight glints and bokeh, biased toward the light source in the top-left corner.
export function sparkleField(count,seed=11){
  let state=seed>>>0||1
  const next=()=>(state=(state*1664525+1013904223)>>>0)/4294967296
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
  let state=seed>>>0||1
  const next=()=>(state=(state*1664525+1013904223)>>>0)/4294967296
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
