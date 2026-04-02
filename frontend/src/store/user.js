import { defineStore } from 'pinia'
import request from '@/api/request'

export const useUserStore = defineStore('user', {
  state: () => ({
    token: localStorage.getItem('token') || '',
    userInfo: JSON.parse(localStorage.getItem('user')) || {}
  }),
  actions: {
    async login(username, password) {
      try {
        const res = await request.post('/auth/login', { username, password })
        this.token = res.access_token
        this.userInfo = res.user
        
        localStorage.setItem('token', res.access_token)
        localStorage.setItem('user', JSON.stringify(res.user))
        return res
      } catch (error) {
        throw error
      }
    },
    logout() {
      this.token = ''
      this.userInfo = {}
      localStorage.removeItem('token')
      localStorage.removeItem('user')
    }
  }
})
