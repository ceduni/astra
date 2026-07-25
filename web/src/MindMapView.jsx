import { useEffect, useRef, useState } from 'react'
import ReactFlow, {
  Background, Controls, MiniMap,
  Handle, Position,
  useEdgesState, useNodesState,
} from 'reactflow'
import 'reactflow/dist/style.css'
import dagre from '@dagrejs/dagre'
import { UNI_COLORS } from './graphShared'
import { computeAvailability } from './availability'

const API = '/api'

function hexWithOpacity(hex, opacity) {
  const r = parseInt(hex.slice(1, 3), 16)
  const g = parseInt(hex.slice(3, 5), 16)
  const b = parseInt(hex.slice(5, 7), 16)
  return `rgba(${r},${g},${b},${opacity})`
}

const DIMS = {
  mm_root:    { w: 240, h: 104 },
  mm_segment: { w: 220, h: 88 },
  mm_course:  { w: 200, h: 84 },
}

// ── Custom node: Root ─────────────────────────────────────────────────────────

function MmRootNode({ data }) {
  const uniColor = UNI_COLORS[data.universite] || '#555'
  return (
    <div style={{
      background: '#fff',
      borderRadius: 14,
      padding: '14px 18px',
      minWidth: DIMS.mm_root.w,
      maxWidth: DIMS.mm_root.w,
      boxShadow: '0 4px 20px rgba(0,0,0,0.10)',
      cursor: 'default',
      userSelect: 'none',
    }}>
      <div style={{ fontSize: 15, fontWeight: 800, color: '#111', letterSpacing: '-0.01em', lineHeight: 1.25 }}>
        {data.programLabel || 'Mon programme'}
      </div>
      {data.orientationLabel && (
        <div style={{ fontSize: 10, color: '#999', marginTop: 2, lineHeight: 1.3 }}>
          {data.orientationLabel}
        </div>
      )}
      <div style={{ display: 'flex', alignItems: 'center', gap: 5, marginTop: 7 }}>
        <span style={{
          width: 8, height: 8, borderRadius: '50%',
          background: uniColor, flexShrink: 0, display: 'inline-block',
        }} />
        <span style={{ fontSize: 10.5, color: uniColor, fontWeight: 700 }}>{data.universite}</span>
      </div>
      <div style={{ height: 1, background: '#f0f0f0', margin: '8px 0' }} />
      <div style={{ fontSize: 10, color: '#2a9d4e', fontWeight: 600 }}>
        {data.completedCount} cours complétés
      </div>
      <Handle type="source" position={Position.Right} style={{ opacity: 0, pointerEvents: 'none' }} />
    </div>
  )
}

// ── Custom node: Segment ──────────────────────────────────────────────────────

