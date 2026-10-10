import type { AskRequest, AskResponse, HistoryRecord, LlmConfig, LlmConfigPayload, LlmStatus, SourceItem } from './types'

const API_BASE = import.meta.env.VITE_API_BASE || '/api'

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, options)
  const contentType = response.headers.get('content-type') || ''
  const payload = contentType.includes('application/json') ? await response.json() : await response.text()

  if (!response.ok) {
    const message = typeof payload === 'object' && payload && 'detail' in payload ? String(payload.detail) : String(payload)
    throw new Error(message || `请求失败：${response.status}`)
  }

  return payload as T
}

export function getHealth() {
  return request<{ status: string }>('/health')
}

export function getSources() {
  return request<SourceItem[]>('/sources')
}

export function uploadDocument(file: File) {
  const data = new FormData()
  data.append('file', file)
  return request<{ source: string; chunks: number }>('/upload', {
    method: 'POST',
    body: data,
  })
}

export function askQuestion(payload: AskRequest) {
  return request<AskResponse>('/ask', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
}

export function deleteSource(source: string) {
  return request<{ source: string; deleted: number }>(`/sources/${encodeURIComponent(source)}`, {
    method: 'DELETE',
  })
}

export function getHistory(limit = 20) {
  return request<HistoryRecord[]>(`/history?limit=${limit}`)
}

export function clearHistory() {
  return request<{ status: string }>('/history', { method: 'DELETE' })
}

export function getLlmStatus() {
  return request<LlmStatus>('/llm/status')
}

export function getLlmConfigs() {
  return request<LlmConfig[]>('/llm/configs')
}

export function createLlmConfig(payload: LlmConfigPayload) {
  return request<LlmConfig>('/llm/configs', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
}

export function activateLlmConfig(configId: string) {
  return request<LlmConfig>(`/llm/configs/${encodeURIComponent(configId)}/activate`, {
    method: 'POST',
  })
}

export function deleteLlmConfig(configId: string) {
  return request<{ id: string; deleted: number }>(`/llm/configs/${encodeURIComponent(configId)}`, {
    method: 'DELETE',
  })
}

export function testLlm(configId?: string) {
  return request<{ status: string; message: string }>('/llm/test', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ config_id: configId || null }),
  })
}
