import { FormEvent, useEffect, useRef, useState } from 'react'
import { request } from './api'
import type { GetToken } from './api'

type ManagedDocument = { id: string | number; title: string }
type Action = 'rename' | 'delete' | null

function ActionIcon({ name }: { name: 'more' | 'rename' | 'trash' }) {
  const paths = {
    more: <><circle cx="5" cy="12" r="1" /><circle cx="12" cy="12" r="1" /><circle cx="19" cy="12" r="1" /></>,
    rename: <><path d="M4 20h4l11-11-4-4L4 16v4Z" /><path d="m13.5 6.5 4 4" /></>,
    trash: <path d="M4 7h16M9 7V4h6v3m3 0-1 14H7L6 7m4 4v6m4-6v6" />,
  }
  return <svg viewBox="0 0 24 24" aria-hidden="true">{paths[name]}</svg>
}

export default function DocumentActions({ document, getToken, canDelete, onRenamed, onDeleted, placement = 'card' }: { document: ManagedDocument; getToken?: GetToken; canDelete: boolean; onRenamed: (title: string) => void; onDeleted: () => void; placement?: 'card' | 'viewer' }) {
  const detailsRef = useRef<HTMLDetailsElement>(null)
  const dialogRef = useRef<HTMLDialogElement>(null)
  const [action, setAction] = useState<Action>(null)
  const [title, setTitle] = useState(document.title)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    if (action && dialogRef.current && !dialogRef.current.open) dialogRef.current.showModal()
  }, [action])

  function openAction(next: Exclude<Action, null>) {
    detailsRef.current?.removeAttribute('open')
    setTitle(document.title)
    setError('')
    setAction(next)
  }

  function closeDialog() {
    if (!busy) setAction(null)
  }

  async function rename(event: FormEvent) {
    event.preventDefault()
    const nextTitle = title.trim()
    if (!nextTitle) return
    setBusy(true)
    setError('')
    try {
      await request(`/api/v1/documents/${document.id}`, {
        method: 'PUT',
        body: JSON.stringify({ title: nextTitle }),
      }, getToken)
      onRenamed(nextTitle)
      setAction(null)
    } catch (caught) {
      setError((caught as Error).message)
    } finally {
      setBusy(false)
    }
  }

  async function deleteDocument() {
    setBusy(true)
    setError('')
    try {
      await request<void>(`/api/v1/documents/${document.id}`, { method: 'DELETE' }, getToken)
      onDeleted()
    } catch (caught) {
      setError((caught as Error).message)
      setBusy(false)
    }
  }

  return (
    <>
      <details className={`document-actions ${placement}`} ref={detailsRef}>
        <summary aria-label={`More actions for ${document.title}`} title="More actions"><ActionIcon name="more" /></summary>
        <div className="document-actions-menu">
          <button type="button" onClick={() => openAction('rename')}><ActionIcon name="rename" /> Rename</button>
          {canDelete && <button className="destructive" type="button" onClick={() => openAction('delete')}><ActionIcon name="trash" /> Delete</button>}
        </div>
      </details>
      {action && (
        <dialog className="document-action-dialog" ref={dialogRef} aria-labelledby="document-action-title" onCancel={(event) => { event.preventDefault(); closeDialog() }} onClick={(event) => event.target === event.currentTarget && closeDialog()}>
          {action === 'rename' ? (
            <form className="document-action-panel" onSubmit={rename}>
              <span className="eyebrow">DOCUMENT SETTINGS</span>
              <h2 id="document-action-title">Rename document</h2>
              <label><span>Document title</span><input value={title} onChange={(event) => setTitle(event.target.value)} maxLength={200} autoFocus disabled={busy} /></label>
              {error && <p className="document-action-error" role="alert">{error}</p>}
              <footer><button className="secondary" type="button" onClick={closeDialog} disabled={busy}>Cancel</button><button className="viewer-button primary-action" disabled={busy || !title.trim()}>{busy ? 'Saving…' : 'Save title'}</button></footer>
            </form>
          ) : (
            <div className="document-action-panel destructive-panel">
              <span className="eyebrow">DESTRUCTIVE ACTION</span>
              <h2 id="document-action-title">Delete {document.title}?</h2>
              <p>The document, its content, and all sharing access will be permanently removed.</p>
              {error && <p className="document-action-error" role="alert">{error}</p>}
              <footer><button className="secondary" onClick={closeDialog} disabled={busy}>Cancel</button><button className="danger-button" onClick={deleteDocument} disabled={busy}>{busy ? 'Deleting…' : 'Delete document'}</button></footer>
            </div>
          )}
        </dialog>
      )}
    </>
  )
}
