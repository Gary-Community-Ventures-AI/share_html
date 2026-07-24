import { FormEvent, useEffect, useRef, useState } from 'react'
import { ApiError, request } from './api'
import type { GetToken } from './api'
import Autocomplete from './components/Autocomplete'
import DocumentActions from './DocumentActions'

type ViewerDocument = {
  id: string
  title: string
  url: string
  relationship?: 'mine' | 'shared'
  can_manage?: boolean
  can_share?: boolean
}

type Group = { id: string; name: string; recipient_count: number; recipients?: string[] }
type Contact = { id: string; name: string; email: string }
type AccessRole = 'viewer' | 'sharer'
type Access = { group_ids: string[]; user_emails: string[]; roles: Record<string, AccessRole> }
type LinkAccess = { enabled: boolean; password_protected: boolean; password?: string | null }
type AccessResponse = { access: Access; groups: Group[]; contacts: Contact[]; link: LinkAccess; can_manage: boolean }
type ViewerMode = 'private' | 'public' | 'password' | 'sign-in' | 'unavailable'

function isValidEmail(value: string) {
  return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(value)
}

function ViewerIcon({ name }: { name: 'back' | 'share' | 'reload' | 'fullscreen' | 'external' | 'download' | 'close' | 'lock' | 'eye' | 'eye-off' | 'copy' }) {
  const paths = {
    back: <path d="m15 18-6-6 6-6M9 12h10" />,
    share: <path d="M12 3v12m-4-8 4-4 4 4M5 13v7h14v-7" />,
    reload: <path d="M20 6v5h-5M4 18v-5h5m9.5-4A7 7 0 0 0 6.8 6.8L4 11m16 2-2.8 4.2A7 7 0 0 1 5.5 15" />,
    fullscreen: <path d="M8 3H3v5m13-5h5v5M8 21H3v-5m13 5h5v-5" />,
    external: <path d="M14 4h6v6m0-6-9 9M19 14v6H4V5h6" />,
    download: <path d="M12 3v12m-5-5 5 5 5-5M5 20h14" />,
    close: <path d="m6 6 12 12M18 6 6 18" />,
    lock: <path d="M7 11V8a5 5 0 0 1 10 0v3M5 11h14v10H5z" />,
    eye: <><path d="M2.5 12s3.5-6 9.5-6 9.5 6 9.5 6-3.5 6-9.5 6-9.5-6-9.5-6Z" /><circle cx="12" cy="12" r="2.5" /></>,
    'eye-off': <><path d="M3 3l18 18M10.6 6.1A9.8 9.8 0 0 1 12 6c6 0 9.5 6 9.5 6a16 16 0 0 1-2.2 2.8M6.2 6.2C3.8 7.8 2.5 12 2.5 12s3.5 6 9.5 6c1.2 0 2.3-.2 3.3-.6" /></>,
    copy: <path d="M8 8h11v11H8zM5 16H4V5h11v1" />,
  }
  return <svg viewBox="0 0 24 24" aria-hidden="true">{paths[name]}</svg>
}

