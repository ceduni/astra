import { useEffect, useState, useCallback } from 'react'

const API = '/api/admin/equivalences'

function authHeader(token) {
  return { Authorization: `Basic ${token}` }
}

// ── Pending queue ──────────────────────────────────────────────────────────────

function PendingQueue({ token, onChanged }) {
  const [rows, setRows] = useState([])
  const [loading, setLoading] = useState(true)
  const [acting, setActing] = useState(null)

  const fetchPending = useCallback(async () => {
    setLoading(true)
    try {
      const resp = await fetch(`${API}/pending`, { headers: authHeader(token) })
      if (resp.ok) setRows(await resp.json())
    } finally {
      setLoading(false)
    }
  }, [token])

  useEffect(() => { fetchPending() }, [fetchPending])

  async function act(id, action) {
    setActing(id)
    try {
      await fetch(`${API}/${id}/${action}`, {
        method: 'PATCH',
        headers: authHeader(token),
      })
      await fetchPending()
      onChanged()
    } finally {
      setActing(null)
    }
  }

  if (loading) return null
  if (rows.length === 0) return null

  return (
    <div className="admin-pending-wrap">
      <div className="admin-pending-header">
        <span className="admin-pending-title">En attente de révision</span>
        <span className="admin-pending-count">{rows.length} paire{rows.length !== 1 ? 's' : ''}</span>
        <span className="admin-pending-hint">Équivalences inférées entre {(70).toFixed(0)}% et {(78).toFixed(0)}% de confiance</span>
      </div>
      <div className="admin-table-wrap">
        <table className="admin-table">
          <thead>
            <tr>
              <th>Cours A</th>
              <th>Cours B</th>
              <th>Confiance</th>
              <th>Preuve</th>
              <th>Actions</th>
            </tr>
          </thead>
          <tbody>
            {rows.map(eq => (
              <tr key={eq.id} className="admin-row-pending">
                <td><code className="admin-sigle">{eq.sigle_a}</code></td>
                <td><code className="admin-sigle">{eq.sigle_b}</code></td>
                <td>
                  <span className="admin-conf-bar-wrap">
                    <span
                      className="admin-conf-bar"
                      style={{ width: `${Math.round((eq.confidence || 0) * 100)}%` }}
                    />
                    <span className="admin-conf-label">
                      {eq.confidence != null ? `${Math.round(eq.confidence * 100)}%` : '—'}
                    </span>
                  </span>
                </td>
                <td className="admin-evidence">{eq.evidence || '—'}</td>
                <td className="admin-pending-actions">
                  <button
                    className="admin-btn-approve"
                    disabled={acting === eq.id}
                    onClick={() => act(eq.id, 'approve')}
                  >
                    ✓ Approuver
                  </button>
                  <button
                    className="admin-btn-reject"
                    disabled={acting === eq.id}
                    onClick={() => act(eq.id, 'reject')}
                  >
                    ✕ Rejeter
                  </button>
                </td>
              </tr>
            ))}
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
    const token = btoa(`${user}:${pass}`)
    try {
      const resp = await fetch(`${API}?limit=1`, {
        headers: authHeader(token),
      })
      if (resp.status === 401) {
        setError('Identifiants incorrects.')
      } else if (!resp.ok) {
        setError(`Erreur serveur : ${resp.status}`)
      } else {
        sessionStorage.setItem('admin_token', token)
        onLogin(token)
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

function CreateForm({ token, onCreated }) {
  const [open, setOpen] = useState(false)
  const [sigleA, setSigleA] = useState('')
  const [sigleB, setSigleB] = useState('')
  const [source, setSource] = useState('official')
  const [evidence, setEvidence] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)

  async function handleSubmit(e) {
    e.preventDefault()
    if (!sigleA.trim() || !sigleB.trim()) return
    setLoading(true)
    setError(null)
    try {
      const resp = await fetch(API, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', ...authHeader(token) },
        body: JSON.stringify({
          sigle_a: sigleA.trim().toUpperCase(),
          sigle_b: sigleB.trim().toUpperCase(),
          source,
          evidence: evidence.trim() || null,
        }),
      })
      if (!resp.ok) {
        const body = await resp.json().catch(() => ({}))
        setError(body.detail || `Erreur ${resp.status}`)
      } else {
        setSigleA(''); setSigleB(''); setEvidence(''); setSource('official')
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
            <div className="admin-create-field">
              <label className="admin-field-label">Source</label>
              <select
                className="admin-input"
                value={source}
                onChange={e => setSource(e.target.value)}
              >
                <option value="official">official</option>
                <option value="inferred">inferred</option>
                <option value="request">request</option>
              </select>
            </div>
          </div>
          <div className="admin-create-field" style={{ marginTop: '0.5rem' }}>
            <label className="admin-field-label">Justification (optionnel)</label>
            <input
              className="admin-input"
              placeholder="ex. Même syllabus, approuvé par comité pédagogique"
              value={evidence}
              onChange={e => setEvidence(e.target.value)}
            />
          </div>
          {error && <p className="admin-error" style={{ marginTop: '0.5rem' }}>{error}</p>}
          <button
            className="admin-btn-primary"
            type="submit"
            disabled={loading}
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
        <option value="official">official</option>
        <option value="inferred">inferred</option>
        <option value="request">request</option>
      </select>
      <select
        className="admin-filter-select"
        value={filters.status}
        onChange={e => onChange({ ...filters, status: e.target.value })}
      >
        <option value="">Tous statuts</option>
        <option value="active">active</option>
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
  official: '#0057a8',
  inferred: '#6c3fb5',
  request:  '#c97300',
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

function EquivTable({ rows, token, onRefresh }) {
  const [acting, setActing] = useState(null)

  async function revoke(id) {
    setActing(id)
    try {
      await fetch(`${API}/${id}`, {
        method: 'DELETE',
        headers: authHeader(token),
      })
      onRefresh()
    } finally {
      setActing(null)
    }
  }

  async function restore(id) {
    setActing(id)
    try {
      await fetch(`${API}/${id}/restore`, {
        method: 'PATCH',
        headers: authHeader(token),
      })
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
  const [token, setToken] = useState(
    () => sessionStorage.getItem('admin_token') || null
  )
  const [rows, setRows] = useState([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const [filters, setFilters] = useState({ source: '', status: 'active', sigle: '' })

  const fetchEquivs = useCallback(async (tok, f) => {
    setLoading(true)
    setError(null)
    const params = new URLSearchParams({ limit: '200' })
    if (f.source) params.set('source', f.source)
    if (f.status) params.set('status', f.status)
    if (f.sigle.trim()) params.set('sigle', f.sigle.trim().toUpperCase())
    try {
      const resp = await fetch(`${API}?${params}`, { headers: authHeader(tok) })
      if (resp.status === 401) {
        sessionStorage.removeItem('admin_token')
        setToken(null)
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
    if (token) fetchEquivs(token, filters)
  }, [token, filters, fetchEquivs])

  function handleLogin(tok) {
    setToken(tok)
  }

  function handleLogout() {
    sessionStorage.removeItem('admin_token')
    setToken(null)
  }

  if (!token) {
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
          <span className="admin-stats">
            {active} actives · {revoked} révoquées
          </span>
        </div>
        <button className="admin-logout-btn" onClick={handleLogout}>
          Déconnexion
        </button>
      </div>

      <div className="admin-body">
        <CreateForm
          token={token}
          onCreated={() => fetchEquivs(token, filters)}
        />

        <FiltersBar filters={filters} onChange={setFilters} />

        {loading && <p className="admin-loading">Chargement…</p>}
        {error && <p className="admin-error">{error}</p>}
        {!loading && !error && (
          <EquivTable
            rows={rows}
            token={token}
            onRefresh={() => fetchEquivs(token, filters)}
          />
        )}
      </div>
    </div>
  )
}
