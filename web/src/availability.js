export function buildOutgoing(edges) {
  const out = {}
  edges.forEach(e => {
    if (e.relation_type === 'equivalent') return
    if (!out[e.source]) out[e.source] = []
    out[e.source].push(e.target)
  })
  return out
}

export function isSatisfied(nodeId, nodeById, outgoing, completedSet) {
  const node = nodeById[nodeId]
  if (!node) return false
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

export function computeAvailability(rawData, completedSigles) {
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
