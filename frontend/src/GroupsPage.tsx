import { FormEvent, useEffect, useRef, useState } from 'react'
import { request } from './api'
import type { GetToken } from './api'
import Autocomplete from './components/Autocomplete'

type Group = { id: string; name: string; recipient_count: number; created_at?: string }
type EmailRecipient = { id: string; email: string }
type Contact = { id: string; name: string; email: string; created_at?: string }
type ManagementView = 'groups' | 'contacts'

function GroupIcon({ name }: { name: 'plus' | 'users' | 'trash' | 'arrow' | 'contact' }) {
  const paths = {
    plus: <path d="M12 5v14M5 12h14" />,
    users: <><path d="M16 20v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2M9 10a4 4 0 1 0 0-8 4 4 0 0 0 0 8M22 20v-2a4 4 0 0 0-3-3.9M16 2.1a4 4 0 0 1 0 7.8" /></>,
    trash: <path d="M4 7h16M9 7V4h6v3m3 0-1 14H7L6 7m4 4v6m4-6v6" />,
    arrow: <path d="m9 18 6-6-6-6M5 12h10" />,
    contact: <><rect x="3" y="4" width="18" height="16" rx="1" /><circle cx="9" cy="10" r="2" /><path d="M5.5 17c.5-2 1.7-3 3.5-3s3 1 3.5 3M15 9h3M15 13h3" /></>,
  }
  return <svg viewBox="0 0 24 24" aria-hidden="true">{paths[name]}</svg>
}

function DeleteGroupDialog({ group, deleting, onCancel, onConfirm }: { group: Group; deleting: boolean; onCancel: () => void; onConfirm: () => void }) {
  const dialogRef = useRef<HTMLDialogElement>(null)

  useEffect(() => {
    if (dialogRef.current && !dialogRef.current.open) dialogRef.current.showModal()
  }, [])

  return (
    <dialog className="group-delete-dialog" ref={dialogRef} aria-labelledby="delete-group-title" onCancel={(event) => { event.preventDefault(); onCancel() }} onClick={(event) => event.target === event.currentTarget && onCancel()}>
      <div className="group-delete-panel">
        <span className="eyebrow">DESTRUCTIVE ACTION</span>
        <h2 id="delete-group-title">Delete {group.name}?</h2>
        <p>The group and its document access will be removed. Your contacts and documents will stay intact.</p>
        <footer><button className="secondary" onClick={onCancel} disabled={deleting}>Cancel</button><button className="danger-button" onClick={onConfirm} disabled={deleting}>{deleting ? 'Deleting…' : 'Delete group'}</button></footer>
      </div>
    </dialog>
  )
}

