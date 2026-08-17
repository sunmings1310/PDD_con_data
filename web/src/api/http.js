import axios from 'axios'
import { ElMessage } from 'element-plus'
import router from '@/router'

const http = axios.create({
  baseURL: '/',
  timeout: 60000,
})

http.interceptors.request.use((config) => {
  const token = localStorage.getItem('sjzq_token')
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  const enterpriseId = localStorage.getItem('sjzq_enterprise_id')
  const workspaceId = localStorage.getItem('sjzq_workspace_id')
  if (enterpriseId) config.headers['X-Enterprise-Id'] = enterpriseId
  if (workspaceId) config.headers['X-Workspace-Id'] = workspaceId
  return config
})

http.interceptors.response.use(
  (res) => {
    const data = res.data
    if (data && typeof data.ok === 'boolean' && !data.ok) {
      ElMessage.error(data.message || '请求失败')
      return Promise.reject(data)
    }
    return data
  },
  (err) => {
    const status = err.response?.status
    const detail = err.response?.data?.detail || err.message
    if (status === 401) {
      localStorage.removeItem('sjzq_token')
      router.replace('/login')
    }
    ElMessage.error(typeof detail === 'string' ? detail : '网络异常')
    return Promise.reject(err)
  },
)

export default http
