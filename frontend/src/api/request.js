import axios from 'axios'
import { ElNotification } from 'element-plus'

// ---------------------------------------------------------------------------
// 断线检测与自动重连
// ---------------------------------------------------------------------------
let _offlineBannerVisible = false
let _healthCheckTimer = null

function _showOfflineBanner() {
  if (_offlineBannerVisible) return
  _offlineBannerVisible = true
  ElNotification({
    title: '服务连接中断',
    message: '后台服务无法连接，系统正在尝试重新连接…',
    type: 'error',
    duration: 0, // 不自动关闭
    customClass: 'offline-notification',
  })
  _startHealthCheck()
}

function _startHealthCheck() {
  if (_healthCheckTimer) return
  _healthCheckTimer = setInterval(async () => {
    try {
      await axios.get('/api/auth/login', { timeout: 3000 })
      // 返回 405 也说明服务在线
      _clearOffline()
    } catch (err) {
      if (err.response) {
        // 有 HTTP 响应，说明后端已恢复
        _clearOffline()
      }
    }
  }, 5000)
}

function _clearOffline() {
  if (!_offlineBannerVisible) return
  _offlineBannerVisible = false
  if (_healthCheckTimer) {
    clearInterval(_healthCheckTimer)
    _healthCheckTimer = null
  }
  ElNotification.closeAll()
  ElNotification({
    title: '服务已恢复',
    message: '后台服务已重新连接，可正常使用',
    type: 'success',
    duration: 3000,
  })
}

// ---------------------------------------------------------------------------

const service = axios.create({
  baseURL: '/api',
  timeout: 15000 // 超时从5s增加到15s，避免复杂操作误超时
})

// Request interceptor
service.interceptors.request.use(
  config => {
    const token = localStorage.getItem('token')
    if (token) {
      config.headers['Authorization'] = 'Bearer ' + token
    }
    return config
  },
  error => {
    console.log(error)
    return Promise.reject(error)
  }
)

// Response interceptor
service.interceptors.response.use(
  response => {
    const res = response.data
    // Handle binary data (blob)
    if (response.config.responseType === 'blob') {
      return res
    }
    // Assuming backend returns { code: 200, data: ... } or just data
    return res
  },
  error => {
    console.log('err' + error)
    if (error.response) {
        if (error.response.status === 401) {
            const requestUrl = (error.config && error.config.url) ? String(error.config.url) : ''
            const isLoginRequest = requestUrl.includes('/auth/login')
            const isOnLoginPage = window.location.pathname === '/login'
            if (!isLoginRequest && !isOnLoginPage) {
                // 只在确认是认证失败时才清除token
                const errorData = error.response.data
                if (errorData && (errorData.msg === 'Bad username or password' || errorData.msg === 'Token has expired')) {
                    localStorage.removeItem('token')
                    localStorage.removeItem('user')
                    window.location.href = '/login'
                } else {
                    // 其他401错误可能是权限问题，不清除token
                    return Promise.reject({ msg: '权限不足', code: 401 })
                }
            }
        }
        const payload = error.response.data
        if (payload && typeof payload === 'object' && !Array.isArray(payload)) {
            return Promise.reject({ ...payload, code: error.response.status })
        }
        return Promise.reject({ msg: payload || 'Request failed', code: error.response.status })
    }
    // 网络错误处理，不清除token，触发断线检测
    const rawMessage = (error && error.message) ? String(error.message) : ''
    const isTimeout = rawMessage.toLowerCase().includes('timeout')
    const isNetworkError = rawMessage.toLowerCase().includes('network error')

    // 网络完全断开时触发断线检测
    if (isNetworkError) {
      _showOfflineBanner()
    }

    const msg = isTimeout
      ? '请求超时，请稍后重试'
      : '无法连接后端服务，请确认后端已启动（http://127.0.0.1:5000）'
    return Promise.reject({ msg, code: 0, detail: rawMessage })
  }
)

export default service
