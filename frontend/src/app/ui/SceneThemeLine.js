import {h} from 'vue'
import {resolveTheme} from '../theme/themes.js'

// This visual copy belongs to one persistent scene, not the latest selection.
export default {
  props:{themeId:{type:String,required:true}},
  setup:props=>()=>{
    const theme=resolveTheme(props.themeId)
    return h('p',{class:'entry-theme-line scene-theme-line-copy'},[h('b',theme.name),h('span',theme.line)])
  },
}
