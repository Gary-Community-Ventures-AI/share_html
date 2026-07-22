import { FormEvent, useEffect, useMemo, useState } from 'react'
import type { ReactNode } from 'react'
import { request } from './api'
import type { GetToken } from './api'
import GroupsPage from './GroupsPage'
import { ShareDialog } from './DocumentViewer'

type EntityId = string | number
type View = 'documents' | 'groups' | 'agent-access'
type User = { email?: string; name?: string }
type Document = { id: EntityId; title: string; relationship: 'mine' | 'shared'; can_share?: boolean; created_at?: string; updated_at?: string }
type ApiKey = { id: EntityId; name?: string; prefix?: string; created_at?: string }
type OpenedDocuments = Record<string, string>

const OPENED_DOCUMENTS_KEY = 'sharehtml-opened-documents'

function collection<T>(payload: unknown, key: string): T[] {
  if (Array.isArray(payload)) return payload as T[]
  if (payload && typeof payload === 'object') {
    const value = (payload as Record<string, unknown>)[key]
    if (Array.isArray(value)) return value as T[]
  }
  return []
}

function entity<T>(payload: unknown, key: string): T {
  if (payload && typeof payload === 'object' && key in payload) return (payload as Record<string, unknown>)[key] as T
  return payload as T
}

function formatDate(value?: string) {
  if (!value) return 'just now'
  const date = new Date(value)
  return Number.isNaN(date.valueOf()) ? value : new Intl.DateTimeFormat(undefined, { month: 'short', day: 'numeric', year: 'numeric' }).format(date)
}

function Icon({ name }: { name: 'plus' | 'arrow' | 'key' | 'trash' | 'copy' | 'refresh' | 'search' | 'close' | 'share' }) {
  const paths = {
    plus: <path d="M12 5v14M5 12h14" />,
    arrow: <path d="m9 18 6-6-6-6M5 12h10" />,
    key: <path d="M15.5 7.5a4 4 0 1 1-2.8 6.8L4 23v-4l2-2H9l2.2-2.2a4 4 0 0 1 4.3-7.3Z" />,
    trash: <path d="M4 7h16M9 7V4h6v3m3 0-1 14H7L6 7m4 4v6m4-6v6" />,
    copy: <path d="M8 8h11v11H8zM5 16H4V5h11v1" />,
    refresh: <path d="M20 6v5h-5M4 18v-5h5m9.5-4A7 7 0 0 0 6.8 6.8L4 11m16 2-2.8 4.2A7 7 0 0 1 5.5 15" />,
    search: <><circle cx="11" cy="11" r="6" /><path d="m16 16 4 4" /></>,
    close: <path d="m7 7 10 10M17 7 7 17" />,
    share: <path d="M12 3v12m-4-8 4-4 4 4M5 13v7h14v-7" />,
  }
  return <svg viewBox="0 0 24 24" aria-hidden="true">{paths[name]}</svg>
}

function DocumentCollection({ documents, loading, profileImageUrl, userName, openedDocuments, onOpen, onShare, search, onSearchChange }: { documents: Document[]; loading: boolean; profileImageUrl?: string; userName: string; openedDocuments: OpenedDocuments; onOpen: (document: Document) => void; onShare: (document: Document) => void; search: string; onSearchChange: (value: string) => void }) {
  return (
    <section className="document-collection">
      <div className="collection-heading">
        <div><h2>Documents</h2></div>
        <div className="document-search"><Icon name="search" /><input value={search} onChange={(event) => onSearchChange(event.target.value)} aria-label="Search documents" placeholder="Search · owner:me · after:YYYY-MM-DD" />{search && <button onClick={() => onSearchChange('')} aria-label="Clear search"><Icon name="close" /></button>}</div>
      </div>
      <div className="document-list">
        {documents.map((document) => {
          const openedAt = openedDocuments[String(document.id)]
          return (
          <div className="document-card" key={document.id}>
          <a className="document-row" href={`/documents/${document.id}`} target="_blank" rel="noopener noreferrer" onClick={() => onOpen(document)}>
            <div className="document-name">
              <span className="document-avatar">{profileImageUrl ? <img src={profileImageUrl} alt="" /> : userName.slice(0, 1).toUpperCase()}</span>
              <div><strong>{document.title}</strong><small>{document.relationship === 'mine' ? 'Owned by me' : 'Shared with me'}</small></div>
            </div>
            <time><span>{openedAt ? 'OPENED' : document.updated_at ? 'UPDATED' : 'CREATED'}</span>{formatDate(openedAt || document.updated_at || document.created_at)}</time>
            <span className="open-button">Open <Icon name="arrow" /></span>
          </a>
          {document.can_share && <button className="share-card-button" type="button" onClick={() => onShare(document)} aria-label={`Share ${document.title}`}><Icon name="share" /> Share</button>}
          </div>
          )
        })}
        {loading && <div className="empty-state loading-state"><Icon name="refresh" /><span>Indexing documents…</span></div>}
        {!loading && documents.length === 0 && <div className="empty-state"><span className="terminal-cursor">_</span><div><strong>{search.trim() ? 'No matching documents.' : 'No documents yet.'}</strong><span>{search.trim() ? 'Try a title or a different filter.' : 'Published and shared documents will appear here.'}</span></div></div>}
      </div>
    </section>
  )
}

