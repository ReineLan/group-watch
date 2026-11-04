import {createApp} from 'vue'
import './app/styles/themes.css'
import './entities/evidence/ui/evidence.css'
import './app/styles/workbench.css'
import './app/styles/unified.css'
import './app/styles/design.css'
import App from './app/App.vue'
import {resolveCsrfToken} from './shared/api/csrf.js'
async function start(){
  const meta=document.querySelector('meta[name="csrf-token"]')
  meta.content=await resolveCsrfToken(meta.content)
  createApp(App).mount('#app')
}
start().catch(error=>{document.getElementById('app').textContent=error.message})
