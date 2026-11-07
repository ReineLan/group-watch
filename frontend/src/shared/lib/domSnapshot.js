export const readAsDataURL=blob=>new Promise((resolve,reject)=>{const reader=new FileReader();reader.onload=()=>resolve(reader.result);reader.onerror=()=>reject(reader.error||new Error('图片读取失败'));reader.readAsDataURL(blob)})
const escapeXml=text=>String(text).replace(/&/g,'&amp;').replace(/</g,'&lt;')

async function collectCss(){
 const parts=[]
 for(const sheet of document.styleSheets){
  let rules
  try{rules=[...sheet.cssRules]}catch{continue}
  for(const rule of rules){
   let text=rule.cssText
   if(rule.type===CSSRule.FONT_FACE_RULE){
    for(const match of [...text.matchAll(/url\((['"]?)([^'")]+)\1/g)]){
     try{
      const response=await fetch(new URL(match[2],sheet.href||location.href))
      if(response.ok)text=text.replace(match[0],`url("${await readAsDataURL(await response.blob())}")`)
     }catch{/* 字体不可用时回退系统字体 */}
    }
   }
   parts.push(text)
  }
 }
 return parts.join('\n')
}

function resolvedVariables(){
 const style=getComputedStyle(document.documentElement),vars=[]
 for(let i=0;i<style.length;i++){
  const name=style[i]
  if(name.startsWith('--'))vars.push(name+':'+style.getPropertyValue(name))
 }
 return vars.length?':root{'+vars.join(';')+'}':''
}

async function encode(canvas){
 const limit=4.5*1024*1024
 for(const quality of [.92,.82,.68]){
  const blob=await new Promise(resolve=>canvas.toBlob(resolve,'image/webp',quality))
  if(blob&&blob.size<=limit)return blob
  if(!blob)return new Promise(resolve=>canvas.toBlob(resolve,'image/png'))
 }
 return null
}

export async function snapshotElement(element,{expand='.qq-chat',scale=2,maxDimension=14000,prepare}={}){
 const clone=element.cloneNode(true)
 for(const node of clone.querySelectorAll(expand)){node.style.maxHeight='none';node.style.overflow='visible'}
 prepare?.(clone)
 Object.assign(clone.style,{position:'fixed',left:'-100000px',top:'0',margin:'0',width:element.getBoundingClientRect().width+'px'})
 document.body.appendChild(clone)
 try{
  const images=[...clone.querySelectorAll('img')]
  await Promise.all(images.map(async image=>{
   image.style.visibility=''
   const src=image.getAttribute('src')
   if(!src||src.startsWith('data:'))return
   try{
    const response=await fetch(src)
    if(!response.ok)throw new Error('图片请求失败')
    image.src=await readAsDataURL(await response.blob())
   }catch{image.remove()}
  }))
  await Promise.allSettled(images.map(image=>image.decode?image.decode():null))
  const width=clone.offsetWidth,height=clone.offsetHeight
  if(!width||!height)throw new Error('没有可截取的内容')
  const css=escapeXml(await collectCss()+resolvedVariables())
  const markup=new XMLSerializer().serializeToString(clone)
  const theme=document.documentElement.dataset.theme
  const svg=`<svg xmlns="http://www.w3.org/2000/svg"${theme?` data-theme="${theme}"`:''} width="${width}" height="${height}"><foreignObject width="100%" height="100%"><div xmlns="http://www.w3.org/1999/xhtml"><style>${css}</style>${markup}</div></foreignObject></svg>`
  const url=URL.createObjectURL(new Blob([svg],{type:'image/svg+xml;charset=utf-8'}))
  try{
   const image=await new Promise((resolve,reject)=>{const img=new Image();img.onload=()=>resolve(img);img.onerror=()=>reject(new Error('聊天截图渲染失败'));img.src=url})
   const canvas=document.createElement('canvas'),ctx=canvas.getContext('2d')
   let ratio=Math.min(scale,maxDimension/Math.max(width,height,1))
   for(let attempt=0;attempt<4;attempt++){
    canvas.width=Math.max(1,Math.round(width*ratio));canvas.height=Math.max(1,Math.round(height*ratio))
    ctx.drawImage(image,0,0,canvas.width,canvas.height)
    const blob=await encode(canvas)
    if(blob&&blob.size<=4.5*1024*1024)return blob
    ratio*=.7
   }
   throw new Error('聊天截图超出大小限制')
  }finally{URL.revokeObjectURL(url)}
 }finally{clone.remove()}
}
