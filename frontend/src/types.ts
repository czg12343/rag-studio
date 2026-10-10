export type SearchMode = 'hybrid' | 'vector' | 'keyword'

export interface SourceItem {
  source: string
  chunks: number
  pages?: number
  sections?: number
}

export interface Citation {
  index: number
  source: string
  chunk_index: number
  content: string
  score: number
  page: number
  section: string
  char_start: number
  char_end: number
  retrieval_mode: string
}

export interface AskRequest {
  question: string
  top_k: number
  search_mode: SearchMode
  candidate_k: number
  rewrite_query: boolean
  source_filter?: string | null
}

export interface AskResponse {
  question: string
  rewritten_question: string
  search_mode: SearchMode
  confidence: 'high' | 'medium' | 'low'
  answer: string
  citations: Citation[]
}

export interface HistoryRecord {
  id: number
  question: string
  answer: string
  sources: Citation[]
  create_time: string
}

export interface LlmStatus {
  has_api_key: boolean
  has_openai_package: boolean
  base_url: string
  model: string
  active_config_id: string
  active_config_name: string
}

export interface LlmConfig {
  id: string
  name: string
  api_key: string
  base_url: string
  model: string
  active: boolean
}

export interface LlmConfigPayload {
  name: string
  api_key: string
  base_url: string
  model: string
  active: boolean
}
