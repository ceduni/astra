import { useEffect, useState } from 'react'
import ReactFlow, {
  Background,
  Controls,
  Handle,
  Position,
  useNodesState,
  useEdgesState,
} from 'reactflow'
import 'reactflow/dist/style.css'

const API = '/api'

// Stable palette indexed by tag insertion order
const TAG_PALETTE = [
  { bg: '#e8f0fe', border: '#4285f4', text: '#1a47a8' },
  { bg: '#e6f4ea', border: '#34a853', text: '#1e7e34' },
  { bg: '#fff8e1', border: '#f9a825', text: '#8a6d00' },
  { bg: '#fce8e6', border: '#ea4335', text: '#c62828' },
  { bg: '#f3e8fd', border: '#9c27b0', text: '#6a1b9a' },
  { bg: '#e8f5e9', border: '#4caf50', text: '#2e7d32' },
  { bg: '#e3f2fd', border: '#2196f3', text: '#0d47a1' },
  { bg: '#fff3e0', border: '#ff9800', text: '#e65100' },
  { bg: '#fce4ec', border: '#e91e63', text: '#880e4f' },
  { bg: '#e8eaf6', border: '#3f51b5', text: '#283593' },
  { bg: '#e0f7fa', border: '#00bcd4', text: '#006064' },
  { bg: '#f9fbe7', border: '#8bc34a', text: '#558b2f' },
  { bg: '#f5f5f5', border: '#9e9e9e', text: '#616161' }, // Autres / fallback
]

const _tagMap = {}
let _tagIdx = 0
function tagStyle(tag) {
  if (!tag || tag === 'Autres') return TAG_PALETTE[TAG_PALETTE.length - 1]
  if (_tagMap[tag] == null) _tagMap[tag] = _tagIdx++ % (TAG_PALETTE.length - 1)
  return TAG_PALETTE[_tagMap[tag]]
}

// ── Layout ─────────────────────────────────────────────────────────────────────

const NODE_W = 180
const NODE_H = 80
const H_GAP = 16
const V_GAP = 14
const PAD = 20
const COL_GAP = 64
const ROW_GAP = 64
const LABEL_H = 30
const CLUSTERS_PER_ROW = 4

function computeLayout(nodes) {
  const groups = {}
  for (const n of nodes) {
    const tag = n.tags && n.tags.length > 0 ? n.tags[0] : 'Autres'
    if (!groups[tag]) groups[tag] = []
    groups[tag].push(n)
  }

  const clusters = Object.entries(groups)
    .sort(([, a], [, b]) => b.length - a.length)
    .map(([tag, courses]) => {
      const n = courses.length
      const cols = n <= 4 ? n : Math.min(4, Math.ceil(Math.sqrt(n)))
      const rows = Math.ceil(n / cols)
      return {
        tag, courses, cols,
        w: cols * NODE_W + (cols - 1) * H_GAP + PAD * 2,
        h: rows * NODE_H + (rows - 1) * V_GAP + PAD * 2,
      }
    })

  let curX = 0, curY = 0, rowMaxH = 0
  return clusters.map((cluster, ci) => {
    if (ci > 0 && ci % CLUSTERS_PER_ROW === 0) {
      curX = 0
      curY += rowMaxH + ROW_GAP + LABEL_H
      rowMaxH = 0
    }
    const nodePositions = cluster.courses.map((_, i) => ({
      x: curX + PAD + (i % cluster.cols) * (NODE_W + H_GAP),
      y: curY + LABEL_H + PAD + Math.floor(i / cluster.cols) * (NODE_H + V_GAP),
    }))
    const out = { ...cluster, x: curX, y: curY, nodePositions }
    curX += cluster.w + COL_GAP
    rowMaxH = Math.max(rowMaxH, cluster.h)
    return out
  })
}

// ── Node components (defined outside the main component to avoid re-registration) ──

function ExplorationCourseNode({ data }) {
  const s = tagStyle(data.tags?.[0] ?? null)
  return (
    <div style={{
      background: s.bg,
      border: `1.5px solid ${s.border}`,
      borderLeft: `4px solid ${s.border}`,
      borderRadius: 7,
      padding: '7px 11px',
      width: NODE_W,
      minHeight: NODE_H,
      fontFamily: 'system-ui, sans-serif',
      cursor: 'pointer',
      boxShadow: '0 1px 3px rgba(0,0,0,.07)',
      display: 'flex',
      flexDirection: 'column',
      gap: 3,
    }}>
      <Handle type="target" position={Position.Left} style={{ opacity: 0 }} />
      <div style={{ fontSize: 11, fontWeight: 700, fontFamily: 'monospace', color: '#1a1a1a' }}>
        {data.sigle}
      </div>
      <div style={{ fontSize: 10.5, color: '#555', lineHeight: 1.35 }}>
        {data.titre ? (data.titre.length > 46 ? data.titre.slice(0, 46) + '…' : data.titre) : ''}
      </div>
      {(data.credits || data.niveau) && (
        <div style={{ fontSize: 9.5, color: '#999', marginTop: 'auto' }}>
          {[data.credits && `${data.credits} cr`, data.niveau && `Niv. ${data.niveau}`]
            .filter(Boolean).join(' · ')}
        </div>
      )}
      <Handle type="source" position={Position.Right} style={{ opacity: 0 }} />
    </div>
  )
}

