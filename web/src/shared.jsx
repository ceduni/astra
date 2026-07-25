import { useEffect, useState } from 'react'

export const API = '/api'

export function useUniversities() {
  const [universities, setUniversities] = useState([])
  useEffect(() => {
    fetch(`${API}/universities`)
      .then(r => r.json())
      .then(data => setUniversities(data.map(u => u.name).sort()))
      .catch(() => {})
  }, [])
  return universities
}

export function useDebounce(value, delay) {
  const [debounced, setDebounced] = useState(value)
  useEffect(() => {
    const t = setTimeout(() => setDebounced(value), delay)
    return () => clearTimeout(t)
  }, [value, delay])
  return debounced
}

// ── Collapsible section ────────────────────────────────────────────────────────

export function Section({ label, count, children, defaultOpen = true, grow = false }) {
  const [open, setOpen] = useState(defaultOpen)
  return (
    <div className={`sidebar-section${grow ? ' grow' : ''}`}>
      <button className="section-toggle" onClick={() => setOpen(o => !o)}>
        <span className="section-label">
          {label}{count != null ? ` (${count})` : ''}
        </span>
        <span className="section-chevron">{open ? '▴' : '▾'}</span>
      </button>
      {open && <div className="section-body">{children}</div>}
    </div>
  )
}

// ── Search + add to completed ──────────────────────────────────────────────────

export function SearchSection({ onAddCompleted, onVisualize, completed }) {
  const [query, setQuery] = useState('')
  const [results, setResults] = useState([])
  const [loading, setLoading] = useState(false)
  const debouncedQuery = useDebounce(query, 300)

  const completedSigles = new Set(completed.map(c => c.sigle))

  useEffect(() => {
    if (debouncedQuery.length < 2) { setResults([]); return }
    setLoading(true)
    fetch(`${API}/search?q=${encodeURIComponent(debouncedQuery)}`)
      .then(r => r.json())
      .then(setResults)
      .catch(() => setResults([]))
      .finally(() => setLoading(false))
  }, [debouncedQuery])

  return (
    <Section label="Explorer" defaultOpen={true}>
      <input
        type="search"
        className="search-input"
        placeholder="Sigle, titre, description…"
        value={query}
        onChange={e => setQuery(e.target.value)}
      />
      {loading && <p className="hint">Recherche…</p>}
      {results.length > 0 && (
        <div className="result-list">
          {results.map(course => {
            const done = completedSigles.has(course.sigle)
            return (
              <div key={`${course.universite}-${course.sigle}`} className={`result-row ${done ? 'done' : ''}`}>
                <span className="uni-dot" data-uni={course.universite} />
                <div className="result-info">
                  <span className="sigle">{course.sigle}</span>
                  <span className="compact-titre">{course.titre}</span>
                </div>
                <div className="result-actions">
                  <button
                    className="btn-add"
                    onClick={() => { onAddCompleted(course); setQuery(''); setResults([]) }}
                    disabled={done}
                    title={done ? 'Déjà ajouté' : 'Ajouter à mon parcours'}
                  >✓</button>
                  {onVisualize && (
                    <button
                      className="btn-add"
                      onClick={() => onVisualize(course)}
                      title="Visualiser la chaîne de prérequis"
                    >⬡</button>
                  )}
                </div>
              </div>
            )
          })}
        </div>
      )}
    </Section>
  )
}

// ── Completed courses list ─────────────────────────────────────────────────────

export function CompletedSection({ completed, onRemove, onSelect }) {
  return (
    <Section label="Complétés" count={completed.length || null} defaultOpen={true}>
      {completed.length === 0 ? (
        <p className="hint">Aucun cours ajouté.</p>
      ) : (
        <ul className="completed-list">
          {completed.map(course => (
            <li
              key={course.sigle}
              className="completed-item"
              onClick={() => onSelect?.(course)}
              style={{ cursor: onSelect ? 'pointer' : 'default' }}
            >
              <span className="uni-dot" data-uni={course.universite} />
              <div className="result-info">
                <span className="sigle">{course.sigle}</span>
                <span className="compact-titre">{course.titre}</span>
              </div>
              <button
                className="btn-remove"
                onClick={e => { e.stopPropagation(); onRemove(course.sigle) }}
                title="Retirer"
              >×</button>
            </li>
          ))}
        </ul>
      )}
    </Section>
  )
}
