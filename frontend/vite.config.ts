import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, '.', '')
  const clerkKey = process.env.VITE_CLERK_PUBLISHABLE_KEY || env.VITE_CLERK_PUBLISHABLE_KEY
  if (mode === 'production' && !clerkKey) {
    throw new Error('VITE_CLERK_PUBLISHABLE_KEY is required for production builds')
  }
  return {
    plugins: [react()],
    server: {
      allowedHosts: ['app.localtest.me'],
      proxy: {
        '/api': {
          target: 'http://127.0.0.1:5000',
          changeOrigin: true,
          headers: {
            Host: 'app.localtest.me:5000',
            ...(clerkKey ? {} : { 'X-Dev-User': 'dev@sharehtml.local' }),
          },
        },
      },
    },
  }
})
