import { StrictMode } from 'react'
import type { ReactNode } from 'react'
import { createRoot } from 'react-dom/client'
import { ClerkProvider, Show, SignIn, UserButton, useAuth, useUser } from '@clerk/react'
import App from './App'
import DocumentViewer from './DocumentViewer'
import type { GetToken } from './api'
import './styles.css'

const clerkKey = import.meta.env.VITE_CLERK_PUBLISHABLE_KEY

function viewerDocumentId() {
  return window.location.pathname.match(/^\/documents\/([a-fA-F0-9]{32})\/?$/)?.[1]
}

function RoutedApp({ getToken, profileImageUrl, accountControl }: { getToken?: GetToken; profileImageUrl?: string; accountControl?: ReactNode }) {
  const documentId = viewerDocumentId()
  if (documentId) return <DocumentViewer documentId={documentId} getToken={getToken} />
  if (window.location.pathname === '/groups') return <App getToken={getToken} view="groups" profileImageUrl={profileImageUrl} accountControl={accountControl} />
  if (window.location.pathname === '/agent-access') return <App getToken={getToken} view="agent-access" profileImageUrl={profileImageUrl} accountControl={accountControl} />
  return <App getToken={getToken} view="documents" profileImageUrl={profileImageUrl} accountControl={accountControl} />
}

function AuthenticatedApp() {
  const { getToken } = useAuth()
  const { user } = useUser()
  return <RoutedApp getToken={getToken} profileImageUrl={user?.imageUrl} accountControl={<UserButton />} />
}

function ClerkApp() {
  const documentId = viewerDocumentId()
  return (
    <ClerkProvider publishableKey={clerkKey}>
      <Show when="signed-out">
        {documentId ? <DocumentViewer documentId={documentId} signedOut /> : (
          <main className="auth-shell">
            <div className="auth-brand"><span>S/</span> ShareHTML</div>
            <section className="auth-panel">
              <div className="auth-label">SECURE CONSOLE</div>
              <h1>Sign in to your documents.</h1>
              <p>Your documents, shares, and agent keys are waiting.</p>
              <SignIn routing="hash" />
            </section>
            <div className="auth-grid" aria-hidden="true" />
          </main>
        )}
      </Show>
      <Show when="signed-in"><AuthenticatedApp /></Show>
    </ClerkProvider>
  )
}

createRoot(document.getElementById('root')!).render(
  <StrictMode>{clerkKey ? <ClerkApp /> : <RoutedApp />}</StrictMode>,
)
