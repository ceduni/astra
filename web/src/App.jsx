import { useEffect, useReducer, useState } from 'react'

const API = '/api'

// ── Utilities ──────────────────────────────────────────────────────────────

function useDebounce(value, delay) {
  const [debounced, setDebounced] = useState(value)
  useEffect(() => {
    const t = setTimeout(() => setDebounced(value), delay)
    return () => clearTimeout(t)
  }, [value, delay])
  return debounced
}

function groupBy(arr, key) {
  return arr.reduce((acc, item) => {
    const k = item[key]
    if (!acc[k]) acc[k] = []
    acc[k].push(item)
    return acc
  }, {})
}

// ── Small shared components ────────────────────────────────────────────────

function CourseCard({ course, action }) {
  return (
    <div className="card">
      <div className="card-header">
        <span className="sigle">{course.sigle}</span>
        <span className="universite">{course.universite}</span>
      </div>
      <div className="titre">{course.titre}</div>
      <div className="card-meta">
        <span>{course.credits} cr</span>
        <span>Niveau {course.niveau}</span>
        {action}
      </div>
    </div>
  )
}

function CompactCourse({ course, action }) {
  return (
    <div className="compact-course">
      <span className="sigle">{course.sigle}</span>
      <span className="compact-titre">{course.titre}</span>
      {action}
    </div>
  )
}

// ── Left panel: profile / completed courses ────────────────────────────────