function MmSegmentNode({ data }) {
  const [hovered, setHovered] = useState(false)
  const isLibre = data.type === 'libre'
  const typeStyle = data.type === 'obligatoire'
    ? { bg: '#e8f5e9', text: '#2a7d3f', label: 'OBLIGATOIRE', barColor: '#4caf50' }
    : isLibre
    ? { bg: '#f5f5f5', text: '#9e9e9e', label: 'LIBRE', barColor: '#9e9e9e' }
    : { bg: '#fff8e1', text: '#f57f17', label: 'OPTION', barColor: '#ffa000' }

  const progressPct = data.credits_max
    ? Math.min(100, (data.credCompleted / data.credits_max) * 100)
    : 0

  return (
    <div
      onMouseEnter={() => !isLibre && setHovered(true)}
      onMouseLeave={() => setHovered(false)}
      style={{
        background: '#fff',
        border: `1px solid ${data.isExpanded ? '#c4c8d0' : '#e8e8e8'}`,
        borderLeft: `3px solid ${data.isExpanded ? '#6b7280' : 'transparent'}`,
        borderRadius: 10,
        padding: '11px 14px',
        minWidth: DIMS.mm_segment.w,
        maxWidth: DIMS.mm_segment.w,
        cursor: isLibre ? 'default' : 'pointer',
        boxShadow: hovered
          ? '0 2px 10px rgba(0,0,0,0.09)'
          : data.isExpanded
          ? '0 2px 6px rgba(0,0,0,0.07)'
          : '0 1px 3px rgba(0,0,0,0.04)',
        transition: 'box-shadow 0.15s ease, border-color 0.15s ease',
        userSelect: 'none',
      }}
    >
      <Handle type="target" position={Position.Left} style={{ opacity: 0, pointerEvents: 'none' }} />

      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: 6 }}>
        <div style={{ fontSize: 12, fontWeight: 700, color: '#111', lineHeight: 1.3, flex: 1 }}>
          {data.label}
        </div>
        {!isLibre && (
          <span style={{
            fontSize: 11,
            color: data.isExpanded ? '#6b7280' : '#c0c0c0',
            flexShrink: 0,
            transition: 'color 0.15s',
          }}>
            {data.isExpanded ? '▾' : '▸'}
          </span>
        )}
      </div>

      {data.group_label && (
        <div style={{ fontSize: 9, color: '#c8c8c8', marginTop: 2, textTransform: 'uppercase', letterSpacing: '0.05em' }}>
          {data.group_label}
        </div>
      )}

      <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginTop: 8 }}>
        <span style={{
          fontSize: 8.5, fontWeight: 700, padding: '1px 5px', borderRadius: 3,
          background: typeStyle.bg, color: typeStyle.text, letterSpacing: '0.04em',
        }}>
          {typeStyle.label}
        </span>
        {data.credits_max != null && (
          <span style={{ fontSize: 9.5, color: '#b8b8b8' }}>
            {data.credCompleted}/{data.credits_max} cr
          </span>
        )}
      </div>

      {!isLibre && data.credits_max != null && (
        <div style={{ height: 2.5, background: '#f0f0f0', borderRadius: 2, marginTop: 8, overflow: 'hidden' }}>
          <div style={{
            height: '100%',
            width: `${progressPct}%`,
            background: typeStyle.barColor,
            borderRadius: 2,
          }} />
        </div>
      )}

      <Handle type="source" position={Position.Right} style={{ opacity: 0, pointerEvents: 'none' }} />
    </div>
  )
}

// ── Custom node: Course ───────────────────────────────────────────────────────

const STATUS_CONFIG = {
  completed: {
    bg: '#fafff9',
    badge: 'COMPLÉTÉ', badgeBg: '#e8f5e9', badgeColor: '#2a7d3f',
    creditsColor: '#2a9d4e',
  },
  available: {
    bg: '#f8fbff',
    badge: 'DISPONIBLE', badgeBg: '#e8f0fe', badgeColor: '#1a47a8',
    creditsColor: '#2563eb',
  },
  locked: {
    bg: '#fafafa',
    badge: 'VERROUILLÉ', badgeBg: '#f0f0f0', badgeColor: '#9e9e9e',
    creditsColor: '#c0c0c0',
  },
}

