import { useEffect, useRef, useState } from 'react'
import ReactFlow, {
  Background,
  Controls,
  useNodesState,
  useEdgesState,
} from 'reactflow'
import 'reactflow/dist/style.css'
import { NODE_TYPES, applyLayout } from './graphShared'

const API = '/api'

// ── Graph transform ────────────────────────────────────────────────────────────
// Pure function: takes raw API data + student state, returns rfNodes/rfEdges
// ready for ReactFlow. Runs on every snapshot load and substitution change.

function buildGraph(rawData, completedSigles, substitutions) {
  const completedSet = new Set(completedSigles)

  // Strip equivalence nodes/edges — they live in the side panel only
  const baseNodes = rawData.nodes.filter(n => !n.data?.is_equivalent)
  const baseEdges = rawData.edges.filter(e => e.relation_type !== 'equivalent')

  // Build outgoing adjacency for BFS
  const outgoing = {}
  for (const edge of baseEdges) {
    if (!outgoing[edge.source]) outgoing[edge.source] = []
    outgoing[edge.source].push(edge.target)
  }

  // BFS from remaining (non-completed) program courses to find the relevant subgraph
  const remainingProgram = rawData.program_sigles.filter(s => !completedSet.has(s))
  const relevant = new Set(remainingProgram)
  const queue = [...remainingProgram]
  while (queue.length > 0) {
    const curr = queue.shift()
    for (const tgt of (outgoing[curr] || [])) {
      if (!relevant.has(tgt)) { relevant.add(tgt); queue.push(tgt) }
    }
  }

  const nodeById = Object.fromEntries(baseNodes.map(n => [n.id, n]))

  // Completed courses that are reachable (i.e. prerequisites of remaining courses)
  const relevantCompleted = new Set(
    [...relevant].filter(id => nodeById[id]?.node_type === 'course' && completedSet.has(id))
  )

  // Groups whose every relevant child is completed → collapse the whole group
  const groupChildrenMap = {}
  for (const edge of baseEdges) {
    const src = nodeById[edge.source]
    if (src?.node_type === 'group' && relevant.has(edge.source) && relevant.has(edge.target)) {
      if (!groupChildrenMap[edge.source]) groupChildrenMap[edge.source] = []
      groupChildrenMap[edge.source].push(edge.target)
    }
  }
  const fullyCompletedGroups = new Set(
    Object.entries(groupChildrenMap)
      .filter(([, ch]) => ch.length > 0 && ch.every(c => completedSet.has(c)))
      .map(([gid]) => gid)
  )

  const nodesToCollapse = new Set([...relevantCompleted, ...fullyCompletedGroups])
  const hasCollapsed = nodesToCollapse.size > 0

  // Build node list
  let filteredNodes = baseNodes.filter(n => relevant.has(n.id) && !nodesToCollapse.has(n.id))

  if (hasCollapsed) {
    filteredNodes = [{
      id: '__completed__',
      node_type: 'course',
      data: {
        sigle: 'Cours complétés',
        titre: `${completedSigles.length} cours complétés`,
        completed: true,
        isCollapsed: true,
      },
    }, ...filteredNodes]
  }

  // Apply substitutions: keep original data, attach substitution metadata
  if (substitutions?.size > 0) {
    filteredNodes = filteredNodes.map(n => {
      if (n.node_type !== 'course' || n.id === '__completed__') return n
      const sub = substitutions.get(n.id)
      if (!sub) return n
      return { ...n, data: { ...n.data, substitution: { ...sub, originalSigle: n.id } } }
    })
  }

  // Build edge list: redirect collapsed nodes → __completed__, deduplicate
  const survivingIds = new Set(filteredNodes.map(n => n.id))
  const seenEdges = new Set()
  const filteredEdges = []

  for (const edge of baseEdges) {
    if (!relevant.has(edge.source) || !relevant.has(edge.target)) continue

    const source = nodesToCollapse.has(edge.source) ? '__completed__' : edge.source
    const target = nodesToCollapse.has(edge.target) ? '__completed__' : edge.target

    if (source === target) continue
    if (!survivingIds.has(source) || !survivingIds.has(target)) continue

    const key = `${source}->${target}`
    if (seenEdges.has(key)) continue
    seenEdges.add(key)

    filteredEdges.push({ ...edge, id: key, source, target })
  }

  return applyLayout(filteredNodes, filteredEdges, new Set(), new Set(), null)
}


// ── Component ──────────────────────────────────────────────────────────────────

export default function ExplorationGraph({ snapshot, substitutions, onNodeClick }) {
  const [nodes, setNodes, onNodesChange] = useNodesState([])
  const [edges, setEdges, onEdgesChange] = useEdgesState([])
  const [status, setStatus] = useState('idle')
  const rawDataRef = useRef(null)

  // Fetch program graph when snapshot changes
  useEffect(() => {
    if (!snapshot) {
      rawDataRef.current = null
      setNodes([]); setEdges([]); setStatus('idle'); return
    }

    let cancelled = false
    setStatus('loading')
    setNodes([]); setEdges([])

    fetch(`${API}/courses/program-graph`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ uni: snapshot.homeUniversite, program: snapshot.program }),
    })
      .then(r => { if (!r.ok) throw new Error(r.status); return r.json() })
      .then(data => {
        if (cancelled) return
        rawDataRef.current = data
        if (!data.nodes.length) { setStatus('empty'); return }
        const { rfNodes, rfEdges } = buildGraph(data, snapshot.completedSigles, substitutions)
        setNodes(rfNodes)
        setEdges(rfEdges)
        setStatus('ready')
      })
      .catch(() => { if (!cancelled) setStatus('error') })

    return () => { cancelled = true }
  }, [snapshot]) // eslint-disable-line react-hooks/exhaustive-deps

  // Re-layout when substitutions change without re-fetching
  useEffect(() => {
    if (!rawDataRef.current || !snapshot) return
    const { rfNodes, rfEdges } = buildGraph(rawDataRef.current, snapshot.completedSigles, substitutions)
    setNodes(rfNodes)
    setEdges(rfEdges)
  }, [substitutions]) // eslint-disable-line react-hooks/exhaustive-deps

  function handleNodeClick(_, node) {
    if (node.type !== 'course' || node.data.isCollapsed) return
    onNodeClick?.(node.data)
  }

  return (
    <div style={{ position: 'absolute', inset: 0, background: '#f7f8fb' }}>
      {status === 'loading' && (
        <div className="graph-empty">
          <div className="graph-empty-text">Chargement du graphe du programme…</div>
        </div>
      )}
      {status === 'empty' && (
        <div className="graph-empty">
          <div className="graph-empty-icon">⬡</div>
          <div className="graph-empty-text">Aucun cours trouvé pour ce programme.</div>
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
