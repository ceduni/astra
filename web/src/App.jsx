import { useEffect, useState } from 'react'

const API = '/api'

function useDebounce(value, delay) {
  const [debounced, setDebounced] = useState(value)
  useEffect(() => {
    const t = setTimeout(() => setDebounced(value), delay)
    return () => clearTimeout(t)
  }, [value, delay])
  return debounced
}

function CourseCard({ course }) {
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
        {course.hors_perimetre && <span className="tag">hors périmètre</span>}
      </div>
    </div>
  )
}

export default function App() {
  const [query, setQuery] = useState('')
  const [universite, setUniversite] = useState('')
  const [universities, setUniversities] = useState([])
  const [results, setResults] = useState([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const [searched, setSearched] = useState(false)

  const debouncedQuery = useDebounce(query, 300)

  useEffect(() => {
    fetch(`${API}/universities`)
      .then(r => r.json())
      .then(setUniversities)
      .catch(() => {})
  }, [])

  useEffect(() => {
    if (debouncedQuery.length < 2) {
      setResults([])
      setSearched(false)
      return
    }

    const params = new URLSearchParams({ q: debouncedQuery })
    if (universite) params.set('universite', universite)

    setLoading(true)
    setError(null)

    fetch(`${API}/search?${params}`)
      .then(r => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`)
        return r.json()
      })
      .then(data => {
        setResults(data)
        setSearched(true)
      })
      .catch(e => setError(e.message))
      .finally(() => setLoading(false))
  }, [debouncedQuery, universite])

  return (
    <div className="app">
      <header>
        <h1>Cours interuniversitaires</h1>
        <p>UdeM · UQAM · McGill · Concordia · Polytechnique</p>
      </header>

      <div className="controls">
        <input
          type="search"
          placeholder="Rechercher un cours (titre ou description)…"
          value={query}
          onChange={e => setQuery(e.target.value)}
          autoFocus
        />
        <select value={universite} onChange={e => setUniversite(e.target.value)}>
          <option value="">Toutes les universités</option>
          {universities.map(u => (
            <option key={u.name} value={u.name}>
              {u.name} ({u.program_courses} cours)
            </option>
          ))}
        </select>
      </div>

      <div className="status">
        {loading && <span>Recherche…</span>}
        {error && <span className="error">Erreur : {error}</span>}
        {!loading && searched && (
          <span>{results.length} résultat{results.length !== 1 ? 's' : ''}</span>
        )}
        {!loading && !searched && query.length > 0 && query.length < 2 && (
          <span>Entrez au moins 2 caractères</span>
        )}
      </div>

      <div className="grid">
        {results.map(course => (
          <CourseCard key={`${course.universite}-${course.sigle}`} course={course} />
        ))}
      </div>
    </div>
  )
}
