import { useEffect, useState } from 'react'
import { UNI_COLORS } from './graphShared'

const API = '/api'

// ── Availability engine ────────────────────────────────────────────────────────
// Edge direction in program-graph: source = course, target = prerequisite node.
// outgoing[course] = list of prerequisite node IDs (courses or groups).

function buildOutgoing(edges) {
  const out = {}
  edges.forEach(e => {
    if (e.relation_type === 'equivalent') return
    if (!out[e.source]) out[e.source] = []
    out[e.source].push(e.target)
  })
  return out
}

function isSatisfied(nodeId, nodeById, outgoing, completedSet) {
  const node = nodeById[nodeId]
  if (!node) return true
  if (node.node_type === 'course') return completedSet.has(nodeId)
  if (node.node_type === 'group') {
    const children = outgoing[nodeId] || []
    if (children.length === 0) return true
    return node.data.type === 'AND'
      ? children.every(c => isSatisfied(c, nodeById, outgoing, completedSet))
      : children.some(c => isSatisfied(c, nodeById, outgoing, completedSet))
  }
  return false
}

function computeAvailability(rawData, completedSigles) {
  const completedSet = new Set(completedSigles)
  const nodeById = {}
  rawData.nodes.forEach(n => { nodeById[n.id] = n })
  const outgoing = buildOutgoing(rawData.edges)

  return rawData.program_sigles.filter(sigle => {
    if (completedSet.has(sigle)) return false
    const prereqs = outgoing[sigle] || []
    return prereqs.every(t => isSatisfied(t, nodeById, outgoing, completedSet))
  })
}

// ── CourseCard ─────────────────────────────────────────────────────────────────

function CourseCard({ data, onClick }) {
  const color = UNI_COLORS[data.universite] || '#aaa'
  return (
    <div
      onClick={() => onClick?.(data)}
      style={{
        background: '#fff',
        border: '1.5px solid #e5e7eb',
        borderLeft: `3px solid ${color}`,
        borderRadius: 7,
        padding: '7px 10px',
        cursor: 'pointer',
        width: 158,
        flexShrink: 0,
      }}
    >
      <div style={{ fontSize: 11, fontWeight: 700, fontFamily: 'monospace', color: '#222' }}>
        {data.sigle}
      </div>
      <div style={{
        fontSize: 10, color: '#777', marginTop: 2, lineHeight: 1.3,
        overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
      }}>
        {data.titre || '—'}
      </div>
    </div>
  )
}

// ── SegmentCluster ─────────────────────────────────────────────────────────────

function SegmentCluster({ segment, nodeById, completedSet, availableSet, onCourseClick }) {
  const isLibre = segment.type === 'libre'
  const availableCourses = isLibre ? [] : (segment.cours || []).filter(s => availableSet.has(s) && nodeById[s])

  if (!isLibre && availableCourses.length === 0) return null

  const completedInSeg = (segment.cours || []).filter(s => completedSet.has(s))
  // TODO V2: courses with null credits in Neo4j default to 3cr — may cause inaccurate progress bars
  const completedCredits = completedInSeg.reduce((sum, s) => {
    return sum + (nodeById[s]?.data?.credits ?? 3)
  }, 0)
  const maxCr = segment.credits_max

  const typeStyle = segment.type === 'obligatoire'
    ? { bg: '#e8f0fe', text: '#1a47a8', label: 'OBLIGATOIRE' }
    : segment.type === 'libre'
    ? { bg: '#f3f4f6', text: '#888', label: 'LIBRE' }
    : { bg: '#fff4e6', text: '#b45309', label: 'OPTION' }

  return (
    <div style={{
      background: '#fff',
      border: '1px solid #e5e7eb',
      borderRadius: 10,
      padding: '12px 14px',
      marginBottom: 10,
    }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8 }}>
        <span style={{ fontSize: 12, fontWeight: 700, color: '#222' }}>{segment.label}</span>
        <span style={{
          fontSize: 9, fontWeight: 700, padding: '2px 6px', borderRadius: 4,
          background: typeStyle.bg, color: typeStyle.text, letterSpacing: '0.05em',
          flexShrink: 0,
        }}>
          {typeStyle.label}
        </span>
        {maxCr != null && (
          <span style={{ fontSize: 10, color: '#bbb', marginLeft: 'auto', whiteSpace: 'nowrap' }}>
            {completedCredits} / {maxCr} cr
          </span>
        )}
      </div>

      {!isLibre && maxCr != null && (
        <div style={{ height: 3, background: '#eee', borderRadius: 2, marginBottom: 10, overflow: 'hidden' }}>
          <div style={{
            height: '100%',
            width: `${Math.min(100, (completedCredits / maxCr) * 100)}%`,
            background: segment.type === 'obligatoire' ? '#2a9d4e' : '#f0a500',
            borderRadius: 2,
          }} />
        </div>
      )}

      {isLibre ? (
        <p style={{ fontSize: 11, color: '#999', margin: 0, fontStyle: 'italic' }}>
          {segment.note || `${segment.credits_min}–${segment.credits_max} crédits au choix`}
        </p>
      ) : (
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
          {availableCourses.map(sigle => {
            const node = nodeById[sigle]
            if (!node) return null
            return <CourseCard key={sigle} data={node.data} onClick={onCourseClick} />
          })}
        </div>
      )}
    </div>
  )
}

// ── WavePanel ──────────────────────────────────────────────────────────────────