export function ShareDialog({ documentId, getToken, onClose }: { documentId: string; getToken?: GetToken; onClose: () => void }) {
  const dialogRef = useRef<HTMLDialogElement>(null)
  const accessLoadStarted = useRef(false)
  const savedAccessSnapshot = useRef<string | null>(null)
  const saveVersion = useRef(0)
  const [access, setAccess] = useState<Access>({ group_ids: [], user_emails: [], roles: {} })
  const [link, setLink] = useState<LinkAccess>({ enabled: false, password_protected: false })
  const [password, setPassword] = useState('')
  const [passwordVisible, setPasswordVisible] = useState(false)
  const [recipientQuery, setRecipientQuery] = useState('')
  const [groups, setGroups] = useState<Group[]>([])
  const [contacts, setContacts] = useState<Contact[]>([])
  const [canManage, setCanManage] = useState(false)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [closeRequested, setCloseRequested] = useState(false)
  const [message, setMessage] = useState('')
  const [error, setError] = useState('')

  useEffect(() => {
    if (dialogRef.current && !dialogRef.current.open) dialogRef.current.showModal()
    if (accessLoadStarted.current) return
    accessLoadStarted.current = true
    request<AccessResponse>(`/api/v1/documents/${documentId}/access`, undefined, getToken)
      .then((result) => {
        const loadedPassword = result.link.password || ''
        setAccess(result.access)
        setLink(result.link)
        setPassword(loadedPassword)
        setGroups(result.groups)
        setContacts(result.contacts)
        setCanManage(result.can_manage)
        savedAccessSnapshot.current = JSON.stringify({ access: result.access, enabled: result.link.enabled, password: loadedPassword })
      })
      .catch((caught: Error) => setError(caught.message))
      .finally(() => setLoading(false))
  }, [documentId, getToken])

  useEffect(() => {
    if (loading || savedAccessSnapshot.current === null) return
    const snapshot = JSON.stringify({ access, enabled: link.enabled, password })
    if (snapshot === savedAccessSnapshot.current) return
    const version = ++saveVersion.current
    setSaving(true)
    setError('')
    setMessage('')
    const timeout = window.setTimeout(async () => {
      const passwordEnabled = link.enabled && password.length > 0
      try {
        await request(`/api/v1/documents/${documentId}/access`, {
          method: 'PUT',
          body: JSON.stringify(canManage ? {
            ...access,
            link: {
              enabled: link.enabled,
              password_protected: passwordEnabled,
              ...(passwordEnabled ? { password } : {}),
            },
          } : access),
        }, getToken)
        savedAccessSnapshot.current = snapshot
        if (version === saveVersion.current) setLink((current) => ({ ...current, password_protected: passwordEnabled }))
      } catch (caught) {
        if (version === saveVersion.current) setError((caught as Error).message)
      } finally {
        if (version === saveVersion.current) setSaving(false)
      }
    }, 500)
    return () => window.clearTimeout(timeout)
  }, [access, canManage, documentId, getToken, link.enabled, loading, password])

  useEffect(() => {
    if (!closeRequested || saving) return
    const snapshot = JSON.stringify({ access, enabled: link.enabled, password })
    if (snapshot === savedAccessSnapshot.current) onClose()
  }, [access, closeRequested, link.enabled, onClose, password, saving])

  function closeDialog() {
    if (saving) setCloseRequested(true)
    else onClose()
  }

  function addRecipient(event: FormEvent) {
    event.preventDefault()
    addRecipientValue(recipientQuery)
  }

  function addRecipientValue(value: string) {
    const query = value.trim().toLowerCase()
    if (!query) return
    const group = groups.find((item) => item.name.toLowerCase() === query)
    if (group) {
      setAccess((current) => ({ ...current, group_ids: current.group_ids.includes(group.id) ? current.group_ids : [...current.group_ids, group.id], roles: { ...current.roles, [`group:${group.id}`]: current.roles[`group:${group.id}`] || 'sharer' } }))
    } else {
      const contact = contacts.find((item) => item.name.toLowerCase() === query || item.email.toLowerCase() === query)
      const email = contact?.email.toLowerCase() || query
      if (!isValidEmail(email)) {
        setError('Enter a valid email address.')
        return
      }
      setAccess((current) => ({ ...current, user_emails: current.user_emails.includes(email) ? current.user_emails : [...current.user_emails, email], roles: { ...current.roles, [`email:${email}`]: current.roles[`email:${email}`] || 'sharer' } }))
    }
    setRecipientQuery('')
    setError('')
    setMessage('')
  }

  function setRole(key: string, role: AccessRole) {
    setAccess((current) => ({ ...current, roles: { ...current.roles, [key]: role } }))
  }

  function removeGroup(groupId: string) {
    setAccess((current) => {
      const roles = { ...current.roles }
      delete roles[`group:${groupId}`]
      return { ...current, group_ids: current.group_ids.filter((value) => value !== groupId), roles }
    })
  }

  function removeEmail(email: string) {
    setAccess((current) => {
      const roles = { ...current.roles }
      delete roles[`email:${email}`]
      return { ...current, user_emails: current.user_emails.filter((value) => value !== email), roles }
    })
  }

  async function copyLink() {
    await navigator.clipboard.writeText(`${window.location.origin}/documents/${documentId}`)
    setMessage('Viewer link copied.')
  }

  async function copyShareMessage() {
    const url = `${window.location.origin}/documents/${documentId}`
    await navigator.clipboard.writeText(`link: ${url}${password ? `\npassword: ${password}` : ''}`)
    setMessage('Share message copied.')
  }

  const recipientOptions = [
    ...groups.map((group) => ({ value: group.name, label: group.name, description: 'Private email list' })),
    ...contacts.map((contact) => ({ value: contact.email, label: contact.name, description: contact.email })),
  ]
  const normalizedRecipientQuery = recipientQuery.trim().toLowerCase()
  const hasRecipientMatch = recipientOptions.some((option) => `${option.label} ${option.value} ${option.description}`.toLowerCase().includes(normalizedRecipientQuery))
  if (normalizedRecipientQuery && !hasRecipientMatch && isValidEmail(normalizedRecipientQuery)) {
    recipientOptions.push({ value: normalizedRecipientQuery, label: normalizedRecipientQuery, description: 'Direct email' })
  }

  return (
    <dialog className="share-dialog" ref={dialogRef} aria-labelledby="share-title" onCancel={(event) => { event.preventDefault(); closeDialog() }} onClick={(event) => event.target === event.currentTarget && closeDialog()}>
      <div className="share-panel">
        <header className="share-heading">
          <div><span>DOCUMENT ACCESS</span><h2 id="share-title">Share document</h2></div>
          <button className="viewer-icon-button" onClick={closeDialog} aria-label="Close share panel"><ViewerIcon name="close" /></button>
        </header>
        <p className="share-note">{canManage ? 'Choose whether each recipient can view or share.' : 'Add people with view or share access. Only the owner can change existing access.'}</p>
        {loading ? <div className="access-loading"><ViewerIcon name="reload" /> Loading access…</div> : (
          <div className="access-options">
            <section className="access-section">
              <h3>Groups and people</h3>
              <form className="recipient-complete-form" onSubmit={addRecipient}>
                <Autocomplete value={recipientQuery} onValueChange={setRecipientQuery} onOptionSelect={(option) => { addRecipientValue(option.value); window.setTimeout(() => setRecipientQuery(''), 0) }} options={recipientOptions} placeholder="Search groups, names, or emails" ariaLabel="Find a group or person" required showAddAction emptyText="No matching groups or people." portalContainer={dialogRef.current} />
                <button className="viewer-button" type="submit">Add</button>
              </form>
              <div className="choice-list recipient-choice-list">
                {groups.filter((group) => access.group_ids.includes(group.id)).map((group) => <div className="access-choice recipient-card" key={group.id}><div className="recipient-card-header"><span><strong>{group.name}</strong><small>Private email list</small></span><select value={access.roles[`group:${group.id}`] || 'sharer'} onChange={(event) => setRole(`group:${group.id}`, event.target.value as AccessRole)} aria-label={`Role for ${group.name}`}><option value="viewer">Can view</option><option value="sharer">Can share</option></select><button type="button" onClick={() => removeGroup(group.id)} aria-label={`Remove ${group.name}`}><ViewerIcon name="close" /></button></div><div className="group-member-list">{group.recipients?.map((email) => <span key={email}>{email}</span>)}{!group.recipients?.length && <span>No people in this group.</span>}</div></div>)}
                {access.user_emails.map((email) => <div className="access-choice recipient-card" key={email}><div className="recipient-card-header"><span><strong>{contacts.find((contact) => contact.email === email)?.name || email}</strong><small>{contacts.find((contact) => contact.email === email) ? email : 'Direct email'}</small></span><select value={access.roles[`email:${email}`] || 'sharer'} onChange={(event) => setRole(`email:${email}`, event.target.value as AccessRole)} aria-label={`Role for ${email}`}><option value="viewer">Can view</option><option value="sharer">Can share</option></select><button type="button" onClick={() => removeEmail(email)} aria-label={`Remove ${email}`}><ViewerIcon name="close" /></button></div></div>)}
                {access.group_ids.length === 0 && access.user_emails.length === 0 && <p className="access-empty">No groups or people selected.</p>}
              </div>
            </section>
            {canManage && <section className="link-access-section">
              <div className="access-choice link-choice">
                <label className="link-choice-toggle">
                  <input type="checkbox" checked={link.enabled} onChange={(event) => setLink((current) => ({ ...current, enabled: event.target.checked }))} />
                  <span><strong>Anyone with the link</strong><small>No account required</small></span>
                </label>
                {password && <button className="link-copy-button" type="button" onClick={copyShareMessage} disabled={!link.enabled || saving} aria-label="Copy link and password" title="Copy link and password"><ViewerIcon name="copy" /><span>Copy</span></button>}
              </div>
              {link.enabled && (
                <div className="password-options">
                  <label className="password-field">
                    <span>OPTIONAL PASSWORD · LEAVE EMPTY FOR NO PASSWORD</span>
                    <div className="password-input-wrap">
                      <input type={passwordVisible ? 'text' : 'password'} value={password} maxLength={128} autoComplete="new-password" onChange={(event) => { setPassword(event.target.value); setError('') }} placeholder="Optional password" />
                      <span className="password-input-actions">
                        <button type="button" onClick={() => setPasswordVisible((current) => !current)} aria-label={passwordVisible ? 'Hide password' : 'Reveal password'} title={passwordVisible ? 'Hide password' : 'Reveal password'} aria-pressed={passwordVisible}><ViewerIcon name={passwordVisible ? 'eye-off' : 'eye'} /></button>
                        <button type="button" onClick={() => { setPassword(''); setPasswordVisible(false); setError('') }} aria-label="Clear password" title="Clear password"><ViewerIcon name="close" /></button>
                      </span>
                    </div>
                  </label>
                </div>
              )}
            </section>}
          </div>
        )}
        {(message || error) && <div className={`share-message ${error ? 'error' : ''}`} role="status">{error || message}</div>}
        <footer className="share-actions">
          <button className="viewer-button quiet" onClick={copyLink}><ViewerIcon name="external" /> Copy link</button>
          <span className={`autosave-status ${saving ? 'saving' : ''}`}>{saving ? 'Saving…' : 'Auto-save on'}</span>
        </footer>
      </div>
    </dialog>
  )
}

