import { useEffect, useRef, useState } from 'react'
import { API, CompletedSection, useDebounce, useUniversities } from './shared'
import { UNI_COLORS } from './graphShared'
import MindMapView from './MindMapView'

function hexWithOpacity(hex, opacity) {
  const r = parseInt(hex.slice(1, 3), 16)
  const g = parseInt(hex.slice(3, 5), 16)
  const b = parseInt(hex.slice(5, 7), 16)
  return `rgba(${r},${g},${b},${opacity})`
}

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
    <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginTop: 4 }}>
      <div style={{ width: 40, height: 4, background: '#eee', borderRadius: 3, overflow: 'hidden' }}>
        <div style={{ width: `${pct}%`, height: '100%', background: fill }} />
      </div>
      <span style={{ fontSize: 10, color: '#777' }}>{pct}%</span>
    </div>
  )
}

// ── Prerequisite tree renderer ─────────────────────────────────────────────────

function renderPrereqNode(node, completedSet, depth = 0) {
  if (!node) return null

  if (node.kind === 'course') {
    const done = completedSet.has(node.sigle)
    return (
      <div key={node.sigle} style={{
        display: 'flex', alignItems: 'center', gap: 6,
        padding: '2px 0', paddingLeft: depth * 10,
      }}>
        <span style={{
          fontFamily: 'monospace', fontSize: 10.5, fontWeight: 700,
          background: done ? '#f0faf3' : '#f3f4f6',
          color: done ? '#2a9d4e' : '#374151',
          border: `1px solid ${done ? '#86efac' : '#e5e7eb'}`,
          padding: '1px 6px', borderRadius: 4, flexShrink: 0,
        }}>
          {node.sigle}{done ? ' ✓' : ''}
        </span>
        <span style={{
          fontSize: 10.5, color: '#6b7280',
          overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
        }}>
          {node.data?.titre}
        </span>
      </div>
    )
  }

  if (node.kind === 'group') {
    const label = node.groupType === 'AND' ? 'Tous les suivants :' : "L'un des suivants :"
    return (
      <div key={`group_${depth}_${node.groupType}`} style={{ paddingLeft: depth * 10 }}>
        <div style={{ fontSize: 9.5, color: '#9ca3af', fontStyle: 'italic', margin: '2px 0' }}>
          {label}
        </div>
        {node.children.map((child, i) => (
          <div key={i}>{renderPrereqNode(child, completedSet, depth + 1)}</div>
        ))}
      </div>
    )
  }

  return null
}

// ── Detail panel ───────────────────────────────────────────────────────────────

const UNLOCK_PREVIEW = 3

