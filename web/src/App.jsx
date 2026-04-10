import { useEffect, useRef, useState, useCallback } from 'react'
import GraphCanvas from './GraphCanvas'

const API = '/api'

function useDebounce(value, delay) {
  const [debounced, setDebounced] = useState(value)
  useEffect(() => {
    const t = setTimeout(() => setDebounced(value), delay)
    return () => clearTimeout(t)
  }, [value, delay])
  return debounced
}

// ── Collapsible sidebar section ────────────────────────────────────────────────

function Section({ label, count, children, defaultOpen = true, grow = false }) {
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

// ── Sidebar: Search section ────────────────────────────────────────────────────

function SearchSection({ onAdd, completed }) {
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
                <button
                  className="btn-add"
                  onClick={() => onAdd(course)}
                  disabled={done}
                  title={done ? 'Déjà ajouté' : 'Ajouter au profil + visualiser'}
                >
                  {done ? '✓' : '+'}
                </button>
              </div>
            )
          })}
        </div>
      )}
    </Section>
  )
}

// ── Sidebar: Completed courses ─────────────────────────────────────────────────

function CompletedSection({ completed, onRemove, onSelect }) {
  return (
    <Section label="Complétés" count={completed.length || null} defaultOpen={true}>
      {completed.length === 0 ? (
        <p className="hint">Aucun cours ajouté.</p>
      ) : (
        <ul className="completed-list">
          {completed.map(course => (
            <li key={course.sigle} className="completed-item" onClick={() => onSelect(course)}>
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

// ── Sidebar: Eligible courses ──────────────────────────────────────────────────

function EligibleSection({ completed, onSelect }) {
  const [eligible, setEligible] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)

  function fetchEligible() {
    setLoading(true)
    setError(null)
    fetch(`${API}/courses/eligible`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ completed: completed.map(c => c.sigle) }),
    })
      .then(r => { if (!r.ok) throw new Error(`HTTP ${r.status}`); return r.json() })
      .then(setEligible)
      .catch(e => setError(e.message))
      .finally(() => setLoading(false))
  }

  return (
    <Section label="Accessibles" count={eligible ? eligible.length : null} defaultOpen={true} grow={true}>
      <button
        className="btn-primary"
        onClick={fetchEligible}
        disabled={loading || completed.length === 0}
      >
        {loading ? 'Calcul…' : 'Voir mes cours accessibles'}
      </button>
      {completed.length === 0 && (
        <p className="hint">Ajoutez des cours complétés d'abord.</p>
      )}
      {error && <p className="error">{error}</p>}
      {eligible !== null && !loading && (
        <>
          <p className="hint" style={{marginTop:'0.25rem'}}>{eligible.length} cours accessible{eligible.length !== 1 ? 's' : ''}</p>
          <div className="eligible-list">
            {['UdeM','UQAM','McGill','Concordia','Poly'].map(uni => {
              const group = eligible.filter(c => c.universite === uni)
              if (group.length === 0) return null
              return (
                <div key={uni}>
                  <div className="eligible-group-label">
                    <span className="uni-dot" data-uni={uni} />
                    {uni} ({group.length})
                  </div>
                  {group.map(course => (
                    <div key={course.sigle} className="result-row" onClick={() => onSelect(course)}>
                      <div className="result-info">
                        <span className="sigle">{course.sigle}</span>
                        <span className="compact-titre">{course.titre}</span>
                      </div>
                    </div>
                  ))}
                </div>
              )
            })}
          </div>
        </>
      )}
    </Section>
  )
}

// ── Detail panel ───────────────────────────────────────────────────────────────

function DetailPanel({ course, completed, onClose, onAdd, onRemove }) {
  if (!course) return <div className="detail-panel" />

  const isDone = completed.some(c => c.sigle === course.sigle)

  return (
    <div className="detail-panel open" data-uni={course.universite}>
      <div className="detail-inner">
        <div className="detail-top">
          <div className="detail-title-block">
            <span className="sigle">{course.sigle}</span>
            <h3>{course.titre || '(sans titre)'}</h3>
          </div>
          <div className="detail-actions">
            {isDone ? (
              <button className="btn-complete done" onClick={() => onRemove(course.sigle)}>
                ✓ Complété
              </button>
            ) : (
              <button className="btn-complete" onClick={() => onAdd(course)}>
                + Marquer complété
              </button>
            )}
            <button className="btn-dismiss" onClick={onClose} title="Fermer">×</button>
          </div>
        </div>

        <div className="detail-meta">
          <span>{course.universite}</span>
          <span>{course.credits ? `${course.credits} crédits` : 'Crédits N/A'}</span>
          <span>Niveau {course.niveau}</span>
          {course.hors_perimetre && <span style={{color:'#c00'}}>Hors périmètre</span>}
        </div>

        {course.description && (
          <p className="detail-description">{course.description}</p>
        )}

        {course.requirement_text && (
          <p className="detail-req">{course.requirement_text}</p>
        )}
      </div>
    </div>
  )
}

// ── Root ───────────────────────────────────────────────────────────────────────

export default function App() {
  const [completed, setCompleted] = useState([])
  const [selectedCourse, setSelectedCourse] = useState(null)
  const [chainToLoad, setChainToLoad] = useState(null)
  const [resetKey, setResetKey] = useState(0)

  // ── Sidebar resize ───────────────────────────────────────────────────────────
  const [sidebarWidth, setSidebarWidth] = useState(340)
  const [collapsed, setCollapsed] = useState(false)
  const isDragging = useRef(false)
  const dragStartX = useRef(0)
  const dragStartWidth = useRef(0)

  const onDividerMouseDown = useCallback(e => {
    if (collapsed) return
    isDragging.current = true
    dragStartX.current = e.clientX
    dragStartWidth.current = sidebarWidth
    e.preventDefault()
  }, [collapsed, sidebarWidth])

  useEffect(() => {
    function onMove(e) {
      if (!isDragging.current) return
      const delta = e.clientX - dragStartX.current
      setSidebarWidth(Math.max(220, Math.min(580, dragStartWidth.current + delta)))
    }
    function onUp() { isDragging.current = false }
    document.addEventListener('mousemove', onMove)
    document.addEventListener('mouseup', onUp)
    return () => {
      document.removeEventListener('mousemove', onMove)
      document.removeEventListener('mouseup', onUp)
    }
  }, [])

  // ── Course actions ───────────────────────────────────────────────────────────

  function addCourse(course) {
    setCompleted(prev =>
      prev.some(c => c.sigle === course.sigle) ? prev : [...prev, course]
    )
    setChainToLoad(course.sigle)
    setSelectedCourse(course)
  }

  function removeCourse(sigle) {
    setCompleted(prev => prev.filter(c => c.sigle !== sigle))
  }

  function selectCourse(course) {
    setSelectedCourse(course)
    setChainToLoad(course.sigle)
  }

  function handleReset() {
    setCompleted([])
    setSelectedCourse(null)
    setChainToLoad(null)
    setResetKey(k => k + 1)
  }

  return (
    <div className="app-shell">
      {/* ── Sidebar ── */}
      <aside
        className="sidebar"
        style={{ width: collapsed ? 0 : sidebarWidth }}
      >
        <div className="sidebar-header">
          <h1>Astra</h1>
          <p>Explorez les relations entre les cours interuniversitaires</p>
        </div>

        <div className="sidebar-body">
          <SearchSection onAdd={addCourse} completed={completed} />
          <CompletedSection
            completed={completed}
            onRemove={removeCourse}
            onSelect={selectCourse}
          />
          <EligibleSection completed={completed} onSelect={selectCourse} />
        </div>

        <div className="sidebar-footer">
          <button className="btn-reset" onClick={handleReset}>
            Réinitialiser le graphe
          </button>
        </div>
      </aside>

      {/* ── Resize handle ── */}
      <div
        className="resize-handle"
        onMouseDown={onDividerMouseDown}
      >
        <button
          className="collapse-btn"
          onClick={() => setCollapsed(c => !c)}
          title={collapsed ? 'Ouvrir le panneau' : 'Fermer le panneau'}
        >
          {collapsed ? '›' : '‹'}
        </button>
      </div>

      {/* ── Main area ── */}
      <main className="main-area">
        <div className="graph-canvas-wrapper">
          <GraphCanvas
            completed={completed}
            chainToLoad={chainToLoad}
            resetKey={resetKey}
            onNodeClick={selectCourse}
          />
        </div>

        <DetailPanel
          course={selectedCourse}
          completed={completed}
          onClose={() => setSelectedCourse(null)}
          onAdd={addCourse}
          onRemove={removeCourse}
        />
      </main>
    </div>
  )
}
