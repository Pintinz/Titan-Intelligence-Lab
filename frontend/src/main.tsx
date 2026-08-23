import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import App from './App.tsx'
import { nativeSessionReady } from '@/lib/supabase'

// On native, the Supabase session lives in Keychain/Keystore behind an async read (see
// supabase.ts) — must resolve before React mounts, or the app's very first render could see "no
// session" and flash a signed-out state even though a real session exists. Resolves immediately
// on web (a no-op there), so this adds no real startup delay outside a native build.
nativeSessionReady.then(() => {
  createRoot(document.getElementById('root')!).render(
    <StrictMode>
      <App />
    </StrictMode>,
  )
})
