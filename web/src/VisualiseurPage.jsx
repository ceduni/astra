import { useEffect, useRef, useState, useCallback } from 'react'
import GraphCanvas from './GraphCanvas'
import { SearchSection, CompletedSection } from './shared'

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
          {course.hors_perimetre && <span style={{ color: '#c00' }}>Hors périmètre</span>}
        </div>
        {course.tags && course.tags.length > 0 && (
          <div className="detail-tags">
            {course.tags.map(tag => <span key={tag} className="tag-pill">{tag}</span>)}
          </div>
        )}
        {course.description && <p className="detail-description">{course.description}</p>}
        {course.requirement_text && <p className="detail-req">{course.requirement_text}</p>}
      </div>
    </div>
  )
}

// ── Visualiseur page ───────────────────────────────────────────────────────────

export default function VisualiseurPage({
  completed, onAddCompleted, onRemoveCompleted,
  chainsToLoad, onAddChain, onRemoveChain,
  resetKey, onResetGraph,
  selectedCourse, onSelectCourse,
}) {
  const [sidebarWidth, setSidebarWidth] = useState(300)
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
      setSidebarWidth(Math.max(200, Math.min(520, dragStartWidth.current + (e.clientX - dragStartX.current))))
    }
    function onUp() { isDragging.current = false }
    document.addEventListener('mousemove', onMove)
    document.addEventListener('mouseup', onUp)
    return () => {
      document.removeEventListener('mousemove', onMove)
      document.removeEventListener('mouseup', onUp)
    }
  }, [])

  function handleVisualize(course) {
    onSelectCourse(course)
    onAddChain(course.sigle)
  }

  function handleNodeClick(course) {
    onSelectCourse(course)
    onAddChain(course.sigle)
  }

  return (
    <div className="vis-shell">
      {/* Sidebar */}
      <aside className="vis-sidebar" style={{ width: collapsed ? 0 : sidebarWidth }}>
        <div className="vis-sidebar-inner">
          <SearchSection
            onAddCompleted={onAddCompleted}
            onVisualize={handleVisualize}
            completed={completed}
          />
          <CompletedSection
            completed={completed}
            onRemove={onRemoveCompleted}
            onSelect={handleVisualize}
          />
        </div>
        <div className="vis-sidebar-footer">
          <button className="btn-reset" onClick={onResetGraph}>
            Réinitialiser le graphe
          </button>
        </div>
      </aside>

      {/* Resize handle */}
      <div className="resize-handle" onMouseDown={onDividerMouseDown}>
        <button
          className="collapse-btn"
          onClick={() => setCollapsed(c => !c)}
          title={collapsed ? 'Ouvrir le panneau' : 'Fermer le panneau'}
        >
          {collapsed ? '›' : '‹'}
        </button>
      </div>

      {/* Canvas + detail */}
      <div className="vis-main">
        <div className="graph-canvas-wrapper">
          <GraphCanvas
            completed={completed}
            chainsToLoad={chainsToLoad}
            resetKey={resetKey}
            onNodeClick={handleNodeClick}
            onRemoveChain={onRemoveChain}
          />
        </div>
        <DetailPanel
          course={selectedCourse}
          completed={completed}
          onClose={() => onSelectCourse(null)}
          onAdd={onAddCompleted}
          onRemove={onRemoveCompleted}
        />
      </div>
    </div>
  )
}
