import axios from 'axios'

const service = axios.create({
  baseURL: '/api', // Proxy will handle this
  timeout: 5000
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
    // 网络错误处理，不清除token
    const rawMessage = (error && error.message) ? String(error.message) : ''
    const isTimeout = rawMessage.toLowerCase().includes('timeout')
    const msg = isTimeout
      ? '请求超时，请稍后重试'
      : '无法连接后端服务，请确认后端已启动（http://127.0.0.1:5000）'
    return Promise.reject({ msg, code: 0, detail: rawMessage })
  }
)

export default service
