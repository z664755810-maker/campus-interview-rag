import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

// 开发服务器配置：把前端的 /api 请求代理到后端 8000 端口，
// 这样前端用同源地址调用、免去跨域麻烦，也更贴近真实部署（同域反代）。
export default defineConfig({
  plugins: [vue()],
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true
      }
    }
  }
})