function MmCourseNode({ data }) {
  const [hovered, setHovered] = useState(false)
  const { sigle, titre, credits, status, substitution } = data

  if (substitution) {
    const uniColor = UNI_COLORS[substitution.universite] || '#7c5cbf'
    return (
      <div
        onMouseEnter={() => setHovered(true)}
        onMouseLeave={() => setHovered(false)}
        style={{
          background: '#fff',
          border: `1px solid ${hexWithOpacity(uniColor, 0.25)}`,
          borderLeft: `4px solid ${uniColor}`,
          borderRadius: 10,
          padding: '10px 12px',
          minWidth: DIMS.mm_course.w,
          maxWidth: DIMS.mm_course.w,
          cursor: 'pointer',
          boxShadow: hovered
            ? `0 3px 14px ${hexWithOpacity(uniColor, 0.20)}`
            : '0 1px 4px rgba(0,0,0,0.06)',
          transition: 'box-shadow 0.15s ease',
          animation: 'mmNodeIn 0.2s ease-out',
        }}
      >
        <Handle type="target" position={Position.Left} style={{ opacity: 0, pointerEvents: 'none' }} />
        <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: 6, marginBottom: 5 }}>
          <span style={{ fontSize: 12, fontWeight: 700, fontFamily: 'monospace', color: '#111', lineHeight: 1.2 }}>
            {substitution.sigle}
          </span>
          <span style={{
            fontSize: 8.5, fontWeight: 700, padding: '2px 6px', borderRadius: 4,
            background: hexWithOpacity(uniColor, 0.10), color: uniColor,
            whiteSpace: 'nowrap', flexShrink: 0, letterSpacing: '0.03em',
          }}>
            via {substitution.universite}
          </span>
        </div>
        <div style={{
          fontSize: 10.5, color: '#555', lineHeight: 1.35,
          overflow: 'hidden', display: '-webkit-box',
          WebkitLineClamp: 2, WebkitBoxOrient: 'vertical',
          marginBottom: 5,
        }}>
          {substitution.titre || titre || '—'}
        </div>
        <div style={{ fontSize: 9, color: '#bbb', fontFamily: 'monospace' }}>
          remplace {sigle}
        </div>
        <Handle type="source" position={Position.Right} style={{ opacity: 0, pointerEvents: 'none' }} />
      </div>
    )
  }

  const s = STATUS_CONFIG[status] || STATUS_CONFIG.locked

  return (
    <div
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
      style={{
        background: s.bg,
        border: '1px solid #e8e8e8',
        borderRadius: 10,
        padding: '10px 12px',
        minWidth: DIMS.mm_course.w,
        maxWidth: DIMS.mm_course.w,
        cursor: 'pointer',
        boxShadow: hovered ? '0 3px 12px rgba(0,0,0,0.10)' : '0 1px 3px rgba(0,0,0,0.05)',
        transition: 'box-shadow 0.15s ease',
        animation: 'mmNodeIn 0.2s ease-out',
      }}
    >
      <Handle type="target" position={Position.Left} style={{ opacity: 0, pointerEvents: 'none' }} />
      <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: 6, marginBottom: 5 }}>
        <span style={{ fontSize: 12, fontWeight: 700, fontFamily: 'monospace', color: '#111', lineHeight: 1.2 }}>
          {sigle}
        </span>
        <span style={{
          fontSize: 8, fontWeight: 700, padding: '2px 5px', borderRadius: 3,
          background: s.badgeBg, color: s.badgeColor,
          whiteSpace: 'nowrap', flexShrink: 0, letterSpacing: '0.04em',
        }}>
          {s.badge}
        </span>
      </div>
      <div style={{
        fontSize: 10.5, color: '#555', lineHeight: 1.35,
        overflow: 'hidden', display: '-webkit-box',
        WebkitLineClamp: 2, WebkitBoxOrient: 'vertical',
        marginBottom: 5,
      }}>
        {titre || '—'}
      </div>
      {credits != null && (
        <div style={{ fontSize: 9.5, color: s.creditsColor, fontWeight: 600 }}>
          {credits} cr
        </div>
      )}
      <Handle type="source" position={Position.Right} style={{ opacity: 0, pointerEvents: 'none' }} />
    </div>
  )
}

// ── Node type registry (must be at module level, not inside a component) ──────

const MM_NODE_TYPES = { mm_root: MmRootNode, mm_segment: MmSegmentNode, mm_course: MmCourseNode }

// ── Prereq tree builder ───────────────────────────────────────────────────────

export function getPrereqTree(sigle, rawData) {
  const nodeById = {}
  rawData.nodes.forEach(n => { nodeById[n.id] = n })

  function resolve(id) {
    const node = nodeById[id]
    if (!node) return null
    if (node.node_type === 'course') {
      return { kind: 'course', sigle: id, data: node.data }
    }
    if (node.node_type === 'group') {
      const children = rawData.edges
        .filter(e => e.source === id && e.relation_type !== 'equivalent')
        .map(e => resolve(e.target))
        .filter(Boolean)
      return { kind: 'group', groupType: node.data?.type || 'AND', children }
    }
    return null
  }

  return rawData.edges
    .filter(e => e.source === sigle && e.relation_type !== 'equivalent')
    .map(e => resolve(e.target))
    .filter(Boolean)
}

// ── Unlock computation ────────────────────────────────────────────────────────

