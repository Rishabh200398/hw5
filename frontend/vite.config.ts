import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// The dashboard runs on http://localhost:5173 and calls the FastAPI backend at
// http://localhost:8000 directly (see src/api.ts; override with VITE_API_URL).
export default defineConfig({
  plugins: [react()],
  server: { port: 5173, strictPort: true },
})
