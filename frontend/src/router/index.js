import { createRouter, createWebHistory } from 'vue-router'
import Login from '@/views/Login.vue'

const safeJsonParse = value => {
  try {
    return value ? JSON.parse(value) : null
  } catch (e) {
    return null
  }
}

const resolveHomeByRole = role => {
  if (role === 'doctor') return '/doctor'
  if (role === 'nurse') return '/nurse'
  if (role === 'admin') return '/admin'
  return null
}

const routes = [
  {
    path: '/login',
    name: 'Login',
    component: Login
  },
  {
    path: '/',
    redirect: '/login'
  },
  {
    path: '/doctor',
    name: 'DoctorDashboard',
    component: () => import('@/views/doctor/Dashboard.vue'),
    meta: { role: 'doctor' },
    redirect: '/doctor/patient',
    children: [
      {
        path: 'patient',
        name: 'PatientSearch',
        component: () => import('@/views/doctor/PatientSearch.vue')
      },
      {
        path: 'direct-purchase',
        name: 'DirectPurchase',
        component: () => import('@/views/doctor/DirectPurchase.vue')
      },
      {
        path: 'visit',
        name: 'VisitForm',
        component: () => import('@/views/doctor/VisitForm.vue')
      },
      {
        path: 'history',
        name: 'PrescriptionHistory',
        component: () => import('@/views/doctor/PrescriptionHistory.vue')
      }
    ]
  },
  {
    path: '/nurse',
    name: 'NurseDashboard',
    component: () => import('@/views/nurse/Dashboard.vue'),
    meta: { role: 'nurse' },
    redirect: '/nurse/pending',
    children: [
      {
        path: 'pending',
        name: 'PendingList',
        component: () => import('@/views/nurse/PendingList.vue')
      },
      {
        path: 'execute/:visitId',
        name: 'ExecutePrescription',
        component: () => import('@/views/nurse/ExecutePrescription.vue')
      },
      {
        path: 'inventory',
        name: 'Inventory',
        component: () => import('@/views/nurse/Inventory.vue')
      },
      {
        path: 'drugs',
        name: 'NurseDrugManagement',
        component: () => import('@/views/nurse/DrugManagement.vue')
      },
      {
        path: 'statistics',
        name: 'NurseStatistics',
        component: () => import('@/views/nurse/Statistics.vue')
      }
    ]
  },
  {
    path: '/admin',
    name: 'AdminDashboard',
    component: () => import('@/views/admin/Dashboard.vue'),
    meta: { role: 'admin' },
    redirect: '/admin/drugs',
    children: [
      {
        path: 'users',
        name: 'UserManagement',
        component: () => import('@/views/admin/UserManagement.vue')
      },
      {
        path: 'drugs',
        name: 'DrugManagement',
        component: () => import('@/views/admin/DrugManagement.vue')
      },
      {
        path: 'patients',
        name: 'PatientManagement',
        component: () => import('@/views/admin/PatientManagement.vue')
      },
      {
        path: 'statistics',
        name: 'Statistics',
        component: () => import('@/views/admin/Statistics.vue')
      },
      {
        path: 'settings',
        name: 'SystemSettings',
        component: () => import('@/views/admin/SystemSettings.vue')
      }
    ]
  }
]

const router = createRouter({
  history: createWebHistory(),
  routes
})

router.beforeEach(to => {
  const token = localStorage.getItem('token')
  const user = safeJsonParse(localStorage.getItem('user')) || {}

  if (to.path === '/login') {
    if (token) {
      const target = resolveHomeByRole(user.role)
      if (target) return target
    }
    return true
  }

  if (!token) return '/login'
  if (to.meta.role && to.meta.role !== user.role) return '/login'

  return true
})

export default router
