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

const TAG_COLORS = [
  '#e8f0fe', '#e6f4ea', '#fff8e1', '#fce8e6', '#f3e8fd',
  '#e8f5e9', '#e3f2fd', '#fff3e0', '#fce4ec', '#e8eaf6',
  '#e0f7fa', '#f9fbe7',
]
const TAG_TEXT_COLORS = [
  '#1a47a8', '#1e7e34', '#8a6d00', '#c62828', '#6a1b9a',
  '#2e7d32', '#0d47a1', '#e65100', '#880e4f', '#283593',
  '#006064', '#558b2f',
]
// Stable color assignment by tag name
const _tagIndex = {}
let _tagCounter = 0
function tagStyle(tag) {
  if (_tagIndex[tag] == null) _tagIndex[tag] = _tagCounter++ % TAG_COLORS.length
  const i = _tagIndex[tag]
  return { background: TAG_COLORS[i], color: TAG_TEXT_COLORS[i] }
}

// ── Custom nodes ───────────────────────────────────────────────────────────────

const EQUIVALENT_COLOR = '#8a3ffc'
const OFFICIAL_BADGE = { bg: '#e6f4ea', color: '#1e7e34' }
const INFERRED_BADGE = { bg: '#fff8e1', color: '#8a6d00' }

function equivalentBadgeLabel(data) {
  if (data.source === 'official') return `OFFICIELLE · ${data.universite}`
  return `SIMILAIRE ${Math.round((data.confidence ?? 0) * 100)}% · ${data.universite}`
}

function CourseNode({ data }) {
  const color = UNI_COLORS[data.universite] || '#999'
  const isEquivalent = !!data.is_equivalent

  const bg = data.completed ? '#f0faf3'
    : data.isRoot ? '#f0f6ff'
    : isEquivalent ? '#faf5ff'
    : '#fff'
  const border = data.completed ? '#2a9d4e'
    : data.isRoot ? '#1a6ef5'
    : isEquivalent ? EQUIVALENT_COLOR
    : '#ddd'
  const leftBorder = data.completed ? '#2a9d4e' : isEquivalent ? EQUIVALENT_COLOR : color

  return (
    <div style={{
      background: bg,
      border: `1.5px ${isEquivalent && !data.completed ? 'dashed' : 'solid'} ${border}`,
      borderLeft: `4px solid ${leftBorder}`,
      borderRadius: 8,
      padding: '8px 12px',
      minWidth: 160,
      maxWidth: 200,
      boxShadow: data.isRoot ? '0 0 0 3px rgba(26,110,245,0.15)' : '0 1px 3px rgba(0,0,0,.08)',
      fontFamily: 'system-ui, sans-serif',
      cursor: 'pointer',
    }}>
      <Handle type="target" position={Position.Left} style={{ background: '#aaa' }} />
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: 4 }}>
        <div style={{ fontSize: 11, fontWeight: 700, fontFamily: 'monospace', color: '#333', marginBottom: 3 }}>
          {data.sigle}
          {data.completed && <span style={{ marginLeft: 6, color: '#2a9d4e', fontSize: 12 }}>✓</span>}
        </div>
        {data.isRoot && data.onRemoveChain && (
          <button
            style={{ background: 'none', border: 'none', cursor: 'pointer', color: '#ccc', fontSize: 13, padding: 0, lineHeight: 1, flexShrink: 0 }}
            onClick={e => { e.stopPropagation(); data.onRemoveChain(data.sigle) }}
            title="Retirer du graphe"
          >×</button>
        )}
      </div>
      {isEquivalent && (
        <div style={{
          display: 'inline-block',
          fontSize: 9,
          fontWeight: 700,
          letterSpacing: '0.05em',
          marginBottom: 2,
          padding: '1px 6px',
          borderRadius: 4,
          background: data.source === 'official' ? OFFICIAL_BADGE.bg : INFERRED_BADGE.bg,
          color: data.source === 'official' ? OFFICIAL_BADGE.color : INFERRED_BADGE.color,
        }}>
          {equivalentBadgeLabel(data)}
        </div>
      )}
      <div style={{ fontSize: 11, color: '#555', lineHeight: 1.35 }}>
        {data.titre ? data.titre.slice(0, 45) + (data.titre.length > 45 ? '…' : '') : ''}
      </div>
      {data.tags && data.tags.length > 0 && (
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 3, marginTop: 5 }}>
          {data.tags.slice(0, 2).map(tag => (
            <span key={tag} style={{
              ...tagStyle(tag),
              fontSize: 9,
              fontWeight: 700,
              padding: '1px 5px',
              borderRadius: 3,
              letterSpacing: '0.03em',
            }}>
              {tag}
            </span>
          ))}
          {data.tags.length > 2 && (
            <span style={{ fontSize: 9, color: '#aaa', alignSelf: 'center' }}>
              +{data.tags.length - 2}
            </span>
          )}
        </div>
      )}
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