function ClusterLabelNode({ data }) {
  const s = tagStyle(data.tag)
  return (
    <div style={{
      pointerEvents: 'none',
      fontFamily: 'system-ui, sans-serif',
      fontSize: 11,
      fontWeight: 700,
      color: s.text,
      letterSpacing: '0.05em',
      textTransform: 'uppercase',
      padding: '3px 8px',
      background: s.bg,
      border: `1px solid ${s.border}`,
      borderRadius: 5,
      whiteSpace: 'nowrap',
      display: 'inline-flex',
      alignItems: 'center',
      gap: 5,
    }}>
      {data.tag}
      <span style={{ fontWeight: 400, opacity: 0.7, textTransform: 'none', letterSpacing: 0 }}>
        ({data.count})
      </span>
    </div>
  )
}

const NODE_TYPES = {
  explorationCourse: ExplorationCourseNode,
  clusterLabel: ClusterLabelNode,
}

// ── Main component ─────────────────────────────────────────────────────────────

export default function ExplorationGraph({ completed, homeUniversite, program, onNodeClick }) {
  const [nodes, setNodes, onNodesChange] = useNodesState([])
  const [edges, setEdges, onEdgesChange] = useEdgesState([])
  const [status, setStatus] = useState('idle')

  useEffect(() => {
    if (!homeUniversite) {
      setNodes([])
      setEdges([])
      setStatus('idle')
      return
    }

    let cancelled = false
    setStatus('loading')

    fetch(`${API}/courses/eligible-graph`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        completed: completed.map(c => c.sigle),
        home_universite: homeUniversite,
        program: program ?? null,
      }),
    })
      .then(r => { if (!r.ok) throw new Error(r.status); return r.json() })
      .then(data => {
        if (cancelled) return
        if (!data.nodes.length) { setStatus('empty'); return }

        const layout = computeLayout(data.nodes)
        const posMap = {}
        const labelNodes = []

        layout.forEach(cluster => {
          cluster.courses.forEach((course, i) => {
            posMap[course.sigle] = cluster.nodePositions[i]
          })
          labelNodes.push({
            id: `__lbl__${cluster.tag}`,
            type: 'clusterLabel',
            position: { x: cluster.x, y: cluster.y },
            data: { tag: cluster.tag, count: cluster.courses.length },
            draggable: false,
            selectable: false,
          })
        })

        const rfNodes = data.nodes.map(n => ({
          id: n.sigle,
          type: 'explorationCourse',
          position: posMap[n.sigle] || { x: 0, y: 0 },
          data: n,
        }))

        const rfEdges = data.edges.map(e => ({
          id: `${e.source}->${e.target}`,
          source: e.source,
          target: e.target,
          type: 'smoothstep',
          style: { stroke: '#b8c4d4', strokeWidth: 1.5 },
          markerEnd: { type: 'arrowclosed', width: 10, height: 10, color: '#b8c4d4' },
        }))

        setNodes([...labelNodes, ...rfNodes])
        setEdges(rfEdges)
        setStatus('ready')
      })
      .catch(() => { if (!cancelled) setStatus('error') })

    return () => { cancelled = true }
  }, [completed, homeUniversite, program]) // eslint-disable-line react-hooks/exhaustive-deps

  function handleNodeClick(_, node) {
    if (node.type !== 'explorationCourse') return
    onNodeClick?.(node.data)
  }

  return (
    <div style={{ position: 'absolute', inset: 0, background: '#f7f8fb' }}>
      {status === 'loading' && (
        <div className="graph-empty">
          <div className="graph-empty-text">Calcul des cours accessibles…</div>
        </div>
      )}
      {status === 'empty' && (
        <div className="graph-empty">
          <div className="graph-empty-icon">⬡</div>
          <div className="graph-empty-text">Aucun cours accessible avec vos cours complétés.</div>
        </div>
      )}
      {status === 'error' && (
        <div className="graph-empty">
          <div className="graph-empty-text" style={{ color: '#c00' }}>Erreur de chargement.</div>
        </div>
      )}
      {status === 'ready' && (
        <ReactFlow
          nodes={nodes}
          edges={edges}
          onNodesChange={onNodesChange}
          onEdgesChange={onEdgesChange}
          nodeTypes={NODE_TYPES}
          onNodeClick={handleNodeClick}
          fitView
          fitViewOptions={{ padding: 0.12 }}
          minZoom={0.05}
          maxZoom={2}
          proOptions={{ hideAttribution: true }}
        >
          <Background color="#e8ebf0" gap={20} />
          <Controls showInteractive={false} />
        </ReactFlow>
      )}
    </div>
  )
}