function ProfilePanel({ completed, onAdd, onRemove }) {
  const [query, setQuery] = useState('')
  const [results, setResults] = useState([])
  const [loading, setLoading] = useState(false)
  const debouncedQuery = useDebounce(query, 300)

  useEffect(() => {
    if (debouncedQuery.length < 2) { setResults([]); return }
    setLoading(true)
    fetch(`${API}/search?q=${encodeURIComponent(debouncedQuery)}`)
      .then(r => r.json())
      .then(setResults)
      .catch(() => setResults([]))
      .finally(() => setLoading(false))
  }, [debouncedQuery])

  const completedSigles = new Set(completed.map(c => c.sigle))

  return (
    <div className="panel">
      <h2>Mon profil</h2>

      <div className="panel-section">
        <label className="section-label">Ajouter des cours complétés</label>
        <input
          type="search"
          className="panel-input"
          placeholder="Rechercher un cours…"
          value={query}
          onChange={e => setQuery(e.target.value)}
        />

        {loading && <p className="hint">Recherche…</p>}

        {results.length > 0 && (
          <div className="search-results-list">
            {results.map(course => {
              const done = completedSigles.has(course.sigle)
              return (
                <div key={course.sigle} className={`result-row ${done ? 'done' : ''}`}>
                  <div className="result-info">
                    <span className="sigle">{course.sigle}</span>
                    <span className="compact-titre">{course.titre}</span>
                  </div>
                  <button
                    className="btn-add"
                    onClick={() => onAdd(course)}
                    disabled={done}
                    title={done ? 'Déjà ajouté' : 'Ajouter'}
                  >
                    {done ? '✓' : '+'}
                  </button>
                </div>
              )
            })}
          </div>
        )}
      </div>

      <div className="panel-section">
        <label className="section-label">
          Cours complétés{completed.length > 0 ? ` (${completed.length})` : ''}
        </label>

        {completed.length === 0 ? (
          <p className="hint">Aucun cours ajouté.</p>
        ) : (
          <ul className="completed-list">
            {completed.map(course => (
              <li key={course.sigle} className="completed-item">
                <span className="sigle">{course.sigle}</span>
                <span className="compact-titre">{course.titre}</span>
                <button
                  className="btn-remove"
                  onClick={() => onRemove(course.sigle)}
                  title="Retirer"
                >×</button>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  )
}

// ── Right panel: eligible courses ──────────────────────────────────────────

function EligiblePanel({ completed }) {
  const [eligible, setEligible] = useState(null)   // null = not yet fetched
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

  const byUni = eligible ? groupBy(eligible, 'universite') : {}
  const uniNames = Object.keys(byUni).sort()

  return (
    <div className="panel eligible-panel">
      <div className="eligible-header">
        <h2>Cours accessibles</h2>
        <button
          className="btn-primary"
          onClick={fetchEligible}
          disabled={loading || completed.length === 0}
        >
          {loading ? 'Calcul…' : 'Voir mes cours accessibles'}
        </button>
        {completed.length === 0 && (
          <p className="hint">Ajoutez des cours complétés pour voir ce qui est accessible.</p>
        )}
      </div>

      {error && <p className="error">Erreur : {error}</p>}

      {eligible !== null && !loading && (
        <>
          <p className="result-count">
            {eligible.length} cours accessible{eligible.length !== 1 ? 's' : ''}
            {' '}dans {uniNames.length} université{uniNames.length !== 1 ? 's' : ''}
          </p>

          {uniNames.map(uni => (
            <div key={uni} className="uni-group">
              <h3 className="uni-heading">
                {uni}
                <span className="uni-count">{byUni[uni].length}</span>
              </h3>
              <div className="eligible-grid">
                {byUni[uni].map(course => (
                  <CourseCard key={course.sigle} course={course} />
                ))}
              </div>
            </div>
          ))}
        </>
      )}
    </div>
  )
}

// ── Top search (general explore) ───────────────────────────────────────────

function ExploreSection({ universities }) {
  const [query, setQuery] = useState('')
  const [universite, setUniversite] = useState('')
  const [results, setResults] = useState([])
  const [loading, setLoading] = useState(false)
  const [searched, setSearched] = useState(false)
  const debouncedQuery = useDebounce(query, 300)

  useEffect(() => {
    if (debouncedQuery.length < 2) { setResults([]); setSearched(false); return }
    const params = new URLSearchParams({ q: debouncedQuery })
    if (universite) params.set('universite', universite)
    setLoading(true)
    fetch(`${API}/search?${params}`)
      .then(r => r.json())
      .then(d => { setResults(d); setSearched(true) })
      .catch(() => {})
      .finally(() => setLoading(false))
  }, [debouncedQuery, universite])

  return (
    <section className="explore-section">
      <h2>Explorer les cours</h2>
      <div className="controls">
        <input
          type="search"
          placeholder="Rechercher par sigle, titre ou description…"
          value={query}
          onChange={e => setQuery(e.target.value)}
        />
        <select value={universite} onChange={e => setUniversite(e.target.value)}>
          <option value="">Toutes les universités</option>
          {universities.map(u => (
            <option key={u.name} value={u.name}>
              {u.name} ({u.program_courses})
            </option>
          ))}
        </select>
      </div>

      <div className="status">
        {loading && <span>Recherche…</span>}
        {!loading && searched && <span>{results.length} résultat{results.length !== 1 ? 's' : ''}</span>}
        {!loading && !searched && query.length > 0 && query.length < 2 && <span>Entrez au moins 2 caractères</span>}
      </div>

      {results.length > 0 && (
        <div className="grid">
          {results.map(c => <CourseCard key={`${c.universite}-${c.sigle}`} course={c} />)}
        </div>
      )}
    </section>
  )
}

// ── Root ───────────────────────────────────────────────────────────────────

export default function App() {
  const [universities, setUniversities] = useState([])
  const [completed, setCompleted] = useState([])   // array of course objects, ordered

  useEffect(() => {
    fetch(`${API}/universities`).then(r => r.json()).then(setUniversities).catch(() => {})
  }, [])

  function addCourse(course) {
    setCompleted(prev =>
      prev.some(c => c.sigle === course.sigle) ? prev : [...prev, course]
    )
  }

  function removeCourse(sigle) {
    setCompleted(prev => prev.filter(c => c.sigle !== sigle))
  }

  return (
    <div className="app">
      <header>
        <h1>Cours interuniversitaires</h1>
        <p>UdeM · UQAM · McGill · Concordia · Polytechnique</p>
      </header>

      <div className="two-col">
        <ProfilePanel completed={completed} onAdd={addCourse} onRemove={removeCourse} />
        <EligiblePanel completed={completed} />
      </div>

      <ExploreSection universities={universities} />
    </div>
  )
}