function filterDocuments(documents: Document[], query: string) {
  const terms = query.trim().toLowerCase().split(/\s+/).filter(Boolean)
  return documents.filter((document) => terms.every((term) => {
    const separator = term.indexOf(':')
    if (separator === -1) return document.title.toLowerCase().includes(term)
    const filter = term.slice(0, separator)
    const value = term.slice(separator + 1)
    if (filter === 'owner') return value === 'me' ? document.relationship === 'mine' : value === 'shared' ? document.relationship === 'shared' : true
    if (filter === 'is') return value === 'owned' ? document.relationship === 'mine' : value === 'shared' ? document.relationship === 'shared' : true
    const documentDate = new Date(document.updated_at || document.created_at || 0).valueOf()
    const filterDate = new Date(value).valueOf()
    if (Number.isNaN(filterDate)) return true
    if (filter === 'after') return documentDate >= filterDate
    if (filter === 'before') return documentDate < filterDate
    return document.title.toLowerCase().includes(term)
  }))
}

export default function App({ getToken, view = 'documents', profileImageUrl, accountControl }: { getToken?: GetToken; view?: View; profileImageUrl?: string; accountControl?: ReactNode }) {
  const [user, setUser] = useState<User | null>(null)
  const [documents, setDocuments] = useState<Document[]>([])
  const [keys, setKeys] = useState<ApiKey[]>([])
  const [keyName, setKeyName] = useState('Agent key')
  const [newKey, setNewKey] = useState('')
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState('')
  const [notice, setNotice] = useState('')
  const [error, setError] = useState('')
  const [search, setSearch] = useState('')
  const [shareDocumentId, setShareDocumentId] = useState('')
  const [openedDocuments, setOpenedDocuments] = useState<OpenedDocuments>(() => {
    try { return JSON.parse(localStorage.getItem(OPENED_DOCUMENTS_KEY) || '{}') as OpenedDocuments }
    catch { return {} }
  })
  const visibleDocuments = useMemo(() => filterDocuments(documents, search).sort((a, b) => {
    const timestamp = (document: Document) => new Date(openedDocuments[String(document.id)] || document.updated_at || document.created_at || 0).valueOf()
    return timestamp(b) - timestamp(a)
  }), [documents, openedDocuments, search])

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    const routeRequest = view === 'documents'
      ? request<unknown>('/api/v1/documents', undefined, getToken)
      : view === 'agent-access'
        ? request<unknown>('/api/v1/api-keys', undefined, getToken)
        : Promise.resolve(null)
    Promise.all([request<unknown>('/api/v1/me', undefined, getToken), routeRequest])
      .then(([mePayload, routePayload]) => {
        if (cancelled) return
        setUser(entity<User>(mePayload, 'user'))
        if (view === 'documents') setDocuments(collection<Document>(routePayload, 'documents'))
        if (view === 'agent-access') setKeys(collection<ApiKey>(routePayload, 'api_keys'))
      })
      .catch((caught: Error) => !cancelled && setError(caught.message))
      .finally(() => !cancelled && setLoading(false))
    return () => { cancelled = true }
  }, [getToken, view])

  function clearMessages() {
    setError('')
    setNotice('')
  }

  function recordDocumentOpen(document: Document) {
    const next = { ...openedDocuments, [String(document.id)]: new Date().toISOString() }
    setOpenedDocuments(next)
    localStorage.setItem(OPENED_DOCUMENTS_KEY, JSON.stringify(next))
  }

  async function createKey(event: FormEvent) {
    event.preventDefault()
    if (!keyName.trim()) return
    clearMessages()
    setBusy('key')
    try {
      const payload = await request<unknown>('/api/v1/api-keys', { method: 'POST', body: JSON.stringify({ name: keyName.trim() }) }, getToken)
      const result = entity<ApiKey & { key?: string; token?: string }>(payload, 'api_key')
      const payloadRecord = payload as Record<string, unknown>
      setNewKey(result.key || result.token || String(payloadRecord.key || payloadRecord.token || ''))
      setKeys((current) => [result, ...current])
      setKeyName('')
    } catch (caught) {
      setError((caught as Error).message)
    } finally {
      setBusy('')
    }
  }

  async function revokeKey(key: ApiKey) {
    clearMessages()
    setBusy(`key-${key.id}`)
    try {
      await request<void>(`/api/v1/api-keys/${key.id}`, { method: 'DELETE' }, getToken)
      setKeys((current) => current.filter((item) => item.id !== key.id))
      setNotice('Key revoked.')
    } catch (caught) {
      setError((caught as Error).message)
    } finally {
      setBusy('')
    }
  }

  async function copyKey() {
    await navigator.clipboard.writeText(newKey)
    setNotice('Key copied.')
  }

  return (
    <main className="shell">
      <header className="topbar">
        <a className="brand" href="/" aria-label="ShareHTML home"><span className="brand-mark">S/</span><span>ShareHTML</span></a>
        <nav className="page-nav" aria-label="Primary navigation">
          <a className={view === 'documents' ? 'active' : ''} href="/">Documents</a>
          <a className={view === 'groups' ? 'active' : ''} href="/groups">Groups</a>
          <a className={view === 'agent-access' ? 'active' : ''} href="/agent-access">Agent access</a>
        </nav>
        <div className="topbar-spacer" />
        <div className="identity"><span>{user?.name || user?.email || (loading ? 'Connecting' : 'Developer')}</span>{accountControl || <span className="avatar">{profileImageUrl ? <img src={profileImageUrl} alt="" /> : (user?.name || user?.email || 'D').slice(0, 1).toUpperCase()}</span>}</div>
      </header>

      {(error || notice) && <div className={`flash ${error ? 'error' : ''}`} role="status"><span>{error || notice}</span><button onClick={clearMessages} aria-label="Dismiss">×</button></div>}

      {view === 'documents' && (
        <div className="dashboard-grid documents-only"><div className="documents-stage">
          <div className="collections-grid">
          <DocumentCollection documents={visibleDocuments} loading={loading} profileImageUrl={profileImageUrl} userName={user?.name || user?.email || 'Developer'} openedDocuments={openedDocuments} onOpen={recordDocumentOpen} onShare={(document) => setShareDocumentId(String(document.id))} search={search} onSearchChange={setSearch} />
        </div></div></div>
      )}

      {view === 'groups' && <GroupsPage getToken={getToken} onError={setError} onNotice={setNotice} />}

      {view === 'agent-access' && (
        <div className="agent-page">
          <header className="agent-intro"><div><span className="eyebrow">AGENT CONNECTIONS</span><h1>Agent access</h1><p>Create and revoke the API keys agents use to publish and manage your documents.</p></div><Icon name="key" /></header>
          <section className="keys-panel agent-keys">
            <div className="section-heading compact"><div><h2>API keys</h2></div></div>
            <p className="aside-copy">Create a separate user-global key for each connected agent.</p>
            <form className="key-form" onSubmit={createKey}><input aria-label="Agent key name" value={keyName} onChange={(event) => setKeyName(event.target.value)} placeholder="Agent name" /><button className="secondary" disabled={busy === 'key'}><Icon name="plus" /> Add key</button></form>
            {newKey && <div className="key-reveal"><div><span>NEW KEY · SHOWN ONCE</span><button onClick={() => setNewKey('')} aria-label="Hide key">×</button></div><code>{newKey}</code><button className="copy-button" onClick={copyKey}><Icon name="copy" /> Copy key</button></div>}
            <div className="key-list">
              {keys.map((key) => <div className="key-row" key={key.id}><div><strong>{key.name || 'API key'}</strong><code>{key.prefix ? `${key.prefix}••••••` : `key_${String(key.id).slice(0, 6)}•••`}</code></div><button onClick={() => revokeKey(key)} disabled={busy === `key-${key.id}`} aria-label={`Revoke ${key.name || 'key'}`}><Icon name="trash" /></button></div>)}
              {!loading && keys.length === 0 && <p className="empty-small">No agents connected.</p>}
            </div>
          </section>
        </div>
      )}
      {shareDocumentId && <ShareDialog documentId={shareDocumentId} getToken={getToken} onClose={() => setShareDocumentId('')} />}
    </main>
  )
}
