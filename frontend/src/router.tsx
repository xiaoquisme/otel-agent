import { createBrowserRouter } from 'react-router-dom'
import DashboardLayout from './layouts/DashboardLayout'
import ListPage from './pages/ListPage'
import DetailPage from './pages/DetailPage'
import UsagePage from './pages/UsagePage'
import SessionsPage from './pages/SessionsPage'
import SessionPage from './pages/SessionPage'

const router = createBrowserRouter([
  {
    path: '/',
    element: <DashboardLayout />,
    children: [
      { index: true, element: <ListPage /> },
      { path: 'request/:id', element: <DetailPage /> },
      { path: 'sessions', element: <SessionsPage /> },
      { path: 'sessions/*', element: <SessionPage /> },
      { path: 'usage', element: <UsagePage /> },
    ],
  },
])

export default router