function computeUnlocks(sigle, rawData, completedSigles) {
  const nodeById = {}
  rawData.nodes.forEach(n => { nodeById[n.id] = n })
  const before = new Set(computeAvailability(rawData, completedSigles))
  const after = computeAvailability(rawData, [...completedSigles, sigle])
  return after
    .filter(s => !before.has(s))
    .map(s => ({ sigle: s, titre: nodeById[s]?.data?.titre }))
}

// ── Dagre layout ──────────────────────────────────────────────────────────────

function applyDagreLayout(nodes, edges) {
  const g = new dagre.graphlib.Graph()
  g.setDefaultEdgeLabel(() => ({}))
  g.setGraph({ rankdir: 'LR', ranksep: 200, nodesep: 44, marginx: 60, marginy: 60 })

  nodes.forEach(n => {
    const d = DIMS[n.type] || { w: 180, h: 84 }
    g.setNode(n.id, { width: d.w, height: d.h })
  })
  edges.forEach(e => g.setEdge(e.source, e.target))
  dagre.layout(g)

  return nodes.map(n => {
    const { x, y, width, height } = g.node(n.id)
    return { ...n, position: { x: x - width / 2, y: y - height / 2 } }
  })
}

// ── Graph construction ────────────────────────────────────────────────────────

function buildGraph(rawData, expandedSegment, completedSigles, substitutions, programInfo = {}) {
  const completedSet = new Set(completedSigles)
  const expandedCompleted = rawData.expanded_completed || completedSigles
  const availableSet = new Set(computeAvailability(rawData, expandedCompleted))

  const nodeById = {}
  rawData.nodes.forEach(n => { nodeById[n.id] = n })

  const segments = rawData.segments || []
  const rfNodes = []
  const rfEdges = []

  rfNodes.push({
    id: '__root__',
    type: 'mm_root',
    position: { x: 0, y: 0 },
    selectable: false,
    draggable: true,
    data: {
      completedCount: completedSigles.length,
      programLabel: programInfo.label,
      orientationLabel: programInfo.orientationLabel,
      universite: programInfo.universite,
    },
  })

  segments.forEach(seg => {
    const credCompleted = (seg.cours || []).reduce((sum, s) => {
      if (!completedSet.has(s)) return sum
      return sum + (nodeById[s]?.data?.credits ?? 0)
    }, 0)
    const isExpanded = expandedSegment === seg.id

    rfNodes.push({
      id: seg.id,
      type: 'mm_segment',
      position: { x: 0, y: 0 },
      selectable: seg.type !== 'libre',
      draggable: true,
      data: { ...seg, isExpanded, credCompleted },
    })

    rfEdges.push({
      id: `e_root_${seg.id}`,
      source: '__root__',
      target: seg.id,
      type: 'default',
      style: { stroke: '#c8ccd0', strokeWidth: 1.2 },
      animated: false,
    })

    if (isExpanded && seg.type !== 'libre') {
      ;(seg.cours || []).forEach(sigle => {
        const courseNode = nodeById[sigle]
        if (!courseNode) return

        const status = completedSet.has(sigle) ? 'completed'
          : availableSet.has(sigle) ? 'available'
          : 'locked'

        rfNodes.push({
          id: sigle,
          type: 'mm_course',
          position: { x: 0, y: 0 },
          draggable: true,
          data: {
            sigle,
            status,
            titre: courseNode.data?.titre,
            description: courseNode.data?.description,
            credits: courseNode.data?.credits,
            universite: courseNode.data?.universite,
            niveau: courseNode.data?.niveau,
            substitution: (substitutions instanceof Map ? substitutions.get(sigle) : null) ?? null,
          },
        })

        rfEdges.push({
          id: `e_${seg.id}_${sigle}`,
          source: seg.id,
          target: sigle,
          type: 'default',
          style: { stroke: '#d1d5db', strokeWidth: 1, opacity: 0.45 },
          animated: false,
        })
      })
    }
  })

  return { rfNodes, rfEdges }
}

// ── Minimap color ─────────────────────────────────────────────────────────────

function minimapColor(node) {
  if (node.type === 'mm_root') return '#e5e7eb'
  if (node.type === 'mm_segment') return '#f3f4f6'
  if (node.type === 'mm_course') {
    if (node.data.substitution) return UNI_COLORS[node.data.substitution.universite] || '#7c5cbf'
    return node.data.status === 'completed' ? '#86efac'
      : node.data.status === 'available' ? '#93c5fd'
      : '#e5e7eb'
  }
  return '#e5e7eb'
}

