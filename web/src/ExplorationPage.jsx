import { useEffect, useState } from 'react'
import { API, SearchSection, CompletedSection, useUniversities } from './shared'
import ExplorationGraph from './ExplorationGraph'

const PROGRAMME_LABELS = {
  informatique: 'Informatique',
  informatique_genie_logiciel: 'Informatique & génie logiciel',
  computer_science: 'Computer Science',
  genie_informatique: 'Génie informatique',
  genie_logiciel: 'Génie logiciel',
  genie_technologies_information: 'Génie TI',
}
function programLabel(id) {
  return PROGRAMME_LABELS[id] ?? id.replace(/_/g, ' ')
}

function usePrograms(homeUniversite) {
  const [programs, setPrograms] = useState([])
  useEffect(() => {
    if (!homeUniversite) { setPrograms([]); return }
    fetch(`${API}/courses/programs`)
      .then(r => r.json())
      .then(data => setPrograms(data[homeUniversite] ?? []))
      .catch(() => setPrograms([]))
  }, [homeUniversite])
  return programs
}

// ── Detail panel ───────────────────────────────────────────────────────────────

function ConfBar({ value }) {
  if (value == null) return <span style={{ color: '#ccc', fontSize: 11 }}>—</span>
  const pct = Math.round(value * 100)
  const fill = pct >= 60 ? '#2a9d4e' : pct >= 40 ? '#f0a500' : '#ed1b2f'
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
      <div style={{ width: 48, height: 4, background: '#eee', borderRadius: 3, overflow: 'hidden' }}>
        <div style={{ width: `${pct}%`, height: '100%', background: fill }} />
      </div>
      <span style={{ fontSize: 10, color: '#777' }}>{pct}%</span>
    </div>
  )
}

