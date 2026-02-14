/**
 * React Entry Point
 *
 * Main entry point for the React application in the Electron renderer process.
 * Uses React 18's createRoot API for concurrent features support.
 */
import React from 'react'
import ReactDOM from 'react-dom/client'
import App from './App'
import './globals.css'

// Get the root element
const rootElement = document.getElementById('root')

if (!rootElement) {
  throw new Error(
    'Failed to find the root element. Make sure there is a <div id="root"></div> in index.html'
  )
}

// Create the React root and render the app
const root = ReactDOM.createRoot(rootElement)

root.render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
)

// Handle any unhandled promise rejections
window.addEventListener('unhandledrejection', (event) => {
  // In production, you might want to send this to an error tracking service
  if (process.env.NODE_ENV === 'development') {
    // eslint-disable-next-line no-console
    console.error('Unhandled promise rejection:', event.reason)
  }
})

// Handle any uncaught errors
window.addEventListener('error', (event) => {
  // In production, you might want to send this to an error tracking service
  if (process.env.NODE_ENV === 'development') {
    // eslint-disable-next-line no-console
    console.error('Uncaught error:', event.error)
  }
})