// ── Main component ────────────────────────────────────────────────────────────

export default function MindMapView({ snapshot, onNodeClick, substitutions }) {
  const [status, setStatus] = useState('idle')
  const [rawData, setRawData] = useState(null)
  const [expandedSegment, setExpandedSegment] = useState(null)
  const [nodes, setNodes, onNodesChange] = useNodesState([])
  const [edges, setEdges, onEdgesChange] = useEdgesState([])
  const rfInstance = useRef(null)
  const prevRawDataRef = useRef(null)
  const positionsRef = useRef(new Map())

  // ── Fetch effect ────────────────────────────────────────────────────────
  useEffect(() => {
    if (!snapshot) { setRawData(null); setStatus('idle'); return }
    setStatus('loading')
    setRawData(null)
    setExpandedSegment(null)
    positionsRef.current.clear()

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

  // ── Track node positions so drag moves are preserved across re-layouts ──
  useEffect(() => {
    nodes.forEach(n => positionsRef.current.set(n.id, n.position))
  }, [nodes])

  // ── Layout effect: only structural changes trigger dagre ────────────────
  useEffect(() => {
    if (!rawData || !snapshot) return

    const isNewData = prevRawDataRef.current !== rawData
    prevRawDataRef.current = rawData

    const { rfNodes, rfEdges } = buildGraph(
      rawData, expandedSegment, snapshot.completedSigles, substitutions,
      { label: snapshot.programLabel, orientationLabel: snapshot.orientationLabel, universite: snapshot.homeUniversite }
    )
    const positioned = applyDagreLayout(rfNodes, rfEdges)

    const withPreserved = isNewData
      ? positioned
      : positioned.map(n => {
          const saved = positionsRef.current.get(n.id)
          return saved ? { ...n, position: saved } : n
        })

    setNodes(withPreserved)
    setEdges(rfEdges)
    setTimeout(() => rfInstance.current?.fitView({ padding: 0.16, duration: 400 }), 60)
  }, [rawData, expandedSegment])

  // ── Substitution patch: updates node data without touching positions ─────
  useEffect(() => {
    setNodes(prev => {
      if (prev.length === 0) return prev
      return prev.map(n => {
        if (n.type !== 'mm_course') return n
        const sub = substitutions instanceof Map ? (substitutions.get(n.id) ?? null) : null
        if (n.data.substitution === sub) return n
        return { ...n, data: { ...n.data, substitution: sub } }
      })
    })
  }, [substitutions])

  function handleNodeClick(_, node) {
    if (node.type === 'mm_segment') {
      if (node.data.type === 'libre') return
      setExpandedSegment(prev => prev === node.id ? null : node.id)
      return
    }
    if (node.type === 'mm_course') {
      const prereqs = getPrereqTree(node.id, rawData)
      const expandedCompleted = rawData.expanded_completed || snapshot.completedSigles
      const unlocked = computeUnlocks(node.id, rawData, expandedCompleted)
      onNodeClick?.({ ...node.data, prereqs, unlocked })
    }
  }

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

  return (
    <div style={{ position: 'absolute', inset: 0 }}>
      <ReactFlow
        nodes={nodes}
        edges={edges}
        onNodesChange={onNodesChange}
        onEdgesChange={onEdgesChange}
        onNodeClick={handleNodeClick}
        onInit={inst => { rfInstance.current = inst }}
        nodeTypes={MM_NODE_TYPES}
        nodesDraggable={true}
        nodesConnectable={false}
        panOnDrag
        zoomOnScroll
        fitView
        fitViewOptions={{ padding: 0.16 }}
        minZoom={0.15}
        maxZoom={2}
      >
        <Background color="#e9ecef" gap={28} size={1} />
        <Controls showInteractive={false} position="bottom-left" />
        <MiniMap
          nodeColor={minimapColor}
          maskColor="rgba(0,0,0,0.04)"
          pannable
          zoomable
          position="bottom-right"
        />
      </ReactFlow>
    </div>
  )
}
