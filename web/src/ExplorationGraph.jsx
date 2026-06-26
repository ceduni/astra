import { useEffect, useState } from 'react'
import ReactFlow, {
  Background,
  Controls,
  useNodesState,
  useEdgesState,
} from 'reactflow'
import 'reactflow/dist/style.css'
import { NODE_TYPES, applyLayout } from './graphShared'

const API = '/api'

export default function ExplorationGraph({ snapshot, onNodeClick }) {
  const [nodes, setNodes, onNodesChange] = useNodesState([])
  const [edges, setEdges, onEdgesChange] = useEdgesState([])
  const [status, setStatus] = useState('idle')

  useEffect(() => {
    if (!snapshot) { setNodes([]); setEdges([]); setStatus('idle'); return }

    let cancelled = false
    setStatus('loading')
    setNodes([])
    setEdges([])

    fetch(`${API}/courses/program-graph`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ uni: snapshot.homeUniversite, program: snapshot.program }),
    })
      .then(r => { if (!r.ok) throw new Error(r.status); return r.json() })
      .then(data => {
        if (cancelled) return
        if (!data.nodes.length) { setStatus('empty'); return }

        const completedSet = new Set(snapshot.completedSigles)
        const { rfNodes, rfEdges } = applyLayout(
          data.nodes,
          data.edges,
          completedSet,
          new Set(),  // no "root" highlighting in program view
          null,
        )
        setNodes(rfNodes)
        setEdges(rfEdges)
        setStatus('ready')
      })
      .catch(() => { if (!cancelled) setStatus('error') })

    return () => { cancelled = true }
  }, [snapshot]) // eslint-disable-line react-hooks/exhaustive-deps

  function handleNodeClick(_, node) {
    if (node.type !== 'course') return
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