function applyLayout(nodeList, edgeList, completedSet, rootSigleSet, onRemoveChain) {
  const g = new dagre.graphlib.Graph()
  g.setDefaultEdgeLabel(() => ({}))
  g.setGraph({ rankdir: 'LR', ranksep: 70, nodesep: 30, marginx: 20, marginy: 20 })

  nodeList.forEach(n => {
    const w = n.node_type === 'course' ? 180 : 64
    const h = n.node_type === 'course' ? 80 : 32
    g.setNode(n.id, { width: w, height: h })
  })
  edgeList.forEach(e => g.setEdge(e.source, e.target))

  dagre.layout(g)

  const rfNodes = nodeList.map(n => {
    const pos = g.node(n.id)
    const isRoot = rootSigleSet.has(n.id)
    return {
      id: n.id,
      type: n.node_type,
      position: { x: pos.x - pos.width / 2, y: pos.y - pos.height / 2 },
      data: {
        ...n.data,
        completed: n.node_type === 'course' && completedSet.has(n.id),
        isRoot,
        onRemoveChain: isRoot ? onRemoveChain : undefined,
      },
    }
  })

  const rfEdges = edgeList.map(e => {
    if (e.relation_type === 'equivalent') {
      return {
        id: e.id,
        source: e.source,
        target: e.target,
        type: 'smoothstep',
        label: e.label,
        labelStyle: { fontSize: 10, fill: EQUIVALENT_COLOR, fontWeight: 600 },
        labelBgStyle: { fill: '#faf5ff', fillOpacity: 0.9 },
        style: { stroke: EQUIVALENT_COLOR, strokeWidth: 1.5, strokeDasharray: '4 3' },
        animated: false,
      }
    }
    return {
      id: e.id,
      source: e.source,
      target: e.target,
      type: 'smoothstep',
      style: { stroke: '#bbb', strokeWidth: 1.5 },
      animated: false,
    }
  })

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

export default function GraphCanvas({ completed, chainsToLoad, resetKey, onNodeClick, onRemoveChain }) {
  const [nodes, setNodes, onNodesChange] = useNodesState([])
  const [edges, setEdges, onEdgesChange] = useEdgesState([])
  const [fullscreen, setFullscreen] = useState(false)
  const [loadingSigles, setLoadingSigles] = useState(new Set())

  const rawNodes = useRef({})
  const rawEdges = useRef({})
  const rootSigles = useRef(new Set())
  const loadedRef = useRef(new Set())
  const chainMembership = useRef(new Map()) // sigle → { nodeIds: Set, edgeIds: Set }
  const prevChainsRef = useRef([])

  // Stable ref to onRemoveChain so relayout doesn't need it as a dep
  const onRemoveChainRef = useRef(onRemoveChain)
  useEffect(() => { onRemoveChainRef.current = onRemoveChain }, [onRemoveChain])

  const completedSet = new Set((completed || []).map(c => c.sigle))

  const relayout = useCallback(() => {
    const nodeList = Object.values(rawNodes.current)
    const edgeList = Object.values(rawEdges.current)
    if (nodeList.length === 0) { setNodes([]); setEdges([]); return }
    const { rfNodes, rfEdges } = applyLayout(
      nodeList, edgeList, completedSet, rootSigles.current,
      (sigle) => onRemoveChainRef.current?.(sigle)
    )
    setNodes(rfNodes)
    setEdges(rfEdges)
  }, [completed]) // eslint-disable-line react-hooks/exhaustive-deps

  const loadChain = useCallback((sigle) => {
    if (!sigle || loadedRef.current.has(sigle)) return
    loadedRef.current.add(sigle)
    setLoadingSigles(prev => new Set([...prev, sigle]))

    fetch(`${API}/courses/${encodeURIComponent(sigle)}/prerequisite-chain`)
      .then(r => { if (!r.ok) throw new Error(r.status); return r.json() })
      .then(chain => {
        rootSigles.current.add(chain.root)
        const nodeIds = new Set()
        const edgeIds = new Set()
        chain.nodes.forEach(n => {
          // A course can be discovered both as a real chain root and as
          // another node's equivalent sibling, depending on which fetch
          // resolves last. Once flagged equivalent, keep it flagged.
          const prev = rawNodes.current[n.id]
          rawNodes.current[n.id] = prev?.data?.is_equivalent
            ? { ...n, data: { ...n.data, is_equivalent: true } }
            : n
          nodeIds.add(n.id)
        })
        chain.edges.forEach(e => { rawEdges.current[e.id] = e; edgeIds.add(e.id) })
        chainMembership.current.set(sigle, { nodeIds, edgeIds })
        relayout()
      })
      .catch(() => { loadedRef.current.delete(sigle) })
      .finally(() => {
        setLoadingSigles(prev => { const s = new Set(prev); s.delete(sigle); return s })
      })
  }, [relayout])

  const removeChain = useCallback((sigle) => {
    const membership = chainMembership.current.get(sigle)
    if (!membership) return

    chainMembership.current.delete(sigle)
    rootSigles.current.delete(sigle)
    loadedRef.current.delete(sigle)

    // Collect node/edge IDs still owned by other chains
    const survivingNodeIds = new Set()
    const survivingEdgeIds = new Set()
    chainMembership.current.forEach(m => {
      m.nodeIds.forEach(id => survivingNodeIds.add(id))
      m.edgeIds.forEach(id => survivingEdgeIds.add(id))
    })

    membership.nodeIds.forEach(id => { if (!survivingNodeIds.has(id)) delete rawNodes.current[id] })
    membership.edgeIds.forEach(id => { if (!survivingEdgeIds.has(id)) delete rawEdges.current[id] })

    relayout()
  }, [relayout])

  // Diff chainsToLoad: load new sigles, remove dropped ones
  useEffect(() => {
    const prev = new Set(prevChainsRef.current)
    const curr = new Set(chainsToLoad)

    chainsToLoad.forEach(sigle => { if (!prev.has(sigle)) loadChain(sigle) })
    prevChainsRef.current.forEach(sigle => { if (!curr.has(sigle)) removeChain(sigle) })

    prevChainsRef.current = [...chainsToLoad]
  }, [chainsToLoad, loadChain, removeChain])

  // Re-layout when completion status changes
  useEffect(() => { relayout() }, [completed]) // eslint-disable-line react-hooks/exhaustive-deps

  // Full reset
  useEffect(() => {
    rawNodes.current = {}
    rawEdges.current = {}
    rootSigles.current = new Set()
    loadedRef.current = new Set()
    chainMembership.current = new Map()
    prevChainsRef.current = []
    setLoadingSigles(new Set())
    setNodes([])
    setEdges([])
    setFullscreen(false)
  }, [resetKey]) // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (!fullscreen) return
    const handler = e => { if (e.key === 'Escape') setFullscreen(false) }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [fullscreen])

  useEffect(() => {
    document.body.style.overflow = fullscreen ? 'hidden' : ''
    return () => { document.body.style.overflow = '' }
  }, [fullscreen])

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
