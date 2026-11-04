import {inject,ref,onScopeDispose} from 'vue'
import {createApi} from './client.js'
export const sessionKey=Symbol('session')
export const useSession=()=>inject(sessionKey)
export function createSession(token,fetcher){
 const api=createApi(token,fetcher),toast=ref('');let timer
 function notify(message){toast.value=message;clearTimeout(timer);timer=setTimeout(()=>toast.value='',4500)}
 onScopeDispose(()=>clearTimeout(timer))
 return {api,toast,notify}
}
