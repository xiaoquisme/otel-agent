import { createBrowserRouter } from 'react-router-dom'
import DashboardLayout from './layouts/DashboardLayout'
import ListPage from './pages/ListPage'
import DetailPage from './pages/DetailPage'
import UsagePage from './pages/UsagePage'

const router = createBrowserRouter([
  {
    path: '/',
    element: <DashboardLayout />,
    children: [
      { index: true, element: <ListPage /> },
      { path: 'request/:id', element: <DetailPage /> },
      { path: 'usage', element: <UsagePage /> },
    ],
  },
])

export default router
