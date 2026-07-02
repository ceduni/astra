import { useEffect, useState } from 'react'
import ExplorationPage from './ExplorationPage'
import AdminPanel from './AdminPanel'

export default function App() {
  const [showAdmin, setShowAdmin] = useState(false)

  const [completed, setCompleted] = useState(() => {
    try { return JSON.parse(localStorage.getItem('completed') || '[]') } catch { return [] }
  })
  useEffect(() => {
    localStorage.setItem('completed', JSON.stringify(completed))
  }, [completed])

  const [homeUniversite, setHomeUniversite] = useState(() =>
    localStorage.getItem('homeUniversite') || null
  )
  useEffect(() => {
    homeUniversite
      ? localStorage.setItem('homeUniversite', homeUniversite)
      : localStorage.removeItem('homeUniversite')
  }, [homeUniversite])

  function markCompleted(course) {
    setCompleted(prev => prev.some(c => c.sigle === course.sigle) ? prev : [...prev, course])
  }

  function removeCourse(sigle) {
    setCompleted(prev => prev.filter(c => c.sigle !== sigle))
  }

  return (
    <div className="app-shell">
      <nav className="app-tabbar">
        <span className="app-brand">Astra</span>
        <button
          className={`tab-btn-admin${showAdmin ? ' active' : ''}`}
          onClick={() => setShowAdmin(v => !v)}
        >
          Admin
        </button>
      </nav>

      <div className="app-content">
        {showAdmin ? (
          <AdminPanel onBack={() => setShowAdmin(false)} />
        ) : (
          <ExplorationPage
            completed={completed}
            onAddCompleted={markCompleted}
            onRemoveCompleted={removeCourse}
            homeUniversite={homeUniversite}
            onSetHome={setHomeUniversite}
          />
        )}
      </div>
    </div>
  )
}
