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

// ── Confidence bar ─────────────────────────────────────────────────────────────

function ConfBar({ value }) {
  if (value == null) return <span style={{ color: '#ccc', fontSize: 11 }}>—</span>
  const pct = Math.round(value * 100)
  const fill = pct >= 60 ? '#2a9d4e' : pct >= 40 ? '#f0a500' : '#ed1b2f'
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
      <div style={{ width: 40, height: 4, background: '#eee', borderRadius: 3, overflow: 'hidden' }}>
        <div style={{ width: `${pct}%`, height: '100%', background: fill }} />
      </div>
      <span style={{ fontSize: 10, color: '#777' }}>{pct}%</span>
    </div>
  )
}

// ── Detail panel ───────────────────────────────────────────────────────────────

function DetailPanel({ course, substitutions, onSubstitute, onRestore, onClose }) {
  const [equivs, setEquivs] = useState([])
  const [loadingEquivs, setLoadingEquivs] = useState(false)

  // course.sigle is always the original program course sigle
  const originalSigle = course?.sigle
  const currentSub = course?.substitution  // set when node is currently substituted
  const isSubstituted = !!currentSub

  useEffect(() => {
    if (!originalSigle) { setEquivs([]); return }
    setLoadingEquivs(true)
    fetch(`${API}/equivalences?q=${encodeURIComponent(originalSigle)}&limit=100`)
      .then(r => r.json())
      .then(data => {
        const exact = (Array.isArray(data) ? data : [])
          .filter(r => r.sigle_a === originalSigle || r.sigle_b === originalSigle)
          .map(r => {
            const isA = r.sigle_a === originalSigle
            return {
              sigle:      isA ? r.sigle_b      : r.sigle_a,
              titre:      isA ? r.titre_b      : r.titre_a,
              universite: isA ? r.universite_b : r.universite_a,
              source:     r.source,
              confidence: r.confidence,
            }
          })
        setEquivs(exact)
      })
      .catch(() => setEquivs([]))
      .finally(() => setLoadingEquivs(false))
  }, [originalSigle])

  if (!course) return <div className="detail-panel" />

  return (
    <div className="detail-panel open" data-uni={course.universite} style={{ maxHeight: 420 }}>
      <div className="detail-inner">
        <div className="detail-top">
          <div className="detail-title-block">
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
              <span className="sigle">{originalSigle}</span>
              {isSubstituted && (
                <span style={{
                  fontSize: 10, fontWeight: 700, background: '#ede9f8', color: '#7c5cbf',
                  padding: '2px 7px', borderRadius: 4, whiteSpace: 'nowrap',
                }}>
                  remplacé par {currentSub.sigle}
                </span>
              )}
            </div>
            <h3>{course.titre || '(sans titre)'}</h3>
          </div>
          <button className="btn-dismiss" onClick={onClose} title="Fermer">×</button>
        </div>

        <div className="detail-meta">
          <span>{course.universite}</span>
          {course.credits ? <span>{course.credits} crédits</span> : null}
          {course.niveau  ? <span>Niveau {course.niveau}</span>   : null}
        </div>

        {isSubstituted && (
          <div style={{
            margin: '6px 0 8px', padding: '6px 10px', borderRadius: 6,
            background: '#ede9f8', border: '1px solid #d6ccf0',
            display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 8,
          }}>
            <div style={{ fontSize: 10.5, color: '#7c5cbf', minWidth: 0 }}>
              <strong style={{ fontFamily: 'monospace' }}>{currentSub.sigle}</strong>
              <span style={{ color: '#9c85c9', marginLeft: 5 }}>({currentSub.universite})</span>
              <span style={{ marginLeft: 5 }}>remplace ce cours</span>
            </div>
            <button
              onClick={() => onRestore(originalSigle)}
              style={{
                background: '#7c5cbf', color: '#fff', border: 'none',
                borderRadius: 4, padding: '3px 9px', fontSize: 10,
                cursor: 'pointer', fontWeight: 700, flexShrink: 0,
              }}
            >
              Restaurer
            </button>
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
              {equivs.map((eq, i) => {
                const isActive = isSubstituted
                  && currentSub.sigle === eq.sigle
                  && currentSub.universite === eq.universite
                return (
                  <div key={i} style={{
                    background: isActive ? '#ede9f8' : '#f9f9f9',
                    border: isActive ? '1.5px dashed #7c5cbf' : '1.5px solid transparent',
                    borderRadius: 6, padding: '5px 9px', fontSize: 11,
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
                        textOverflow: 'ellipsis', whiteSpace: 'nowrap', maxWidth: 200,
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
                      {isActive ? (
                        <button
                          onClick={() => onRestore(originalSigle)}
                          style={{
                            background: '#7c5cbf', color: '#fff', border: 'none',
                            borderRadius: 4, padding: '2px 8px', fontSize: 9,
                            cursor: 'pointer', fontWeight: 700, marginTop: 1,
                          }}
                        >
                          Restaurer
                        </button>
                      ) : (
                        <button
                          onClick={() => onSubstitute(originalSigle, eq)}
                          style={{
                            background: '#f3f0ff', color: '#7c5cbf',
                            border: '1px solid #c9bcef', borderRadius: 4,
                            padding: '2px 8px', fontSize: 9,
                            cursor: 'pointer', fontWeight: 700, marginTop: 1,
                          }}
                        >
                          Substituer
                        </button>
                      )}
                    </div>
                  </div>
                )
              })}
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
  const [snapshot, setSnapshot] = useState(null)
  const [substitutions, setSubstitutions] = useState(new Map())

  useEffect(() => { setProgram(null); setSnapshot(null) }, [homeUniversite])
  useEffect(() => { setSnapshot(null) }, [program])
  // Reset substitutions whenever a new snapshot is generated
  useEffect(() => { setSubstitutions(new Map()) }, [snapshot])

  function handleCalculer() {
    if (!homeUniversite || !program) return
    setSelectedCourse(null)
    setSnapshot({ completedSigles: completed.map(c => c.sigle), homeUniversite, program })
  }

  function handleSubstitute(originalSigle, equivObj) {
    setSubstitutions(prev => new Map(prev).set(originalSigle, equivObj))
  }

  function handleRestore(originalSigle) {
    setSubstitutions(prev => { const m = new Map(prev); m.delete(originalSigle); return m })
  }

  // Derive the panel's course data from selectedCourse + live substitutions
  // so the panel immediately reflects substitute/restore without requiring a re-click
  const activeCourse = selectedCourse
    ? (() => {
        const sub = substitutions.get(selectedCourse.sigle)
        if (sub) return { ...selectedCourse, substitution: { ...sub, originalSigle: selectedCourse.sigle } }
        const { substitution: _, ...rest } = selectedCourse
        return rest
      })()
    : null

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

        <div className="vis-sidebar-footer">
          <button
            className="btn-calculer"
            onClick={handleCalculer}
            disabled={!homeUniversite || !program}
          >
            Visualiser le programme
          </button>
        </div>
      </aside>

      {/* Main */}
      <div className="vis-main">
        <div className="graph-canvas-wrapper">
          {!snapshot ? (
            <div className="graph-empty">
              <div className="graph-empty-icon">⬡</div>
              <div className="graph-empty-text">
                {!homeUniversite
                  ? 'Sélectionne ton université et ton programme'
                  : !program
                  ? 'Sélectionne ton programme'
                  : 'Ajoute tes cours complétés puis clique sur Visualiser'}
              </div>
            </div>
          ) : (
            <ExplorationGraph
              snapshot={snapshot}
              substitutions={substitutions}
              onNodeClick={setSelectedCourse}
            />
          )}
        </div>
        <DetailPanel
          course={activeCourse}
          substitutions={substitutions}
          onSubstitute={handleSubstitute}
          onRestore={handleRestore}
          onClose={() => setSelectedCourse(null)}
        />
      </div>
    </div>
  )
}