function DetailPanel({ course, onClose }) {
  const [equivs, setEquivs] = useState([])
  const [loadingEquivs, setLoadingEquivs] = useState(false)

  useEffect(() => {
    if (!course) { setEquivs([]); return }
    setLoadingEquivs(true)
    fetch(`${API}/equivalences?q=${encodeURIComponent(course.sigle)}&limit=100`)
      .then(r => r.json())
      .then(data => {
        const exact = (Array.isArray(data) ? data : [])
          .filter(r => r.sigle_a === course.sigle || r.sigle_b === course.sigle)
          .map(r => {
            const isA = r.sigle_a === course.sigle
            return {
              sigle: isA ? r.sigle_b : r.sigle_a,
              titre: isA ? r.titre_b : r.titre_a,
              universite: isA ? r.universite_b : r.universite_a,
              source: r.source,
              confidence: r.confidence,
            }
          })
        setEquivs(exact)
      })
      .catch(() => setEquivs([]))
      .finally(() => setLoadingEquivs(false))
  }, [course?.sigle])

  if (!course) return <div className="detail-panel" />

  return (
    <div className="detail-panel open" data-uni={course.universite} style={{ maxHeight: 340 }}>
      <div className="detail-inner">
        <div className="detail-top">
          <div className="detail-title-block">
            <span className="sigle">{course.sigle}</span>
            <h3>{course.titre || '(sans titre)'}</h3>
          </div>
          <button className="btn-dismiss" onClick={onClose} title="Fermer">×</button>
        </div>

        <div className="detail-meta">
          <span>{course.universite}</span>
          <span>{course.credits ? `${course.credits} crédits` : 'Crédits N/A'}</span>
          <span>Niveau {course.niveau}</span>
        </div>

        {course.tags && course.tags.length > 0 && (
          <div className="detail-tags">
            {course.tags.map(tag => <span key={tag} className="tag-pill">{tag}</span>)}
          </div>
        )}

        {course.description && (
          <p className="detail-description">{course.description}</p>
        )}

        <div>
          <div style={{
            fontSize: 10, fontWeight: 700, color: '#aaa',
            textTransform: 'uppercase', letterSpacing: '0.07em', marginBottom: 6,
          }}>
            Équivalences
          </div>
          {loadingEquivs && <p style={{ fontSize: 11, color: '#bbb' }}>Chargement…</p>}
          {!loadingEquivs && equivs.length === 0 && (
            <p style={{ fontSize: 11, color: '#ccc' }}>Aucune équivalence connue.</p>
          )}
          {!loadingEquivs && equivs.length > 0 && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 5 }}>
              {equivs.map((eq, i) => (
                <div key={i} style={{
                  background: '#f9f9f9', borderRadius: 6,
                  padding: '5px 9px', fontSize: 11,
                  display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 8,
                }}>
                  <div style={{ minWidth: 0 }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 5, marginBottom: 2 }}>
                      <span className="uni-dot" data-uni={eq.universite} />
                      <strong style={{ fontFamily: 'monospace', fontSize: 11 }}>{eq.sigle}</strong>
                      <span style={{ color: '#aaa', fontSize: 10 }}>{eq.universite}</span>
                    </div>
                    <div style={{
                      color: '#666', fontSize: 10.5, overflow: 'hidden',
                      textOverflow: 'ellipsis', whiteSpace: 'nowrap', maxWidth: 220,
                    }}>
                      {eq.titre}
                    </div>
                  </div>
                  <div style={{ flexShrink: 0, display: 'flex', flexDirection: 'column', alignItems: 'flex-end', gap: 3 }}>
                    <span style={{
                      fontSize: 9, fontWeight: 700,
                      background: eq.source === 'official' ? '#e6f4ea' : '#fff8e1',
                      color: eq.source === 'official' ? '#1e7e34' : '#8a6d00',
                      padding: '1px 5px', borderRadius: 3, whiteSpace: 'nowrap',
                    }}>
                      {eq.source === 'official' ? 'OFFICIELLE' : 'SIMILAIRE'}
                    </span>
                    {eq.source !== 'official' && <ConfBar value={eq.confidence} />}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

// ── Page ───────────────────────────────────────────────────────────────────────

export default function ExplorationPage({
  completed, onAddCompleted, onRemoveCompleted,
  homeUniversite, onSetHome,
}) {
  const universities = useUniversities()
  const programs = usePrograms(homeUniversite)
  const [program, setProgram] = useState(null)
  const [selectedCourse, setSelectedCourse] = useState(null)

  // Reset program when university changes
  useEffect(() => { setProgram(null) }, [homeUniversite])

  return (
    <div className="vis-shell">
      {/* Sidebar */}
      <aside className="vis-sidebar" style={{ width: 280, borderRight: '1px solid #e5e7eb' }}>
        <div className="vis-sidebar-inner">
          <div className="sidebar-section" style={{ borderBottom: '1px solid #f3f4f6' }}>
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
          </div>

          {programs.length > 0 && (
            <div className="sidebar-section" style={{ borderBottom: '1px solid #f3f4f6' }}>
              <div className="section-label" style={{ marginBottom: '0.6rem' }}>Programme</div>
              <div className="uni-selector">
                {programs.map(p => (
                  <button
                    key={p.id}
                    className={`uni-pill${program === p.id ? ' active' : ''}`}
                    onClick={() => setProgram(program === p.id ? null : p.id)}
                  >
                    {programLabel(p.id)}
                  </button>
                ))}
              </div>
            </div>
          )}

          <SearchSection onAddCompleted={onAddCompleted} completed={completed} />
          <CompletedSection completed={completed} onRemove={onRemoveCompleted} />
        </div>
      </aside>

      {/* Main */}
      <div className="vis-main">
        <div className="graph-canvas-wrapper">
          {!homeUniversite ? (
            <div className="graph-empty">
              <div className="graph-empty-icon">⬡</div>
              <div className="graph-empty-text">
                Sélectionne ton université d'accueil pour voir les cours accessibles
              </div>
            </div>
          ) : (
            <ExplorationGraph
              completed={completed}
              homeUniversite={homeUniversite}
              program={program}
              onNodeClick={setSelectedCourse}
            />
          )}
        </div>
        <DetailPanel
          course={selectedCourse}
          onClose={() => setSelectedCourse(null)}
        />
      </div>
    </div>
  )
}
