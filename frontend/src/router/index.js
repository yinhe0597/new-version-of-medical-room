import { createRouter, createWebHistory } from 'vue-router'
import Login from '@/views/Login.vue'

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
    children: [
      {
        path: 'patient',
        name: 'PatientSearch',
        component: () => import('@/views/doctor/PatientSearch.vue')
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
      },
      {
        path: '',
        redirect: '/doctor/patient'
      }
    ]
  },
  {
    path: '/nurse',
    name: 'NurseDashboard',
    component: () => import('@/views/nurse/Dashboard.vue'),
    meta: { role: 'nurse' },
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
        path: '',
        redirect: '/nurse/pending'
      }
    ]
  },
  {
    path: '/admin',
    name: 'AdminDashboard',
    component: () => import('@/views/admin/Dashboard.vue'),
    meta: { role: 'admin' },
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
        path: 'statistics',
        name: 'Statistics',
        component: () => import('@/views/admin/Statistics.vue')
      },
      {
        path: 'settings',
        name: 'SystemSettings',
        component: () => import('@/views/admin/SystemSettings.vue')
      },
      {
        path: '',
        redirect: '/admin/drugs'
      }
    ]
  }
]

const router = createRouter({
  history: createWebHistory(),
  routes
})

router.beforeEach((to, from, next) => {
  const token = localStorage.getItem('token')
  const user = JSON.parse(localStorage.getItem('user'))
  
  if (to.path === '/login') {
    if (token) {
        // Redirect based on role
        if (user.role === 'doctor') next('/doctor')
        else if (user.role === 'nurse') next('/nurse')
        else if (user.role === 'admin') next('/admin')
        else next()
    } else {
        next()
    }
  } else {
    if (!token) {
      next('/login')
    } else {
      // Check role
      if (to.meta.role && to.meta.role !== user.role) {
        next('/login') // Unauthorized
      } else {
        next()
      }
    }
  }
})

export default router
