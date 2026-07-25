import { useEffect, useState, useCallback } from 'react'

const API = '/api/admin/equivalences'
const API_META = '/api/admin'

function parseChange(flagReason) {
  if (!flagReason) return null
  const m = flagReason.match(/^(\w+):\s*(.+?)\s*→\s*(.+)$/)
  if (m) {
    const field = m[1].toLowerCase()
    if (field === 'credits') return `Les crédits sont passés de ${m[2]} à ${m[3]}.`
    if (field === 'titre' || field === 'title') return `Le titre a changé : "${m[2]}" → "${m[3]}".`
    return `${m[1]} : ${m[2]} → ${m[3]}`
  }
  if (/description/i.test(flagReason)) return 'La description du cours a changé.'
  if (/titre|title/i.test(flagReason)) return 'Le titre du cours a changé.'
  return flagReason
}

// ── Pending queue ──────────────────────────────────────────────────────────────

function PendingQueue({ university, onChanged, onAlerts }) {
  const [rows, setRows] = useState([])
  const [loading, setLoading] = useState(true)
  const [acting, setActing] = useState(null)

  const fetchPending = useCallback(async () => {
    setLoading(true)
    try {
      const resp = await fetch(`${API}/pending`, { credentials: 'include' })
      if (resp.ok) setRows(await resp.json())
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { fetchPending() }, [fetchPending])

  useEffect(() => {
    onAlerts?.(rows.filter(r => r.flag_reason))
  }, [rows, onAlerts])

  async function act(id, action) {
    setActing(id)
    try {
      await fetch(`${API}/${id}/${action}`, {
        method: 'PATCH',
        credentials: 'include',
      })
      await fetchPending()
      onChanged()
    } finally {
      setActing(null)
    }
  }

  if (loading) return null
  if (rows.length === 0) return null

  const alerts = rows.filter(eq => eq.flag_reason)

  return (
    <div className="admin-pending-wrap">
      <div className="admin-pending-header">
        <span className="admin-pending-title">En attente de révision</span>
        <span className="admin-pending-count">{rows.length} paire{rows.length !== 1 ? 's' : ''}</span>
        {alerts.length > 0 && (
          <span className="admin-pending-alert-hint">{alerts.length} alerte{alerts.length !== 1 ? 's' : ''} cours modifié</span>
        )}
      </div>
      <div className="admin-table-wrap">
        <table className="admin-table">
          <thead>
            <tr>
              <th>Cours A</th>
              <th>Cours B</th>
              <th>Actions</th>
            </tr>
          </thead>
          <tbody>
            {rows.map(eq => {
              const isAlert = Boolean(eq.flag_reason)
              return (
                <tr key={eq.id} className={isAlert ? 'admin-row-alert' : 'admin-row-pending'}>
                  <td>
                    <code className="admin-sigle">{eq.sigle_a}</code>
                    {eq.universite_a && eq.universite_a !== university && (
                      <span className="admin-uni-label">{eq.universite_a}</span>
                    )}
                  </td>
                  <td>
                    <code className="admin-sigle">{eq.sigle_b}</code>
                    {eq.universite_b && eq.universite_b !== university && (
                      <span className="admin-uni-label">{eq.universite_b}</span>
                    )}
                  </td>
                  <td className="admin-pending-actions">
                    <button
                      className="admin-btn-approve"
                      disabled={acting === eq.id}
                      onClick={() => act(eq.id, 'approve')}
                    >
                      {isAlert ? '✓ Confirmer valide' : '✓ Approuver'}
                    </button>
                    <button
                      className="admin-btn-skip"
                      disabled={acting === eq.id}
                      onClick={() => act(eq.id, 'skip')}
                    >
                      → Passer
                    </button>
                    <button
                      className="admin-btn-reject"
                      disabled={acting === eq.id}
                      onClick={() => act(eq.id, 'reject')}
                    >
                      ✕ Révoquer
                    </button>
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
    </div>
  )
}

// ── Login screen ───────────────────────────────────────────────────────────────

function LoginScreen({ onLogin }) {
  const [user, setUser] = useState('')
  const [pass, setPass] = useState('')
  const [error, setError] = useState(null)
  const [loading, setLoading] = useState(false)

  async function handleSubmit(e) {
    e.preventDefault()
    if (!user || !pass) return
    setLoading(true)
    setError(null)
    try {
      const resp = await fetch(`${API_META}/login`, {
        method: 'POST',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ username: user, password: pass }),
      })
      if (resp.status === 401) {
        setError('Identifiants incorrects.')
      } else if (resp.status === 429) {
        setError('Trop de tentatives. Réessayez dans une minute.')
      } else if (!resp.ok) {
        setError(`Erreur serveur : ${resp.status}`)
      } else {
        const me = await resp.json()
        onLogin(me.university || null)
      }
    } catch {
      setError('Impossible de contacter le serveur.')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="admin-login-wrap">
      <form className="admin-login-card" onSubmit={handleSubmit}>
        <h2 className="admin-login-title">Administration</h2>
        <p className="admin-login-sub">Gestion des équivalences de cours</p>
        <label className="admin-field-label">Utilisateur</label>
        <input
          className="admin-input"
          type="text"
          autoComplete="username"
          value={user}
          onChange={e => setUser(e.target.value)}
          autoFocus
        />
        <label className="admin-field-label">Mot de passe</label>
        <input
          className="admin-input"
          type="password"
          autoComplete="current-password"
          value={pass}
          onChange={e => setPass(e.target.value)}
        />
        {error && <p className="admin-error">{error}</p>}
        <button className="admin-btn-primary" type="submit" disabled={loading}>
          {loading ? 'Connexion…' : 'Se connecter'}
        </button>
      </form>
    </div>
  )
}

// ── Create form ────────────────────────────────────────────────────────────────

function CreateForm({ onCreated }) {
  const [open, setOpen] = useState(false)
  const [sigleA, setSigleA] = useState('')
  const [sigleB, setSigleB] = useState('')
  const [evidence, setEvidence] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)

  async function handleSubmit(e) {
    e.preventDefault()
    if (!sigleA.trim() || !sigleB.trim() || !evidence.trim()) return
    setLoading(true)
    setError(null)
    try {
      const resp = await fetch(API, {
        method: 'POST',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          sigle_a: sigleA.trim().toUpperCase(),
          sigle_b: sigleB.trim().toUpperCase(),
          source: 'admin_created',
          evidence: evidence.trim(),
        }),
      })
      if (!resp.ok) {
        const body = await resp.json().catch(() => ({}))
        setError(body.detail || `Erreur ${resp.status}`)
      } else {
        setSigleA(''); setSigleB(''); setEvidence('')
        setOpen(false)
        onCreated()
      }
    } catch {
      setError('Erreur réseau.')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="admin-create-wrap">
      <button className="admin-btn-secondary" onClick={() => setOpen(o => !o)}>
        {open ? '▴ Annuler' : '+ Nouvelle équivalence'}
      </button>
      {open && (
        <form className="admin-create-form" onSubmit={handleSubmit}>
          <div className="admin-create-row">
            <div className="admin-create-field">
              <label className="admin-field-label">Sigle A</label>
              <input
                className="admin-input"
                placeholder="ex. IFT3275"
                value={sigleA}
                onChange={e => setSigleA(e.target.value)}
                autoFocus
              />
            </div>
            <div className="admin-create-field">
              <label className="admin-field-label">Sigle B</label>
              <input
                className="admin-input"
                placeholder="ex. INF4420A"
                value={sigleB}
                onChange={e => setSigleB(e.target.value)}
              />
            </div>
          </div>
          <div className="admin-create-field" style={{ marginTop: '0.5rem' }}>
            <label className="admin-field-label">Justification <span style={{ color: '#c00' }}>*</span></label>
            <input
              className="admin-input"
              placeholder="ex. Même syllabus, approuvé par comité pédagogique"
              value={evidence}
              onChange={e => setEvidence(e.target.value)}
              required
            />
          </div>
          {error && <p className="admin-error" style={{ marginTop: '0.5rem' }}>{error}</p>}
          <button
            className="admin-btn-primary"
            type="submit"
            disabled={loading || !evidence.trim()}
            style={{ marginTop: '0.75rem', width: 'auto', padding: '0.4rem 1.25rem' }}
          >
            {loading ? 'Création…' : 'Créer'}
          </button>
        </form>
      )}
    </div>
  )
}

// ── Filters bar ────────────────────────────────────────────────────────────────

function FiltersBar({ filters, onChange }) {
  return (
    <div className="admin-filters">
      <select
        className="admin-filter-select"
        value={filters.source}
        onChange={e => onChange({ ...filters, source: e.target.value })}
      >
        <option value="">Toutes sources</option>
        <option value="official_table">official_table</option>
        <option value="admin_created">admin_created</option>
        <option value="inferred">inferred</option>
        <option value="official">official (legacy)</option>
      </select>
      <select
        className="admin-filter-select"
        value={filters.status}
        onChange={e => onChange({ ...filters, status: e.target.value })}
      >
        <option value="">Tous statuts</option>
        <option value="active">active</option>
        <option value="pending">pending</option>
        <option value="needs_review">needs_review</option>
        <option value="revoked">revoked</option>
      </select>
      <input
        className="admin-filter-input"
        placeholder="Filtrer par sigle…"
        value={filters.sigle}
        onChange={e => onChange({ ...filters, sigle: e.target.value })}
      />
    </div>
  )
}

// ── Source / status badges ─────────────────────────────────────────────────────

const SOURCE_COLORS = {
  official_table: '#0057a8',
  admin_created:  '#127a4c',
  official:       '#0057a8',
  inferred:       '#6c3fb5',
  request:        '#c97300',
}

function Badge({ value, colorMap }) {
  return (
    <span
      className="admin-badge"
      style={{ background: (colorMap[value] || '#888') + '1a', color: colorMap[value] || '#888' }}
    >
      {value}
    </span>
  )
}

// ── Equivalences table ─────────────────────────────────────────────────────────

function EquivTable({ rows, onRefresh }) {
  const [acting, setActing] = useState(null)

  async function revoke(id) {
    setActing(id)
    try {
      await fetch(`${API}/${id}`, { method: 'DELETE', credentials: 'include' })
      onRefresh()
    } finally {
      setActing(null)
    }
  }

  async function restore(id) {
    setActing(id)
    try {
      await fetch(`${API}/${id}/restore`, { method: 'PATCH', credentials: 'include' })
      onRefresh()
    } finally {
      setActing(null)
    }
  }

  if (rows.length === 0) {
    return <p className="admin-empty">Aucune équivalence trouvée.</p>
  }

  return (
    <div className="admin-table-wrap">
      <table className="admin-table">
        <thead>
          <tr>
            <th>Cours A</th>
            <th>Cours B</th>
            <th>Source</th>
            <th>Statut</th>
            <th>Confiance</th>
            <th>Créé le</th>
            <th>Par</th>
            <th>Actions</th>
          </tr>
        </thead>
        <tbody>
          {rows.map(eq => (
            <tr key={eq.id} className={eq.status === 'revoked' ? 'admin-row-revoked' : ''}>
              <td><code className="admin-sigle">{eq.sigle_a}</code></td>
              <td><code className="admin-sigle">{eq.sigle_b}</code></td>
              <td><Badge value={eq.source} colorMap={SOURCE_COLORS} /></td>
              <td>
                <span className={`admin-status ${eq.status}`}>{eq.status}</span>
              </td>
              <td className="admin-num">
                {eq.confidence != null ? `${(eq.confidence * 100).toFixed(0)}%` : '—'}
              </td>
              <td className="admin-date">
                {eq.created_at ? eq.created_at.slice(0, 10) : '—'}
              </td>
              <td className="admin-by">{eq.created_by || '—'}</td>
              <td>
                {eq.status === 'active' ? (
                  <button
                    className="admin-btn-revoke"
                    disabled={acting === eq.id}
                    onClick={() => revoke(eq.id)}
                  >
                    Révoquer
                  </button>
                ) : (
                  <button
                    className="admin-btn-restore"
                    disabled={acting === eq.id}
                    onClick={() => restore(eq.id)}
                  >
                    Restaurer
                  </button>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

// ── Admin panel root ───────────────────────────────────────────────────────────

export default function AdminPanel({ onBack }) {
  const [loggedIn, setLoggedIn] = useState(false)
  const [university, setUniversity] = useState(null)
  const [sessionChecked, setSessionChecked] = useState(false)
  const [rows, setRows] = useState([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const [filters, setFilters] = useState({ source: '', status: 'active', sigle: '' })
  const [alerts, setAlerts] = useState([])
  const [showNotifs, setShowNotifs] = useState(false)

  // Restore session on mount — cookie is sent automatically
  useEffect(() => {
    fetch(`${API_META}/me`, { credentials: 'include' })
      .then(r => r.ok ? r.json() : null)
      .then(me => {
        if (me) {
          setLoggedIn(true)
          setUniversity(me.university || null)
        }
      })
      .catch(() => {})
      .finally(() => setSessionChecked(true))
  }, [])

  const fetchEquivs = useCallback(async (f) => {
    setLoading(true)
    setError(null)
    const params = new URLSearchParams({ limit: '200' })
    if (f.source) params.set('source', f.source)
    if (f.status) params.set('status', f.status)
    if (f.sigle.trim()) params.set('sigle', f.sigle.trim().toUpperCase())
    try {
      const resp = await fetch(`${API}?${params}`, { credentials: 'include' })
      if (resp.status === 401) {
        setLoggedIn(false)
        return
      }
      if (!resp.ok) { setError(`Erreur ${resp.status}`); return }
      setRows(await resp.json())
    } catch {
      setError('Erreur réseau.')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    if (loggedIn) fetchEquivs(filters)
  }, [loggedIn, filters, fetchEquivs])

  function handleLogin(uni) {
    setLoggedIn(true)
    setUniversity(uni || null)
  }

  async function handleLogout() {
    await fetch(`${API_META}/logout`, { method: 'POST', credentials: 'include' })
    setLoggedIn(false)
    setUniversity(null)
    setRows([])
  }

  if (!sessionChecked) return null

  if (!loggedIn) {
    return <LoginScreen onLogin={handleLogin} />
  }

  const active = rows.filter(r => r.status === 'active').length
  const revoked = rows.filter(r => r.status === 'revoked').length

  return (
    <div className="admin-panel">
      <div className="admin-topbar">
        <div className="admin-topbar-left">
          <button className="admin-back-btn" onClick={onBack} title="Retour au graphe">
            ‹ Retour
          </button>
          <h2 className="admin-title">Administration — Équivalences</h2>
          {university && (
            <span className="admin-university-badge">{university}</span>
          )}
          <span className="admin-stats">
            {active} actives · {revoked} révoquées
          </span>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          <div style={{ position: 'relative' }}>
            <button
              onClick={() => setShowNotifs(v => !v)}
              style={{
                position: 'relative', background: 'none', border: 'none',
                cursor: 'pointer', fontSize: 20, lineHeight: 1, padding: '4px 6px',
              }}
            >
              🔔
              {alerts.length > 0 && (
                <span style={{
                  position: 'absolute', top: 0, right: 0,
                  background: '#e53e3e', color: '#fff',
                  fontSize: 10, fontWeight: 700, lineHeight: 1,
                  minWidth: 16, height: 16, borderRadius: 8,
                  display: 'flex', alignItems: 'center', justifyContent: 'center',
                  padding: '0 3px',
                }}>
                  {alerts.length}
                </span>
              )}
            </button>

            {showNotifs && (
              <>
                <div
                  onClick={() => setShowNotifs(false)}
                  style={{ position: 'fixed', inset: 0, zIndex: 99 }}
                />
                <div style={{
                  position: 'absolute', top: 'calc(100% + 8px)', right: 0,
                  width: 320, background: '#fff',
                  border: '1px solid #e5e7eb', borderRadius: 10,
                  boxShadow: '0 8px 24px rgba(0,0,0,0.12)',
                  zIndex: 100, overflow: 'hidden',
                }}>
                  <div style={{
                    padding: '12px 16px', borderBottom: '1px solid #f0f0f0',
                    fontWeight: 700, fontSize: 13, color: '#111',
                  }}>
                    Notifications
                  </div>
                  {alerts.length === 0 ? (
                    <p style={{ padding: '16px', color: '#aaa', fontSize: 12, margin: 0 }}>
                      Aucune alerte.
                    </p>
                  ) : (
                    alerts.map(eq => (
                      <div key={eq.id} style={{
                        padding: '12px 16px', borderBottom: '1px solid #f0f0f0',
                        display: 'flex', gap: 10, alignItems: 'flex-start',
                      }}>
                        <div style={{
                          width: 8, height: 8, borderRadius: '50%',
                          background: '#e53e3e', flexShrink: 0, marginTop: 4,
                        }} />
                        <div>
                          <div style={{ fontSize: 12, fontWeight: 700, color: '#111', marginBottom: 3 }}>
                            Cours {eq.sigle_a} ({eq.universite_a}) mis à jour
                          </div>
                          <div style={{ fontSize: 11, color: '#444', marginBottom: 3 }}>
                            {parseChange(eq.flag_reason)}
                          </div>
                          <div style={{ fontSize: 10, color: '#999' }}>
                            Équivalence avec{' '}
                            <span style={{ fontWeight: 600 }}>{eq.sigle_b}</span>
                            {' '}({eq.universite_b}) · {eq.flagged_at?.slice(0, 10)}
                          </div>
                        </div>
                      </div>
                    ))
                  )}
                </div>
              </>
            )}
          </div>
          <button className="admin-logout-btn" onClick={handleLogout}>
            Déconnexion
          </button>
        </div>
      </div>

      <div className="admin-body">
        <PendingQueue
          university={university}
          onChanged={() => fetchEquivs(filters)}
          onAlerts={setAlerts}
        />

        <CreateForm
          onCreated={() => fetchEquivs(filters)}
        />

        <FiltersBar filters={filters} onChange={setFilters} />

        {loading && <p className="admin-loading">Chargement…</p>}
        {error && <p className="admin-error">{error}</p>}
        {!loading && !error && (
          <EquivTable
            rows={rows}
            onRefresh={() => fetchEquivs(filters)}
          />
        )}
      </div>
    </div>
  )
}