export default function DocumentViewer({ documentId, getToken, signedOut = false }: { documentId: string; getToken?: GetToken; signedOut?: boolean }) {
  const viewerShellRef = useRef<HTMLElement>(null)
  const initialLoadStarted = useRef(false)
  const tokenKey = `sharehtml:public-access:${documentId}`
  const [document, setDocument] = useState<ViewerDocument | null>(null)
  const [mode, setMode] = useState<ViewerMode>('unavailable')
  const [publicToken, setPublicToken] = useState('')
  const [password, setPassword] = useState('')
  const [renderUrl, setRenderUrl] = useState('')
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [shareOpen, setShareOpen] = useState(false)

  async function requestPublicRender(token?: string) {
    return request<{ url: string }>(`/api/v1/public/documents/${documentId}/render`, {
      method: 'POST',
      body: JSON.stringify(token ? { access_token: token } : {}),
    })
  }

  function returnToPassword(message = '') {
    sessionStorage.removeItem(tokenKey)
    setPublicToken('')
    setRenderUrl('')
    setMode('password')
    setError(message)
  }

  async function loadInitial() {
    setLoading(true)
    setError('')
    try {
      const result = await request<{ document: ViewerDocument }>(`/api/v1/documents/${documentId}`, undefined, getToken)
      setDocument(result.document)
      setMode('private')
      try {
        const render = await request<{ url: string }>(`/api/v1/documents/${documentId}/render`, { method: 'POST' }, getToken)
        setRenderUrl(render.url)
      } catch (caught) {
        setRenderUrl('')
        setError((caught as Error).message)
      }
      return
    } catch {
      try {
        const result = await request<{ document: ViewerDocument; link: LinkAccess }>(`/api/v1/public/documents/${documentId}`)
        setDocument(result.document)
        if (result.link.password_protected) {
          const storedToken = sessionStorage.getItem(tokenKey) || ''
          if (!storedToken) {
            setMode('password')
            return
          }
          try {
            setPublicToken(storedToken)
            const render = await requestPublicRender(storedToken)
            setMode('public')
            setRenderUrl(render.url)
          } catch (caught) {
            if (caught instanceof ApiError && (caught.status === 401 || caught.status === 403)) returnToPassword('Session expired. Enter the password again.')
            else {
              setMode('public')
              setError((caught as Error).message)
            }
          }
        } else {
          setMode('public')
          try {
            const render = await requestPublicRender()
            setRenderUrl(render.url)
          } catch (caught) {
            setRenderUrl('')
            setError((caught as Error).message)
          }
        }
      } catch (caught) {
        setMode(signedOut ? 'sign-in' : 'unavailable')
        setError((caught as Error).message)
      }
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    if (initialLoadStarted.current) return
    initialLoadStarted.current = true
    loadInitial()
  }, [documentId, getToken])

  async function refreshRender() {
    if (mode === 'password' || mode === 'sign-in' || mode === 'unavailable') return
    setLoading(true)
    setError('')
    try {
      const result = mode === 'private'
        ? await request<{ url: string }>(`/api/v1/documents/${documentId}/render`, { method: 'POST' }, getToken)
        : await requestPublicRender(publicToken || undefined)
      setRenderUrl(result.url)
    } catch (caught) {
      if (mode === 'public' && publicToken && caught instanceof ApiError && (caught.status === 401 || caught.status === 403)) {
        returnToPassword('Session expired. Enter the password again.')
      } else {
        setRenderUrl('')
        setError((caught as Error).message)
      }
    } finally {
      setLoading(false)
    }
  }

  async function unlock(event: FormEvent) {
    event.preventDefault()
    if (!password) return
    setLoading(true)
    setError('')
    try {
      const unlocked = await request<{ access_token: string }>(`/api/v1/public/documents/${documentId}/unlock`, {
        method: 'POST',
        body: JSON.stringify({ password }),
      })
      sessionStorage.setItem(tokenKey, unlocked.access_token)
      setPublicToken(unlocked.access_token)
      const render = await requestPublicRender(unlocked.access_token)
      setMode('public')
      setPassword('')
      setRenderUrl(render.url)
    } catch (caught) {
      sessionStorage.removeItem(tokenKey)
      setError((caught as Error).message)
    } finally {
      setLoading(false)
    }
  }

  async function downloadDocument() {
    if (mode !== 'private' && mode !== 'public') return
    try {
      const result = mode === 'private'
        ? await request<{ url: string }>(`/api/v1/documents/${documentId}/render`, { method: 'POST' }, getToken)
        : await requestPublicRender(publicToken || undefined)
      const downloadUrl = new URL(result.url)
      downloadUrl.searchParams.set('download', '1')
      const link = window.document.createElement('a')
      link.href = downloadUrl.toString()
      link.click()
    } catch (caught) {
      if (mode === 'public' && publicToken && caught instanceof ApiError && (caught.status === 401 || caught.status === 403)) returnToPassword('Session expired. Enter the password again.')
      else setError((caught as Error).message)
    }
  }

  async function enterFullscreen() {
    try {
      await viewerShellRef.current?.requestFullscreen()
    } catch {
      setError('Fullscreen is unavailable.')
    }
  }

  const contentReady = mode === 'private' || mode === 'public'

  return (
    <main className="viewer-shell" ref={viewerShellRef}>
      <header className="viewer-toolbar">
        <a className="viewer-back" href="/"><ViewerIcon name="back" /><span>Back to documents</span></a>
        <div className="viewer-title"><span>TRUSTED VIEWER</span><strong>{document?.title || 'Loading document…'}</strong></div>
        <div className="viewer-controls">
          {mode === 'private' && document?.can_share && <button className="viewer-button" onClick={() => setShareOpen(true)} aria-label="Share document" title="Share"><ViewerIcon name="share" /><span>Share</span></button>}
          <button className="viewer-button" onClick={refreshRender} disabled={loading || !contentReady} aria-label="Reload document" title="Reload"><ViewerIcon name="reload" /><span>Reload</span></button>
          <button className="viewer-button" onClick={enterFullscreen} aria-label="Enter fullscreen" title="Fullscreen"><ViewerIcon name="fullscreen" /><span>Fullscreen</span></button>
          <button className="viewer-button download-action" onClick={downloadDocument} disabled={!contentReady} aria-label="Download document" title="Download"><ViewerIcon name="download" /><span>Download</span></button>
          {mode === 'private' && document?.can_manage && <DocumentActions placement="viewer" document={document} getToken={getToken} onRenamed={(title) => setDocument((current) => current ? { ...current, title } : current)} onDeleted={() => window.location.assign('/')} />}
        </div>
      </header>
      <div className="viewer-stage">
        {renderUrl && <iframe title={document?.title || 'Document viewer'} src={renderUrl} sandbox="allow-scripts allow-same-origin" />}
        {loading && <div className="viewer-state"><ViewerIcon name="reload" /><strong>Preparing secure render…</strong><span>Requesting a fresh ticket.</span></div>}
        {!loading && mode === 'password' && (
          <div className="viewer-state password-gate">
            <div className="gate-icon"><ViewerIcon name="lock" /></div>
            <span className="gate-label">PROTECTED LINK</span>
            <strong>{document?.title || 'Password required'}</strong>
            <p>Enter the document password to continue.</p>
            <form onSubmit={unlock}><input type="password" value={password} onChange={(event) => setPassword(event.target.value)} autoFocus autoComplete="current-password" placeholder="Document password" aria-label="Document password" /><button className="viewer-button primary-action">Unlock</button></form>
            {error && <div className="gate-error" role="alert">{error}</div>}
            <small>Passwords and access tokens stay out of the URL.</small>
          </div>
        )}
        {!loading && mode === 'sign-in' && <div className="viewer-state viewer-error"><span>!</span><strong>Sign in required.</strong><p>This document is not available by public link.</p><a className="viewer-button primary-action" href="/">Go to sign in</a></div>}
        {!loading && mode === 'unavailable' && <div className="viewer-state viewer-error"><span>!</span><strong>Document unavailable.</strong><p>{error || 'This document could not be opened.'}</p><button className="viewer-button" onClick={loadInitial}>Try again</button></div>}
        {!loading && contentReady && error && !renderUrl && <div className="viewer-state viewer-error"><span>!</span><strong>Render unavailable.</strong><p>{error}</p><button className="viewer-button" onClick={refreshRender}>Try again</button></div>}
      </div>
      {shareOpen && mode === 'private' && document?.can_share && <ShareDialog documentId={documentId} getToken={getToken} onClose={() => setShareOpen(false)} />}
    </main>
  )
}