function DetailPanel({ course, completed, substitutions, onSubstitute, onRestore, onClose }) {
  const [equivs, setEquivs] = useState([])
  const [loadingEquivs, setLoadingEquivs] = useState(false)
  const [showAllUnlocks, setShowAllUnlocks] = useState(false)

  const completedSet = new Set((completed || []).map(c => c.sigle))
  const originalSigle = course?.sigle
  const currentSub = course?.substitution
  const isSubstituted = !!currentSub
  const subUniColor = isSubstituted ? (UNI_COLORS[currentSub.universite] || '#7c5cbf') : null

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
          .sort((a, b) => {
            if (a.source === 'official' && b.source !== 'official') return -1
            if (b.source === 'official' && a.source !== 'official') return 1
            return (b.confidence ?? 0) - (a.confidence ?? 0)
          })
        setEquivs(exact)
      })
      .catch(() => setEquivs([]))
      .finally(() => setLoadingEquivs(false))
  }, [originalSigle])

  useEffect(() => { setShowAllUnlocks(false) }, [originalSigle])

  if (!course) return <div className="detail-panel" />

  const STATUS_BADGE = {
    completed: { label: 'COMPLÉTÉ',   bg: '#f0faf3', color: '#2a9d4e' },
    available: { label: 'DISPONIBLE', bg: '#eff6ff', color: '#2563eb' },
    locked:    { label: 'VERROUILLÉ', bg: '#f3f4f6', color: '#6b7280' },
  }
  const statusBadge = course.status ? STATUS_BADGE[course.status] : null

  const prereqs  = course.prereqs  || []
  const unlocked = course.unlocked || []
  const visibleUnlocks = showAllUnlocks ? unlocked : unlocked.slice(0, UNLOCK_PREVIEW)
  const hiddenCount = unlocked.length - UNLOCK_PREVIEW

  return (
    <div className="detail-panel open" data-uni={course.universite}>
      <div className="detail-inner" style={{ overflowY: 'auto' }}>

        {/* Header */}
        <div className="detail-top">
          <div className="detail-title-block">
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
              <span className="sigle">{originalSigle}</span>
              {statusBadge && (
                <span style={{
                  fontSize: 9, fontWeight: 700, padding: '2px 7px', borderRadius: 4,
                  background: statusBadge.bg, color: statusBadge.color, letterSpacing: '0.05em',
                }}>
                  {statusBadge.label}
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

        {/* Active substitution banner — uses university color */}
        {isSubstituted && (
          <div style={{
            margin: '10px 0 14px',
            padding: '10px 12px',
            borderRadius: 8,
            background: hexWithOpacity(subUniColor, 0.06),
            border: `1.5px solid ${hexWithOpacity(subUniColor, 0.30)}`,
            display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 10,
          }}>
            <div>
              <div style={{
                fontSize: 9, fontWeight: 700, color: subUniColor,
                textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: 4,
              }}>
                Remplacé par
              </div>
              <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                <span className="uni-dot" data-uni={currentSub.universite} />
                <strong style={{ fontFamily: 'monospace', fontSize: 13, color: '#111' }}>
                  {currentSub.sigle}
                </strong>
                <span style={{ fontSize: 11, color: subUniColor, fontWeight: 600 }}>
                  {currentSub.universite}
                </span>
              </div>
            </div>
            <button
              onClick={() => onRestore(originalSigle)}
              style={{
                background: subUniColor, color: '#fff', border: 'none',
                borderRadius: 6, padding: '7px 16px',
                fontSize: 12, fontWeight: 600, cursor: 'pointer', flexShrink: 0,
              }}
            >
              Restaurer
            </button>
          </div>
        )}

        {course.description && (
          <p className="detail-description">{course.description}</p>
        )}

        {/* ── Équivalences — first-class section ──────────────────────────── */}
        <div style={{ marginBottom: 14 }}>
          <div style={{
            fontSize: 10, fontWeight: 700, color: '#aaa',
            textTransform: 'uppercase', letterSpacing: '0.07em', marginBottom: 8,
          }}>
            Équivalences
          </div>

          {loadingEquivs && <p style={{ fontSize: 11, color: '#bbb', margin: 0 }}>Chargement…</p>}

          {!loadingEquivs && equivs.length === 0 && (
            <p style={{ fontSize: 11, color: '#ccc', margin: 0 }}>Aucune équivalence connue.</p>
          )}

          {!loadingEquivs && equivs.length > 0 && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 7 }}>
              {equivs.map((eq, i) => {
                const eqUniColor = UNI_COLORS[eq.universite] || '#888'
                const isActive = isSubstituted
                  && currentSub.sigle === eq.sigle
                  && currentSub.universite === eq.universite
                return (
                  <div key={i} style={{
                    background: isActive ? hexWithOpacity(eqUniColor, 0.05) : '#f9f9f9',
                    border: isActive
                      ? `1.5px dashed ${hexWithOpacity(eqUniColor, 0.50)}`
                      : '1.5px solid #eee',
                    borderRadius: 8,
                    padding: '9px 11px',
                  }}>
                    <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: 10 }}>
                      <div style={{ minWidth: 0, flex: 1 }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: 5, marginBottom: 3, flexWrap: 'wrap' }}>
                          <span className="uni-dot" data-uni={eq.universite} />
                          <strong style={{ fontFamily: 'monospace', fontSize: 11 }}>{eq.sigle}</strong>
                          <span style={{ color: eqUniColor, fontSize: 10, fontWeight: 600 }}>{eq.universite}</span>
                          <span style={{
                            fontSize: 9, fontWeight: 700, padding: '1px 5px', borderRadius: 3,
                            background: eq.source === 'official' ? '#e6f4ea' : '#fff8e1',
                            color: eq.source === 'official' ? '#1e7e34' : '#8a6d00',
                          }}>
                            {eq.source === 'official' ? 'OFFICIELLE' : 'SIMILAIRE'}
                          </span>
                        </div>
                        <div style={{
                          fontSize: 10.5, color: '#666',
                          overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
                        }}>
                          {eq.titre}
                        </div>
                        {eq.source !== 'official' && <ConfBar value={eq.confidence} />}
                      </div>

                      <div style={{ flexShrink: 0, paddingTop: 1 }}>
                        {isActive ? (
                          <button
                            onClick={() => onRestore(originalSigle)}
                            style={{
                              background: eqUniColor, color: '#fff', border: 'none',
                              borderRadius: 6, padding: '6px 12px',
                              fontSize: 11, fontWeight: 600, cursor: 'pointer',
                            }}
                          >
                            Restaurer
                          </button>
                        ) : (
                          <button
                            onClick={() => onSubstitute(originalSigle, eq)}
                            style={{
                              background: hexWithOpacity(eqUniColor, 0.08),
                              color: eqUniColor,
                              border: `1px solid ${hexWithOpacity(eqUniColor, 0.30)}`,
                              borderRadius: 6,
                              padding: '6px 12px', fontSize: 11,
                              fontWeight: 600, cursor: 'pointer',
                              whiteSpace: 'nowrap',
                            }}
                          >
                            Substituer →
                          </button>
                        )}
                      </div>
                    </div>
                  </div>
                )
              })}
            </div>
          )}
        </div>

        {/* ── Prérequis ────────────────────────────────────────────────────── */}
        <div style={{ marginBottom: 12 }}>
          <div style={{
            fontSize: 10, fontWeight: 700, color: '#aaa',
            textTransform: 'uppercase', letterSpacing: '0.07em', marginBottom: 6,
          }}>
            Prérequis
          </div>
          {prereqs.length === 0 ? (
            <p style={{ fontSize: 11, color: '#ccc', margin: 0 }}>Aucun prérequis.</p>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 1 }}>
              {prereqs.map((node, i) => <div key={i}>{renderPrereqNode(node, completedSet, 0)}</div>)}
            </div>
          )}
        </div>

        {/* ── Ce cours débloque ────────────────────────────────────────────── */}
        {course.status !== 'completed' && (
          <div style={{ marginBottom: 12 }}>
            <div style={{
              fontSize: 10, fontWeight: 700, color: '#aaa',
              textTransform: 'uppercase', letterSpacing: '0.07em', marginBottom: 6,
            }}>
              Ce cours débloque
            </div>
            {unlocked.length === 0 ? (
              <p style={{ fontSize: 11, color: '#ccc', margin: 0 }}>Aucun cours supplémentaire.</p>
            ) : (
              <>
                <div style={{ display: 'flex', flexWrap: 'wrap', gap: 5 }}>
                  {visibleUnlocks.map(u => (
                    <div key={u.sigle} style={{
                      background: '#f0f9ff', border: '1px solid #bae6fd',
                      borderRadius: 5, padding: '3px 8px',
                      display: 'flex', flexDirection: 'column', gap: 1,
                    }}>
                      <span style={{ fontFamily: 'monospace', fontSize: 10.5, fontWeight: 700, color: '#0369a1' }}>
                        {u.sigle}
                      </span>
                      {u.titre && (
                        <span style={{
                          fontSize: 9.5, color: '#64748b',
                          maxWidth: 140, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
                        }}>
                          {u.titre}
                        </span>
                      )}
                    </div>
                  ))}
                </div>
                {!showAllUnlocks && hiddenCount > 0 && (
                  <button
                    onClick={() => setShowAllUnlocks(true)}
                    style={{
                      marginTop: 5, background: 'none', border: 'none',
                      color: '#0369a1', fontSize: 11, cursor: 'pointer',
                      padding: 0, fontWeight: 600,
                    }}
                  >
                    Voir {hiddenCount} de plus ▾
                  </button>
                )}
              </>
            )}
          </div>
        )}

      </div>
    </div>
  )
}

