import axios from 'axios'

type ApiErrorDetail = {
  msg?: string
}

export function extractApiErrorMessage(error: unknown): string {
  if (!axios.isAxiosError(error)) {
    return 'Request failed'
  }

  const data = error.response?.data
  if (typeof data === 'string' && data.trim()) {
    return data
  }
  if (typeof data?.detail === 'string' && data.detail.trim()) {
    return data.detail
  }
  if (Array.isArray(data?.detail)) {
    const details = data.detail
      .map((entry: ApiErrorDetail | string) => typeof entry === 'string' ? entry : entry?.msg)
      .filter((entry: string | undefined): entry is string => Boolean(entry))
    if (details.length > 0) {
      return details.join('; ')
    }
  }
  if (typeof data?.message === 'string' && data.message.trim()) {
    return data.message
  }
  if (error.code === 'ERR_NETWORK') {
    return 'Unable to reach server'
  }
  if (error.response?.status) {
    return `Request failed (${error.response.status})`
  }
  return error.message || 'Request failed'
}

export function getSuccessToastMessage(method?: string, url?: string): string | null {
  const normalizedMethod = method?.toLowerCase()
  if (!normalizedMethod || normalizedMethod === 'get') {
    return null
  }

  if (normalizedMethod === 'delete') {
    return 'Deleted successfully'
  }
  if (normalizedMethod === 'put' || normalizedMethod === 'patch') {
    return 'Saved successfully'
  }
  if (normalizedMethod === 'post') {
    if (url?.includes('/imports/')) {
      return 'Import completed'
    }
    if (url?.includes('/generate')) {
      return 'Generation completed'
    }
    if (url?.includes('/run')) {
      return 'Run completed'
    }
    return 'Saved successfully'
  }

  return 'Request completed'
}