function WavePanel({ title, segments, nodeById, completedSet, availableSet, onCourseClick }) {
  const visible = segments.filter(seg =>
    seg.type === 'libre' || (seg.cours || []).some(s => availableSet.has(s) && nodeById[s])
  )

  if (visible.length === 0) {
    return (
      <div style={{ flexShrink: 0, width: 360 }}>
        <div style={{
          fontSize: 11, fontWeight: 700, color: '#aaa', textTransform: 'uppercase',
          letterSpacing: '0.07em', marginBottom: 14,
        }}>
          {title}
        </div>
        <p style={{ fontSize: 12, color: '#ccc' }}>Aucun cours disponible.</p>
      </div>
    )
  }

  const rows = []
  let lastGroup = '__UNSET__'
  for (const seg of visible) {
    const gl = seg.group_label
    if (gl !== lastGroup) {
      lastGroup = gl
      if (gl) {
        rows.push(
          <div key={`grp-${gl}`} style={{
            fontSize: 9.5, fontWeight: 700, color: '#bbb',
            textTransform: 'uppercase', letterSpacing: '0.08em',
            marginTop: rows.length > 0 ? 6 : 0, marginBottom: 6,
          }}>
            {gl}
          </div>
        )
      }
    }
    rows.push(
      <SegmentCluster
        key={seg.id}
        segment={seg}
        nodeById={nodeById}
        completedSet={completedSet}
        availableSet={availableSet}
        onCourseClick={onCourseClick}
      />
    )
  }

  return (
    <div style={{ flexShrink: 0, width: 360 }}>
      <div style={{
        fontSize: 11, fontWeight: 700, color: '#aaa', textTransform: 'uppercase',
        letterSpacing: '0.07em', marginBottom: 14,
      }}>
        {title}
      </div>
      {rows}
    </div>
  )
}

// ── Connector arrow ────────────────────────────────────────────────────────────

function Arrow() {
  return (
    <div style={{ flexShrink: 0, paddingTop: 52, color: '#d1d5db', fontSize: 20, userSelect: 'none' }}>
      →
    </div>
  )
}

// ── Main component ─────────────────────────────────────────────────────────────

export default function RoadmapView({ snapshot, onNodeClick }) {
  const [status, setStatus] = useState('idle')
  const [rawData, setRawData] = useState(null)
  const [showNext, setShowNext] = useState(false)

  useEffect(() => {
    if (!snapshot) { setRawData(null); setStatus('idle'); return }
    setStatus('loading')
    setRawData(null)
    setShowNext(false)

    fetch(`${API}/courses/program-graph`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        uni: snapshot.homeUniversite,
        program: snapshot.program,
        orientation: snapshot.orientation ?? null,
        completed_sigles: snapshot.completedSigles,
      }),
    })
      .then(r => { if (!r.ok) throw new Error(r.status); return r.json() })
      .then(data => { setRawData(data); setStatus('ready') })
      .catch(() => setStatus('error'))
  }, [snapshot])

  if (status === 'loading') {
    return (
      <div className="graph-empty">
        <div className="graph-empty-text">Chargement du programme…</div>
      </div>
    )
  }
  if (status === 'error') {
    return (
      <div className="graph-empty">
        <div className="graph-empty-text" style={{ color: '#c00' }}>Erreur de chargement.</div>
      </div>
    )
  }
  if (!rawData) return null

  const completedSet = new Set(snapshot.completedSigles)
  const nodeById = {}
  rawData.nodes.forEach(n => { nodeById[n.id] = n })

  const availableSigles = computeAvailability(rawData, snapshot.completedSigles)
  const availableSet = new Set(availableSigles)

  const nextWaveSigles = showNext
    ? computeAvailability(rawData, [...snapshot.completedSigles, ...availableSigles])
    : []
  const nextWaveSet = new Set(nextWaveSigles)

  const segments = rawData.segments || []

  return (
    <div style={{
      position: 'absolute', inset: 0,
      background: '#f7f8fb',
      overflowX: 'auto', overflowY: 'auto',
    }}>
      <div style={{
        display: 'flex', flexDirection: 'row', alignItems: 'flex-start',
        padding: '28px 32px', gap: 20, minWidth: 'max-content',
      }}>

        {/* Completed anchor */}
        <div style={{ flexShrink: 0, width: 148, paddingTop: 30 }}>
          <div style={{
            background: '#f0faf3', border: '2px solid #2a9d4e',
            borderRadius: 14, padding: '16px', textAlign: 'center',
          }}>
            <div style={{ fontSize: 24, lineHeight: 1, color: '#2a9d4e' }}>✓</div>
            <div style={{ fontSize: 14, fontWeight: 700, color: '#2a9d4e', marginTop: 6 }}>
              {snapshot.completedSigles.length} cours
            </div>
            <div style={{ fontSize: 10, color: '#5a8a6a', marginTop: 2 }}>complétés</div>
          </div>
        </div>

        <Arrow />

        {/* Available Now */}
        <WavePanel
          title="Disponible maintenant"
          segments={segments}
          nodeById={nodeById}
          completedSet={completedSet}
          availableSet={availableSet}
          onCourseClick={onNodeClick}
        />

        <Arrow />

        {/* Et ensuite */}
        {!showNext ? (
          <div style={{ flexShrink: 0, width: 148, paddingTop: 30 }}>
            <button
              onClick={() => setShowNext(true)}
              style={{
                width: '100%', background: '#fff',
                border: '2px dashed #d1d5db', borderRadius: 14,
                padding: '20px 16px', cursor: 'pointer', textAlign: 'center',
                color: '#888', fontSize: 12, fontWeight: 600, lineHeight: 1.6,
              }}
            >
              Et ensuite<br />
              <span style={{ fontSize: 22, color: '#d1d5db' }}>→</span>
            </button>
          </div>
        ) : (
          <WavePanel
            title="Et ensuite"
            segments={segments}
            nodeById={nodeById}
            completedSet={completedSet}
            availableSet={nextWaveSet}
            onCourseClick={onNodeClick}
          />
        )}

      </div>
    </div>
  )
}
