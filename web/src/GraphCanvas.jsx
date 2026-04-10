import { useEffect, useRef, useState, useCallback } from 'react'
import ReactFlow, {
  Background,
  Controls,
  Handle,
  Panel,
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

// ── Custom nodes ───────────────────────────────────────────────────────────────

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
      cursor: 'pointer',
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

// ── Layout ─────────────────────────────────────────────────────────────────────

function applyLayout(nodeList, edgeList, completedSet, rootSigleSet) {
  const g = new dagre.graphlib.Graph()
  g.setDefaultEdgeLabel(() => ({}))
  g.setGraph({ rankdir: 'LR', ranksep: 70, nodesep: 30, marginx: 20, marginy: 20 })

  nodeList.forEach(n => {
    const w = n.node_type === 'course' ? 180 : 64
    const h = n.node_type === 'course' ? 64 : 32
    g.setNode(n.id, { width: w, height: h })
  })
  edgeList.forEach(e => g.setEdge(e.source, e.target))

  dagre.layout(g)

  const rfNodes = nodeList.map(n => {
    const pos = g.node(n.id)
    return {
      id: n.id,
      type: n.node_type,
      position: { x: pos.x - pos.width / 2, y: pos.y - pos.height / 2 },
      data: {
        ...n.data,
        completed: n.node_type === 'course' && completedSet.has(n.id),
        isRoot: rootSigleSet.has(n.id),
      },
    }
  })

  const rfEdges = edgeList.map(e => ({
    id: e.id,
    source: e.source,
    target: e.target,
    type: 'smoothstep',
    style: { stroke: '#bbb', strokeWidth: 1.5 },
    animated: false,
  }))

  return { rfNodes, rfEdges }
}

// ── Main component ─────────────────────────────────────────────────────────────

const btnStyle = {
  background: '#fff',
  border: '1px solid #ddd',
  borderRadius: 6,
  padding: '5px 8px',
  cursor: 'pointer',
  fontSize: 14,
  lineHeight: 1,
  color: '#555',
  boxShadow: '0 1px 3px rgba(0,0,0,.1)',
}

export default function GraphCanvas({ completed, chainToLoad, resetKey, onNodeClick }) {
  const [nodes, setNodes, onNodesChange] = useNodesState([])
  const [edges, setEdges, onEdgesChange] = useEdgesState([])
  const [fullscreen, setFullscreen] = useState(false)
  const [loadingSigles, setLoadingSigles] = useState(new Set())

  // Raw accumulated graph data — plain objects, not React state, to avoid stale closures
  const rawNodes = useRef({})  // id → API node object
  const rawEdges = useRef({})  // id → API edge object
  const rootSigles = useRef(new Set())
  const loadedRef = useRef(new Set())  // sigles already fetched (dedup)

  const completedSet = new Set((completed || []).map(c => c.sigle))

  // Re-layout and push to ReactFlow whenever raw data or completion changes
  const relayout = useCallback(() => {
    const nodeList = Object.values(rawNodes.current)
    const edgeList = Object.values(rawEdges.current)
    if (nodeList.length === 0) { setNodes([]); setEdges([]); return }
    const { rfNodes, rfEdges } = applyLayout(nodeList, edgeList, completedSet, rootSigles.current)
    setNodes(rfNodes)
    setEdges(rfEdges)
  }, [completed]) // eslint-disable-line react-hooks/exhaustive-deps

  // Load a single chain and merge into accumulated raw data
  const loadChain = useCallback((sigle) => {
    if (!sigle || loadedRef.current.has(sigle)) return
    loadedRef.current.add(sigle)
    setLoadingSigles(prev => new Set([...prev, sigle]))

    fetch(`${API}/courses/${encodeURIComponent(sigle)}/prerequisite-chain`)
      .then(r => { if (!r.ok) throw new Error(r.status); return r.json() })
      .then(chain => {
        rootSigles.current.add(chain.root)
        chain.nodes.forEach(n => { rawNodes.current[n.id] = n })
        chain.edges.forEach(e => { rawEdges.current[e.id] = e })
        relayout()
      })
      .catch(() => {})
      .finally(() => {
        setLoadingSigles(prev => {
          const next = new Set(prev)
          next.delete(sigle)
          return next
        })
      })
  }, [relayout])

  // Trigger chain load when prop changes
  useEffect(() => {
    if (chainToLoad) loadChain(chainToLoad)
  }, [chainToLoad, loadChain])

  // Re-layout when completion status changes
  useEffect(() => {
    relayout()
  }, [completed]) // eslint-disable-line react-hooks/exhaustive-deps

  // Reset all state when resetKey changes
  useEffect(() => {
    rawNodes.current = {}
    rawEdges.current = {}
    rootSigles.current = new Set()
    loadedRef.current = new Set()
    setLoadingSigles(new Set())
    setNodes([])
    setEdges([])
    setFullscreen(false)
  }, [resetKey]) // eslint-disable-line react-hooks/exhaustive-deps

  // Escape closes fullscreen
  useEffect(() => {
    if (!fullscreen) return
    const handler = e => { if (e.key === 'Escape') setFullscreen(false) }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [fullscreen])

  // Lock body scroll when fullscreen
  useEffect(() => {
    document.body.style.overflow = fullscreen ? 'hidden' : ''
    return () => { document.body.style.overflow = '' }
  }, [fullscreen])

  // Handle node click: open detail + expand chain
  function handleNodeClick(_, node) {
    if (node.type !== 'course') return
    if (onNodeClick) onNodeClick(node.data)
    loadChain(node.id)
  }

  const containerStyle = fullscreen
    ? { position: 'fixed', inset: 0, zIndex: 200, background: '#fff' }
    : { position: 'absolute', inset: 0 }

  const isEmpty = nodes.length === 0 && loadingSigles.size === 0

  return (
    <div style={containerStyle}>
      {isEmpty && (
        <div className="graph-empty">
          <div className="graph-empty-icon">⬡</div>
          <div className="graph-empty-text">
            Recherchez un cours et cliquez sur + pour visualiser sa chaîne de prérequis
          </div>
        </div>
      )}

      {!isEmpty && (
        <ReactFlow
          nodes={nodes}
          edges={edges}
          onNodesChange={onNodesChange}
          onEdgesChange={onEdgesChange}
          nodeTypes={NODE_TYPES}
          onNodeClick={handleNodeClick}
          fitView
          fitViewOptions={{ padding: 0.2 }}
          minZoom={0.2}
          proOptions={{ hideAttribution: true }}
        >
          <Background color="#f0f0f0" gap={16} />
          <Controls showInteractive={false} />
          <Panel position="top-right">
            <button
              style={btnStyle}
              onClick={() => setFullscreen(f => !f)}
              title={fullscreen ? 'Quitter le plein écran' : 'Plein écran'}
            >
              {fullscreen ? '✕  Quitter' : '⛶  Plein écran'}
            </button>
          </Panel>
        </ReactFlow>
      )}

      {loadingSigles.size > 0 && (
        <div className="graph-loading-badge">
          Chargement… ({loadingSigles.size})
        </div>
      )}
    </div>
  )
}
