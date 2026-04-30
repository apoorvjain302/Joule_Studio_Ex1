import React from 'react'
import ReactDOM from 'react-dom/client'
import { ThemeProvider } from '@ui5/webcomponents-react'
import App from './App.jsx'
import '@ui5/webcomponents-react/dist/Assets.js'
import '@ui5/webcomponents-fiori/dist/Assets.js'
import '@ui5/webcomponents-icons/dist/AllIcons.js'

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <ThemeProvider>
      <App />
    </ThemeProvider>
  </React.StrictMode>
)
