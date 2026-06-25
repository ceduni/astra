import { useEffect, useState } from 'react'
import { API, useDebounce } from './shared'

const UNIVERSITIES = ['UdeM', 'UQAM', 'McGill', 'Concordia', 'Poly']

const SOURCE_STYLE = {
  official: { bg: '#e6f4ea', color: '#1e7e34' },
  inferred: { bg: '#fff8e1', color: '#8a6d00' },
  request:  { bg: '#e8f0fe', color: '#1a47a8' },
}

function SourceBadge({ source }) {
  const s = SOURCE_STYLE[source] || { bg: '#eee', color: '#888' }
  return (
    <span style={{
      background: s.bg, color: s.color,
      fontSize: 11, fontWeight: 700, letterSpacing: '0.03em',
      padding: '2px 8px', borderRadius: 4, whiteSpace: 'nowrap',
    }}>
      {source}
    </span>
  )
}

function ConfBar({ value }) {
  if (value == null) return <span style={{ color: '#ccc', fontSize: 12 }}>—</span>
  const pct = Math.round(value * 100)
  const fill = pct >= 60 ? '#2a9d4e' : pct >= 40 ? '#f0a500' : '#ed1b2f'
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
      <div style={{ width: 64, height: 5, background: '#eee', borderRadius: 3, overflow: 'hidden', flexShrink: 0 }}>
        <div style={{ width: `${pct}%`, height: '100%', background: fill, borderRadius: 3 }} />
      </div>
      <span style={{ fontSize: 12, color: '#555', minWidth: 28 }}>{pct}%</span>
    </div>
  )
}

function UniCell({ sigle, titre, universite }) {
  return (
    <td className="equiv-course-cell">
      <div style={{ display: 'flex', alignItems: 'baseline', gap: 6 }}>
        <code className="sigle">{sigle}</code>
        <span className="uni-dot" data-uni={universite} style={{ flexShrink: 0, marginBottom: 1 }} />
        <span style={{ fontSize: 11, color: '#888', fontWeight: 600 }}>{universite}</span>
      </div>
      <div className="compact-titre" style={{ maxWidth: 240, marginTop: 2 }}>{titre}</div>
    </td>
  )
}

export default function EquivalencesPage() {
  const [rows, setRows]         = useState([])
  const [loading, setLoading]   = useState(true)
  const [source, setSource]     = useState('')
  const [uni, setUni]           = useState('')
  const [rawQ, setRawQ]         = useState('')
  const q = useDebounce(rawQ, 250)

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    const params = new URLSearchParams({ limit: '500' })
    if (source)   params.set('source', source)
    if (uni)      params.set('universite', uni)
    if (q.trim()) params.set('q', q.trim())
    fetch(`${API}/equivalences?${params}`)
      .then(r => r.json())
      .then(data => { if (!cancelled) setRows(Array.isArray(data) ? data : []) })
      .catch(() => { if (!cancelled) setRows([]) })
      .finally(() => { if (!cancelled) setLoading(false) })
    return () => { cancelled = true }
  }, [source, uni, q])

  return (
    <div className="equiv-shell">
      <div className="equiv-toolbar">
        <div className="equiv-toolbar-left">
          <h2 className="equiv-title">Équivalences de cours</h2>
          <span className="equiv-count">
            {loading ? '…' : `${rows.length} paire${rows.length !== 1 ? 's' : ''}`}
          </span>
        </div>
        <div className="equiv-filters">
          <select
            className="equiv-select"
            value={source}
            onChange={e => setSource(e.target.value)}
          >
            <option value="">Toutes sources</option>
            <option value="official">Officielles</option>
            <option value="inferred">Inférées</option>
            <option value="request">Demandes</option>
          </select>
          <select
            className="equiv-select"
            value={uni}
            onChange={e => setUni(e.target.value)}
          >
            <option value="">Toutes universités</option>
            {UNIVERSITIES.map(u => <option key={u} value={u}>{u}</option>)}
          </select>
          <input
            className="equiv-search"
            placeholder="Chercher sigle ou titre…"
            value={rawQ}
            onChange={e => setRawQ(e.target.value)}
          />
        </div>
      </div>

      <div className="equiv-table-wrap">
        {loading && (
          <p style={{ padding: '3rem', color: '#aaa', textAlign: 'center' }}>Chargement…</p>
        )}
        {!loading && rows.length === 0 && (
          <p style={{ padding: '3rem', color: '#bbb', textAlign: 'center' }}>
            Aucune équivalence trouvée.
          </p>
        )}
        {!loading && rows.length > 0 && (
          <table className="equiv-table">
            <thead>
              <tr>
                <th>Cours A</th>
                <th>Cours B</th>
                <th>Source</th>
                <th>Confiance</th>
              </tr>
            </thead>
            <tbody>
              {rows.map(row => (
                <tr key={row.id}>
                  <UniCell sigle={row.sigle_a} titre={row.titre_a} universite={row.universite_a} />
                  <UniCell sigle={row.sigle_b} titre={row.titre_b} universite={row.universite_b} />
                  <td><SourceBadge source={row.source} /></td>
                  <td><ConfBar value={row.confidence} /></td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  )
}
