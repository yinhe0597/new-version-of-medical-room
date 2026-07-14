import axios from 'axios'
import { ElNotification } from 'element-plus'

// ---------------------------------------------------------------------------
// 断线检测与自动重连
// ---------------------------------------------------------------------------
let _offlineBannerVisible = false
let _healthCheckTimer = null
let _authRedirectInProgress = false

const JWT_422_MESSAGE_PATTERNS = [
  /^not enough segments$/,
  /^signature verification failed$/,
  /^invalid (header|payload|crypto) (padding|string)(:.*)?$/,
  /^invalid token type\. token must be .+$/,
  /^missing claim: .+$/,
  /^subject must be a string$/,
  /^invalid audience$/,
  /^audience doesn't match$/,
  /^invalid issuer$/,
  /^the token is not yet valid \((iat|nbf)\)$/,
  /^token is missing the ".+" claim$/,
  /^only (refresh|non-refresh) tokens are allowed$/,
  /^fresh token required$/,
  /^algorithm not (allowed|supported)$/,
  /^the specified alg value is not allowed$/,
  /^(expiration time|issued at|not before) claim \((exp|iat|nbf)\) must be an integer\.?$/,
  /^audience claim \(aud\) must be a string or a list of strings$/,
  /^issuer claim \(iss\) must be a string$/
]

const _getErrorMessage = payload => {
  if (typeof payload === 'string') return payload
  if (!payload || typeof payload !== 'object' || Array.isArray(payload)) return ''
  return String(payload.msg || payload.message || payload.error || '')
}

const _normalizeErrorPayload = async payload => {
  if (typeof Blob === 'undefined' || !(payload instanceof Blob)) return payload

  try {
    const body = (await payload.text()).trim()
    if (!body) return ''
    if (payload.type.includes('application/json') || body.startsWith('{') || body.startsWith('[')) {
      try {
        return JSON.parse(body)
      } catch {
        return body
      }
    }
    return body
  } catch {
    return payload
  }
}

const _isJwtValidationError = (status, payload) => {
  if (status === 401) return true
  if (status !== 422 || !payload || typeof payload !== 'object' || Array.isArray(payload)) {
    return false
  }

  // Flask-JWT-Extended's default invalid-token response only contains its
  // error message. Business 422 responses may carry fields/details and must
  // remain visible to the page instead of forcing a logout.
  const keys = Object.keys(payload)
  const messageOnlyPayload = keys.length === 1 && keys[0] === 'msg'
  if (!messageOnlyPayload) return false

  const message = _getErrorMessage(payload).toLowerCase()
  return JWT_422_MESSAGE_PATTERNS.some(pattern => pattern.test(message))
}

export const handleAuthenticationFailure = ({ status, payload, requestUrl = '' }) => {
  if (String(requestUrl).includes('/auth/login') || !_isJwtValidationError(status, payload)) {
    return false
  }

  localStorage.removeItem('token')
  localStorage.removeItem('user')

  if (window.location.pathname !== '/login' && !_authRedirectInProgress) {
    _authRedirectInProgress = true
    window.location.replace('/login')
  }
  return true
}

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
      await axios.get('/api/health/ready', { timeout: 3000 })
      _clearOffline()
    } catch (err) {
      if (err.response && err.response.status < 500) {
        // 4xx 说明服务可达；5xx readiness 仍表示数据库不可用。
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
      return response.config.returnFullResponse ? response : res
    }
    // Assuming backend returns { code: 200, data: ... } or just data
    return res
  },
  async error => {
    console.log('err' + error)
    if (error.response) {
        const payload = await _normalizeErrorPayload(error.response.data)
        handleAuthenticationFailure({
          status: error.response.status,
          payload,
          requestUrl: error.config && error.config.url
        })
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
