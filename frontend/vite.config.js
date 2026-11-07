import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import { readFileSync, existsSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
export default defineConfig({
  plugins: [vue(), {
    name: 'scene-assets',
    resolveId(id) { if (id === 'virtual:scene-assets') return '\0scene-assets' },
    load(id) {
      if (id !== '\0scene-assets') return
      const names = ['chunxi', 'feihua', 'shuizhong', 'mengxue', 'huaiye', 'lianmeng']
      const videos = ['shuizhong', 'lianmeng']
      const local = new URL('./src/shared/ui/scene/', import.meta.url)
      const originals = names.flatMap(name => [name + '.avif', 'thumb-' + name + '.avif']).concat(videos.map(name => name + '.mp4'))
      const useLocal = process.env.GROUP_WATCH_PUBLIC_RESOURCES !== '1' && originals.every(name => existsSync(new URL(name, local)))
      const imports = [], rows = []
      for (const name of names) {
        const source = useLocal ? new URL(name + '.avif', local) : new URL('./src/shared/ui/scene-example/example-' + name + '.svg', import.meta.url)
        imports.push(`import ${name} from ${JSON.stringify(fileURLToPath(source))}`)
        if (useLocal) imports.push(`import thumb_${name} from ${JSON.stringify(fileURLToPath(new URL('thumb-' + name + '.avif', local)))}`)
        const video = useLocal && videos.includes(name)
        if (video) imports.push(`import video_${name} from ${JSON.stringify(fileURLToPath(new URL(name + '.mp4', local)))}`)
        rows.push(`${name}:{image:${name},thumb:${useLocal ? 'thumb_' + name : name}${video ? ',video:video_' + name : ''}}`)
      }
      return imports.join('\n') + '\nexport const sceneAssets={' + rows.join(',') + '}'
    }
  }, {
    name: 'third-party-notices',
    generateBundle() {
      this.emitFile({type: 'asset', fileName: 'THIRD_PARTY_NOTICES.md',
        source: readFileSync(new URL('../THIRD_PARTY_NOTICES.md', import.meta.url), 'utf8')})
    }
  }], base: '/ui/',
  build: {outDir: 'dist', emptyOutDir: true},
  server: {proxy: {'/api': 'http://127.0.0.1:8066', '/evidence': 'http://127.0.0.1:8066'}}
})