export default function GroupsPage({ getToken, onError, onNotice }: { getToken?: GetToken; onError: (message: string) => void; onNotice: (message: string) => void }) {
  const [groups, setGroups] = useState<Group[]>([])
  const [contacts, setContacts] = useState<Contact[]>([])
  const [selectedId, setSelectedId] = useState('')
  const [selectedGroup, setSelectedGroup] = useState<Group | null>(null)
  const [emails, setEmails] = useState<EmailRecipient[]>([])
  const [groupName, setGroupName] = useState('')
  const [email, setEmail] = useState('')
  const [contactName, setContactName] = useState('')
  const [contactEmail, setContactEmail] = useState('')
  const [loading, setLoading] = useState(true)
  const [contactsLoading, setContactsLoading] = useState(true)
  const [busy, setBusy] = useState('')
  const [contactBusy, setContactBusy] = useState('')
  const [activeView, setActiveView] = useState<ManagementView>('groups')
  const [deletingGroup, setDeletingGroup] = useState<Group | null>(null)

  useEffect(() => {
    let cancelled = false
    request<{ groups: Group[] }>('/api/v1/groups', undefined, getToken)
      .then((result) => {
        if (cancelled) return
        setGroups(result.groups)
        setSelectedId(result.groups[0]?.id || '')
      })
      .catch((caught: Error) => !cancelled && onError(caught.message))
      .finally(() => !cancelled && setLoading(false))
    return () => { cancelled = true }
  }, [getToken, onError])

  useEffect(() => {
    let cancelled = false
    request<{ contacts: Contact[] }>('/api/v1/contacts', undefined, getToken)
      .then((result) => !cancelled && setContacts(result.contacts))
      .catch((caught: Error) => !cancelled && onError(caught.message))
      .finally(() => !cancelled && setContactsLoading(false))
    return () => { cancelled = true }
  }, [getToken, onError])

  useEffect(() => {
    if (!selectedId) {
      setSelectedGroup(null)
      setEmails([])
      return
    }
    let cancelled = false
    setBusy('emails')
    request<{ group: Group; emails: EmailRecipient[] }>(`/api/v1/groups/${selectedId}`, undefined, getToken)
      .then((result) => {
        if (cancelled) return
        setSelectedGroup(result.group)
        setEmails(result.emails)
      })
      .catch((caught: Error) => !cancelled && onError(caught.message))
      .finally(() => !cancelled && setBusy(''))
    return () => { cancelled = true }
  }, [getToken, onError, selectedId])

  async function createGroup(event: FormEvent) {
    event.preventDefault()
    if (!groupName.trim()) return
    setBusy('create')
    onError('')
    try {
      const result = await request<{ group: Group }>('/api/v1/groups', { method: 'POST', body: JSON.stringify({ name: groupName.trim() }) }, getToken)
      const group = { ...result.group, recipient_count: result.group.recipient_count ?? 0 }
      setGroups((current) => [...current, group])
      setSelectedId(group.id)
      setGroupName('')
      onNotice('Group created.')
    } catch (caught) {
      onError((caught as Error).message)
    } finally {
      setBusy('')
    }
  }

  async function saveContact(event: FormEvent) {
    event.preventDefault()
    if (!contactName.trim() || !contactEmail.trim()) return
    setContactBusy('save')
    onError('')
    try {
      const result = await request<{ contact: Contact }>('/api/v1/contacts', { method: 'POST', body: JSON.stringify({ name: contactName.trim(), email: contactEmail.trim() }) }, getToken)
      setContacts((current) => [...current.filter((contact) => contact.id !== result.contact.id), result.contact].sort((a, b) => a.name.localeCompare(b.name) || a.email.localeCompare(b.email)))
      setContactName('')
      setContactEmail('')
      onNotice('Contact saved.')
    } catch (caught) {
      onError((caught as Error).message)
    } finally {
      setContactBusy('')
    }
  }

  async function removeContact(contact: Contact) {
    setContactBusy(`remove-${contact.id}`)
    onError('')
    try {
      await request<void>(`/api/v1/contacts/${contact.id}`, { method: 'DELETE' }, getToken)
      setContacts((current) => current.filter((item) => item.id !== contact.id))
      onNotice('Contact removed.')
    } catch (caught) {
      onError((caught as Error).message)
    } finally {
      setContactBusy('')
    }
  }

  async function addEmail(event: FormEvent) {
    event.preventDefault()
    if (!selectedId || !email.trim()) return
    setBusy('add-email')
    onError('')
    try {
      const result = await request<{ email: EmailRecipient }>(`/api/v1/groups/${selectedId}/emails`, { method: 'POST', body: JSON.stringify({ email: email.trim() }) }, getToken)
      const alreadyListed = emails.some((item) => item.id === result.email.id)
      setEmails((current) => [...current.filter((item) => item.id !== result.email.id), result.email])
      if (!alreadyListed) setGroups((current) => current.map((group) => group.id === selectedId ? { ...group, recipient_count: group.recipient_count + 1 } : group))
      setEmail('')
      onNotice('Email added.')
    } catch (caught) {
      onError((caught as Error).message)
    } finally {
      setBusy('')
    }
  }

  async function removeEmail(recipient: EmailRecipient) {
    if (!selectedId) return
    setBusy(`remove-${recipient.id}`)
    onError('')
    try {
      await request<void>(`/api/v1/groups/${selectedId}/emails/${recipient.id}`, { method: 'DELETE' }, getToken)
      setEmails((current) => current.filter((item) => item.id !== recipient.id))
      setGroups((current) => current.map((group) => group.id === selectedId ? { ...group, recipient_count: Math.max(0, group.recipient_count - 1) } : group))
      onNotice('Email removed.')
    } catch (caught) {
      onError((caught as Error).message)
    } finally {
      setBusy('')
    }
  }

  async function deleteGroup() {
    if (!deletingGroup) return
    setBusy('delete-group')
    onError('')
    try {
      await request<void>(`/api/v1/groups/${deletingGroup.id}`, { method: 'DELETE' }, getToken)
      const remaining = groups.filter((group) => group.id !== deletingGroup.id)
      setGroups(remaining)
      setSelectedGroup(null)
      setEmails([])
      setSelectedId(remaining[0]?.id || '')
      setDeletingGroup(null)
      onNotice('Group deleted.')
    } catch (caught) {
      onError((caught as Error).message)
    } finally {
      setBusy('')
    }
  }

  return (
    <div className="groups-page">
      <nav className="management-tabs" aria-label="Recipient management" role="tablist">
        <button id="groups-tab" className={activeView === 'groups' ? 'active' : ''} type="button" role="tab" aria-selected={activeView === 'groups'} aria-controls="groups-panel" onClick={() => setActiveView('groups')}>
          <GroupIcon name="users" />
          <span><strong>Groups</strong><small>Reusable recipient lists</small></span>
        </button>
        <button id="contacts-tab" className={activeView === 'contacts' ? 'active' : ''} type="button" role="tab" aria-selected={activeView === 'contacts'} aria-controls="contacts-panel" onClick={() => setActiveView('contacts')}>
          <GroupIcon name="contact" />
          <span><strong>Contacts</strong><small>Your address book</small></span>
        </button>
      </nav>
      {activeView === 'contacts' && <section className="contacts-panel" id="contacts-panel" role="tabpanel" aria-labelledby="contacts-tab">
        <header className="contacts-heading"><div><span className="eyebrow">ADDRESS BOOK</span><h2>Contacts</h2><p>Keep the people you share documents with close at hand.</p></div></header>
        <form className="contact-add-form" onSubmit={saveContact}>
          <label><span>Name</span><input value={contactName} onChange={(event) => setContactName(event.target.value)} placeholder="Ada Lovelace" maxLength={160} required /></label>
          <label><span>Email</span><input type="email" value={contactEmail} onChange={(event) => setContactEmail(event.target.value)} placeholder="ada@example.com" maxLength={320} required /></label>
          <button className="secondary" disabled={contactBusy === 'save'}><GroupIcon name="plus" /> Save contact</button>
        </form>
        <div className="contact-table">
          <div className="contact-table-head"><span>NAME</span><span>EMAIL</span><span>ACTION</span></div>
          {contacts.map((contact) => <div className="contact-row" key={contact.id}><div className="contact-name"><span>{contact.name.slice(0, 1).toUpperCase()}</span><strong>{contact.name}</strong></div><a href={`mailto:${contact.email}`}>{contact.email}</a><button onClick={() => removeContact(contact)} disabled={contactBusy === `remove-${contact.id}`} aria-label={`Remove ${contact.name}`}><GroupIcon name="trash" /></button></div>)}
          {contactsLoading && <div className="group-empty">Loading contacts…</div>}
          {!contactsLoading && contacts.length === 0 && <div className="group-empty"><GroupIcon name="contact" /> Add your first contact above.</div>}
        </div>
      </section>}
      {activeView === 'groups' && <div className="groups-layout" id="groups-panel" role="tabpanel" aria-labelledby="groups-tab">
        <aside className="group-index">
          <div className="group-panel-heading"><span>YOUR GROUPS</span></div>
          <form className="group-create-form" onSubmit={createGroup}><input value={groupName} onChange={(event) => setGroupName(event.target.value)} placeholder="New group" aria-label="New group name" /><button disabled={busy === 'create'} aria-label="Create group"><GroupIcon name="plus" /></button></form>
          <div className="group-list">
            {groups.map((group) => <button className={selectedId === group.id ? 'active' : ''} key={group.id} onClick={() => setSelectedId(group.id)}><span><strong>{group.name}</strong><small>Private email list</small></span><GroupIcon name="arrow" /></button>)}
            {!loading && groups.length === 0 && <p>No groups yet.<br />Create a private email list.</p>}
          </div>
        </aside>
        <section className="group-detail">
          {selectedGroup ? <>
            <header className="group-detail-heading"><div><span className="eyebrow">SELECTED GROUP</span><h2>{selectedGroup.name}</h2></div><details className="group-settings"><summary>Group settings</summary><div><button onClick={() => setDeletingGroup(selectedGroup)}><GroupIcon name="trash" /> Delete group…</button></div></details></header>
            <form className="recipient-add-form" onSubmit={addEmail}><div><label htmlFor="recipient-email">Add an email</label><span>Type a contact name or any valid address.</span></div><div><Autocomplete value={email} onValueChange={setEmail} options={contacts.map((contact) => ({ value: contact.email, label: contact.name, description: contact.email }))} placeholder="Name or email" ariaLabel="Group recipient email" required /><button className="secondary" disabled={busy === 'add-email'}><GroupIcon name="plus" /> Add email</button></div></form>
            <div className="recipient-table"><div className="recipient-table-head"><span>EMAIL</span><span>ACTION</span></div>
              {emails.map((recipient) => <div className="recipient-row" key={recipient.id}><div className="recipient-identity"><span>{recipient.email.slice(0, 1).toUpperCase()}</span><strong>{recipient.email}</strong></div><div><button onClick={() => removeEmail(recipient)} disabled={busy === `remove-${recipient.id}`} aria-label={`Remove ${recipient.email}`}><GroupIcon name="trash" /></button></div></div>)}
              {busy === 'emails' && <div className="group-empty">Loading emails…</div>}
              {busy !== 'emails' && emails.length === 0 && <div className="group-empty">No email recipients yet.</div>}
            </div>
          </> : <div className="group-empty detail-empty"><GroupIcon name="users" /><strong>Select a group.</strong><span>Email recipients appear here.</span></div>}
        </section>
      </div>}
      {deletingGroup && <DeleteGroupDialog group={deletingGroup} deleting={busy === 'delete-group'} onCancel={() => setDeletingGroup(null)} onConfirm={deleteGroup} />}
    </div>
  )
}
