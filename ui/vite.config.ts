import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
// An open native WebView can still import chunks from its previous build after waking.
export default defineConfig({ plugins: [react()], build: { outDir: 'dist', emptyOutDir:false } })
