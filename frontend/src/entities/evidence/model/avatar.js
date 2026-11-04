import {computed, ref, watch} from 'vue'
import {localUrl} from '../../../shared/lib/format.js'

// A failed local image must not stay suppressed across later page activations.
export function useAvatar(profile, view) {
  const failed = ref(false)
  const source = computed(() => {
    const value = profile.value
    return /^\/avatars\/[a-f0-9]{64}\.webp$/.test(value.avatar_url || '')
      ? localUrl(value.avatar_url) + '?v=' + encodeURIComponent(value.avatar_at || '') : ''
  })
  watch([source, view, profile], () => { failed.value = false }, {flush: 'sync'})
  function fail(event) {
    // Ignore errors from an image replaced while profiles or pages were changing.
    if (event.target.getAttribute('src') === source.value) failed.value = true
  }
  return {source, failed, fail}
}