// ── Compact search (same fetch/debounce logic as SearchSection, compact shell) ─

function CompactSearch({ onAddCompleted, completed }) {
  const [query, setQuery] = useState('')
  const [results, setResults] = useState([])
  const [loading, setLoading] = useState(false)
  const [open, setOpen] = useState(false)
  const debouncedQuery = useDebounce(query, 300)
  const wrapRef = useRef(null)

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

  useEffect(() => {
    function onDocClick(e) {
      if (wrapRef.current && !wrapRef.current.contains(e.target)) setOpen(false)
    }
    document.addEventListener('mousedown', onDocClick)
    return () => document.removeEventListener('mousedown', onDocClick)
  }, [])

  const showDropdown = open && (loading || results.length > 0 || debouncedQuery.length >= 2)

  return (
    <div className="compact-search" ref={wrapRef}>
      <input
        type="search"
        className="search-input"
        placeholder="Rechercher un cours…"
        value={query}
        onFocus={() => setOpen(true)}
        onChange={e => { setQuery(e.target.value); setOpen(true) }}
      />
      {showDropdown && (
        <div className="compact-search-results result-list">
          {loading && <p className="hint" style={{ padding: '0.4rem 0.65rem' }}>Recherche…</p>}
          {!loading && results.length === 0 && (
            <p className="hint" style={{ padding: '0.4rem 0.65rem' }}>Aucun résultat.</p>
          )}
          {!loading && results.map(course => {
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
                    onClick={() => onAddCompleted(course)}
                    disabled={done}
                    title={done ? 'Déjà ajouté' : 'Ajouter à mon parcours'}
                  >✓</button>
                </div>
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}

// ── Completed courses — compact popover trigger around the existing section ────

function CompletedToggle({ completed, onRemove }) {
  const [open, setOpen] = useState(false)
  const wrapRef = useRef(null)

  useEffect(() => {
    function onDocClick(e) {
      if (wrapRef.current && !wrapRef.current.contains(e.target)) setOpen(false)
    }
    document.addEventListener('mousedown', onDocClick)
    return () => document.removeEventListener('mousedown', onDocClick)
  }, [])

  return (
    <div className="completed-toggle-wrap" ref={wrapRef}>
      <button className="completed-toggle-btn" onClick={() => setOpen(o => !o)}>
        Complétés {completed.length > 0 ? `(${completed.length})` : ''}
      </button>
      {open && (
        <div className="completed-popover">
          <CompletedSection completed={completed} onRemove={onRemove} />
        </div>
      )}
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
  const [orientation, setOrientation] = useState(null)
  const [selectedCourse, setSelectedCourse] = useState(null)
  const [snapshot, setSnapshot] = useState(null)
  const [substitutions, setSubstitutions] = useState(new Map())

  const selectedProgramData = programs.find(p => p.id === program)
  const hasOrientations = !!selectedProgramData?.orientations

  useEffect(() => { setProgram(null); setOrientation(null); setSnapshot(null) }, [homeUniversite])
  useEffect(() => { setOrientation(null); setSnapshot(null) }, [program])
  useEffect(() => { setSubstitutions(new Map()) }, [snapshot])

  function handleCalculer() {
    if (!homeUniversite || !program) return
    setSelectedCourse(null)
    const orientationLabel = selectedProgramData?.orientations?.find(o => o.id === orientation)?.label ?? null
    setSnapshot({
      completedSigles: completed.map(c => c.sigle),
      homeUniversite,
      program,
      programLabel: programLabel(program),
      orientationLabel,
      orientation: orientation ?? null,
    })
  }

  function handleSubstitute(originalSigle, equivObj) {
    setSubstitutions(prev => new Map(prev).set(originalSigle, equivObj))
  }

  function handleRestore(originalSigle) {
    setSubstitutions(prev => { const m = new Map(prev); m.delete(originalSigle); return m })
  }

  const activeCourse = selectedCourse
    ? (() => {
        const sub = substitutions.get(selectedCourse.sigle)
        if (sub) return { ...selectedCourse, substitution: { ...sub, originalSigle: selectedCourse.sigle } }
        const { substitution: _, ...rest } = selectedCourse
        return rest
      })()
    : null

  return (
    <div className="explore-shell">
      {/* Top bar */}
      <div className="explore-topbar">
        <div className="explore-topbar-row">
          <div className="explore-filter-group">
            <span className="explore-filter-label">Université</span>
            <div className="uni-selector-inline">
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
            <div className="explore-filter-group">
              <span className="explore-filter-label">Programme</span>
              <div className="uni-selector-inline">
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

          {hasOrientations && (
            <div className="explore-filter-group">
              <span className="explore-filter-label">Orientation</span>
              <div className="uni-selector-inline">
                {selectedProgramData.orientations.map(o => (
                  <button
                    key={o.id}
                    className={`uni-pill${orientation === o.id ? ' active' : ''}`}
                    onClick={() => setOrientation(prev => prev === o.id ? null : o.id)}
                  >
                    {o.label}
                  </button>
                ))}
              </div>
            </div>
          )}

          <button
            className="btn-calculer explore-calculer"
            onClick={handleCalculer}
            disabled={!homeUniversite || !program || (hasOrientations && !orientation)}
          >
            Visualiser le programme
          </button>
        </div>

        <div className="explore-topbar-row">
          <CompactSearch onAddCompleted={onAddCompleted} completed={completed} />
          <CompletedToggle completed={completed} onRemove={onRemoveCompleted} />
        </div>
      </div>

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
                  : hasOrientations && !orientation
                  ? 'Sélectionne ton orientation'
                  : 'Ajoute tes cours complétés puis clique sur Visualiser'}
              </div>
            </div>
          ) : (
            <MindMapView
              snapshot={snapshot}
              onNodeClick={setSelectedCourse}
              substitutions={substitutions}
            />
          )}
        </div>
        <DetailPanel
          course={activeCourse}
          completed={completed}
          substitutions={substitutions}
          onSubstitute={handleSubstitute}
          onRestore={handleRestore}
          onClose={() => setSelectedCourse(null)}
        />
      </div>
    </div>
  )
}
