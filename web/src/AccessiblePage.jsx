import { useEffect, useState } from 'react'
import { API, SearchSection, CompletedSection, useUniversities } from './shared'

const UNI_ACCENT = {
  UdeM: '#0057a8', UQAM: '#00833e', McGill: '#ed1b2f',
  Concordia: '#912338', Poly: '#f0a500', ETS: '#0891b2',
}

// ── Course card ────────────────────────────────────────────────────────────────

function CourseCard({ course }) {
  const accent = UNI_ACCENT[course.universite] || '#999'
  return (
    <div className="course-card" style={{ borderTopColor: accent }}>
      <div className="course-card-top">
        <code className="course-card-sigle">{course.sigle}</code>
        {course.official_equiv_sigle && (
          <span className="badge-equiv" title={`Équivalent à ${course.official_equiv_sigle}`}>
            Équivalent
          </span>
        )}
      </div>
      <div className="course-card-title">
        {course.titre || '(sans titre)'}
      </div>
      {(course.credits || course.niveau) && (
        <div className="course-card-meta">
          {[
            course.credits && `${course.credits} cr`,
            course.niveau && `Niv. ${course.niveau}`,
          ].filter(Boolean).join(' · ')}
        </div>
      )}
      {course.tags && course.tags.length > 0 && (
        <div className="course-card-tags">
          {course.tags.slice(0, 3).map(t => (
            <span key={t} className="tag-pill">{t}</span>
          ))}
        </div>
      )}
    </div>
  )
}

// ── Page ───────────────────────────────────────────────────────────────────────

export default function AccessiblePage({
  completed, onAddCompleted, onRemoveCompleted,
  homeUniversite, onSetHome,
}) {
  const universities = useUniversities()
  const [eligible, setEligible] = useState([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    setError(null)
    fetch(`${API}/courses/eligible`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        completed: completed.map(c => c.sigle),
        home_universite: homeUniversite || null,
      }),
    })
      .then(r => { if (!r.ok) throw new Error(`HTTP ${r.status}`); return r.json() })
      .then(data => { if (!cancelled) setEligible(data) })
      .catch(e => { if (!cancelled) setError(e.message) })
      .finally(() => { if (!cancelled) setLoading(false) })
    return () => { cancelled = true }
  }, [completed, homeUniversite])

  const visibleUnis = homeUniversite
    ? universities.filter(u => u !== homeUniversite)
    : universities

  const byUni = {}
  for (const c of eligible) {
    if (!byUni[c.universite]) byUni[c.universite] = []
    byUni[c.universite].push(c)
  }

  const equivCount = eligible.filter(c => c.official_equiv_sigle).length

  return (
    <div className="accessible-shell">

      {/* ── Sidebar ── */}
      <aside className="accessible-sidebar">
        <div className="sidebar-section" style={{ borderBottom: '1px solid #f3f4f6', paddingBottom: '1rem' }}>
          <div className="section-label" style={{ marginBottom: '0.6rem' }}>Mon université</div>
          <div className="uni-selector">
            {universities.map(uni => (
              <button
                key={uni}
                className={`uni-pill${homeUniversite === uni ? ' active' : ''}`}
                onClick={() => onSetHome(homeUniversite === uni ? null : uni)}
                data-uni={uni}
              >
                <span className="uni-dot" data-uni={uni} />
                {uni}
              </button>
            ))}
          </div>
          {homeUniversite && (
            <p className="hint" style={{ marginTop: '0.5rem' }}>
              Cours des autres universités affichés
            </p>
          )}
        </div>

        <SearchSection onAddCompleted={onAddCompleted} completed={completed} />
        <CompletedSection completed={completed} onRemove={onRemoveCompleted} />
      </aside>

      {/* ── Main ── */}
      <main className="accessible-main">
        <div className="accessible-header">
          {loading ? (
            <span className="accessible-summary">Calcul des cours accessibles…</span>
          ) : error ? (
            <span className="error">{error}</span>
          ) : (
            <span className="accessible-summary">
              <strong>{eligible.length}</strong> cours accessibles
              {equivCount > 0 && (
                <> · <span style={{ color: '#2a9d4e' }}>{equivCount} avec équivalence officielle</span></>
              )}
              {homeUniversite && <> dans les universités partenaires</>}
            </span>
          )}
        </div>

        {!loading && !error && eligible.length === 0 && (
          <div className="accessible-empty">
            <div className="accessible-empty-icon">⬡</div>
            <p className="accessible-empty-text">
              {completed.length === 0
                ? 'Ajoutez des cours complétés dans la barre latérale pour voir les cours accessibles.'
                : 'Aucun cours accessible avec vos cours complétés.'}
            </p>
          </div>
        )}

        <div className="accessible-groups">
          {visibleUnis.map(uni => {
            const courses = byUni[uni] || []
            if (courses.length === 0) return null
            return (
              <section key={uni} className="accessible-group">
                <div className="accessible-group-header">
                  <span className="uni-dot" data-uni={uni} />
                  <span className="accessible-group-name" style={{ color: UNI_ACCENT[uni] }}>
                    {uni}
                  </span>
                  <span className="accessible-group-count">{courses.length} cours</span>
                </div>
                <div className="accessible-cards">
                  {courses.map(course => (
                    <CourseCard key={course.sigle} course={course} />
                  ))}
                </div>
              </section>
            )
          })}
        </div>
      </main>
    </div>
  )
}
