import { createRoot } from 'react-dom/client'
import App from './App'
import './styles.css'
import './responsive.css'
import './pet.css'
if ((window as any).__FISH_DESKTOP__) createRoot(document.getElementById('root')!).render(<App />)
else document.getElementById('root')!.textContent = '请从 macOS 应用程序打开大肥鱼。'
