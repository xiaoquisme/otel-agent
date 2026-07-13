import { createBrowserRouter } from 'react-router-dom'
import DashboardLayout from './layouts/DashboardLayout'
import ListPage from './pages/ListPage'
import DetailPage from './pages/DetailPage'

const router = createBrowserRouter([
  {
    path: '/',
    element: <DashboardLayout />,
    children: [
      { index: true, element: <ListPage /> },
      { path: 'request/:id', element: <DetailPage /> },
    ],
  },
])

export default router
