import { useEffect, useState, useCallback } from 'react'
import ReactFlow, {
  Background,
  Controls,
  Handle,
  Position,
  useNodesState,
  useEdgesState,
} from 'reactflow'
import dagre from '@dagrejs/dagre'
import 'reactflow/dist/style.css'

const API = '/api'

const UNI_COLORS = {
  UdeM:      '#0057a8',
  UQAM:      '#00833e',
  McGill:    '#ed1b2f',
  Concordia: '#912338',
  Poly:      '#f0a500',
}

// ── Custom node: Course ────────────────────────────────────────────────────

function CourseNode({ data }) {
  const color = UNI_COLORS[data.universite] || '#999'
  const bg = data.completed ? '#f0faf3' : data.isRoot ? '#f0f6ff' : '#fff'
  const border = data.completed ? '#2a9d4e' : data.isRoot ? '#1a6ef5' : '#ddd'

  return (
    <div style={{
      background: bg,
      border: `1.5px solid ${border}`,
      borderLeft: `4px solid ${data.completed ? '#2a9d4e' : color}`,
      borderRadius: 8,
      padding: '8px 12px',
      minWidth: 160,
      maxWidth: 200,
      boxShadow: data.isRoot ? '0 0 0 3px rgba(26,110,245,0.15)' : '0 1px 3px rgba(0,0,0,.08)',
      fontFamily: 'system-ui, sans-serif',
    }}>
      <Handle type="target" position={Position.Left} style={{ background: '#aaa' }} />
      <div style={{ fontSize: 11, fontWeight: 700, fontFamily: 'monospace', color: '#333', marginBottom: 3 }}>
        {data.sigle}
        {data.completed && <span style={{ marginLeft: 6, color: '#2a9d4e', fontSize: 12 }}>✓</span>}
      </div>
      <div style={{ fontSize: 11, color: '#555', lineHeight: 1.35 }}>
        {data.titre ? data.titre.slice(0, 45) + (data.titre.length > 45 ? '…' : '') : ''}
      </div>
      <Handle type="source" position={Position.Right} style={{ background: '#aaa' }} />
    </div>
  )
}

// ── Custom node: AND / OR group ────────────────────────────────────────────

function GroupNode({ data }) {
  const isAnd = data.type === 'AND'
  return (
    <div style={{
      background: isAnd ? '#e8f0fe' : '#fff4e6',
      border: `1.5px solid ${isAnd ? '#4285f4' : '#f59f00'}`,
      borderRadius: 20,
      padding: '4px 12px',
      fontSize: 11,
      fontWeight: 700,
      color: isAnd ? '#1a47a8' : '#b45309',
      letterSpacing: '0.06em',
      whiteSpace: 'nowrap',
    }}>
      <Handle type="target" position={Position.Left} style={{ background: '#aaa' }} />
      {isAnd ? 'ET' : 'OU'}
      <Handle type="source" position={Position.Right} style={{ background: '#aaa' }} />
    </div>
  )
}

const NODE_TYPES = { course: CourseNode, group: GroupNode }

// ── Dagre layout ───────────────────────────────────────────────────────────

function applyLayout(chainNodes, chainEdges, completedSet, rootSigle) {
  const g = new dagre.graphlib.Graph()
  g.setDefaultEdgeLabel(() => ({}))
  g.setGraph({ rankdir: 'LR', ranksep: 70, nodesep: 30, marginx: 20, marginy: 20 })

  chainNodes.forEach(n => {
    const w = n.node_type === 'course' ? 180 : 64
    const h = n.node_type === 'course' ? 64 : 32
    g.setNode(n.id, { width: w, height: h })
  })
  chainEdges.forEach(e => g.setEdge(e.source, e.target))

  dagre.layout(g)

  const rfNodes = chainNodes.map(n => {
    const pos = g.node(n.id)
    return {
      id: n.id,
      type: n.node_type,
      position: { x: pos.x - pos.width / 2, y: pos.y - pos.height / 2 },
      data: {
        ...n.data,
        completed: n.node_type === 'course' && completedSet.has(n.id),
        isRoot: n.id === rootSigle,
      },
    }
  })

  const rfEdges = chainEdges.map(e => ({
    id: e.id,
    source: e.source,
    target: e.target,
    type: 'smoothstep',
    style: { stroke: '#bbb', strokeWidth: 1.5 },
    animated: false,
  }))

  return { rfNodes, rfEdges }
}

// ── Main component ─────────────────────────────────────────────────────────

export default function PrereqGraph({ sigle, completed }) {
  const [nodes, setNodes, onNodesChange] = useNodesState([])
  const [edges, setEdges, onEdgesChange] = useEdgesState([])
  const [status, setStatus] = useState('loading') // loading | empty | ready | error

  const completedSet = new Set((completed || []).map(c => c.sigle))

  useEffect(() => {
    setStatus('loading')
    fetch(`${API}/courses/${encodeURIComponent(sigle)}/prerequisite-chain`)
      .then(r => { if (!r.ok) throw new Error(r.status); return r.json() })
      .then(chain => {
        // Only course nodes that aren't the root
        const hasPrereqs = chain.nodes.some(n => n.node_type === 'course' && n.id !== sigle)
        if (!hasPrereqs) { setStatus('empty'); return }

        const { rfNodes, rfEdges } = applyLayout(chain.nodes, chain.edges, completedSet, chain.root)
        setNodes(rfNodes)
        setEdges(rfEdges)
        setStatus('ready')
      })
      .catch(() => setStatus('error'))
  }, [sigle])

  if (status === 'loading') return <div className="graph-placeholder">Chargement du graphe…</div>
  if (status === 'empty')   return <div className="graph-placeholder">Aucun prérequis enregistré.</div>
  if (status === 'error')   return <div className="graph-placeholder" style={{color:'#c00'}}>Erreur de chargement.</div>

  return (
    <div style={{ height: 340, borderRadius: 8, overflow: 'hidden', border: '1px solid #e2e5ea' }}>
      <ReactFlow
        nodes={nodes}
        edges={edges}
        onNodesChange={onNodesChange}
        onEdgesChange={onEdgesChange}
        nodeTypes={NODE_TYPES}
        fitView
        fitViewOptions={{ padding: 0.2 }}
        minZoom={0.3}
        proOptions={{ hideAttribution: true }}
      >
        <Background color="#f0f0f0" gap={16} />
        <Controls showInteractive={false} />
      </ReactFlow>
    </div>
  )
}
