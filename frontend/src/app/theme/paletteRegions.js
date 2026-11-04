import {workspacePalette} from './workspacePalette.js'

export function syncPaletteRegions(host,regions,create=workspacePalette){
  if(!host)return []
  // Metric cards share one owner/arrival time. A teleported archive must shed
  // its previous owner when it becomes a descendant of maintenance-archive.
  const nodes=[...host.querySelectorAll('.sidebar,.topbar,.page>.error-banner,.page>.view>*,#toast')]
    .filter(node=>!node.closest('[hidden]')&&node.getClientRects().length)
  const wanted=new Set(nodes)
  for(const [node,region] of regions)if(!wanted.has(node)){
    region.dispose({release:true});regions.delete(node)
  }
  for(const node of nodes)if(!regions.has(node)){
    const colors=create(node)
    regions.set(node,{sync:colors.sync,dispose:colors.dispose,rect:()=>node.getBoundingClientRect()})
  }
  return [...regions.values()]
}
