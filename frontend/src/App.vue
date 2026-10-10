<template>
  <div class="app-shell">
    <div class="ambient-grid" />
    <aside class="sidebar">
      <div class="brand">
        <div class="brand-mark">R</div>
        <div>
          <h1>RAG Studio</h1>
          <p>文档知识库工作台</p>
        </div>
      </div>

      <el-menu class="nav-menu" :default-active="activeView" @select="activeView = $event as ViewKey">
        <el-menu-item index="qa">
          <el-icon><ChatDotRound /></el-icon>
          <span>智能问答</span>
        </el-menu-item>
        <el-menu-item index="documents">
          <el-icon><FolderOpened /></el-icon>
          <span>知识库</span>
        </el-menu-item>
        <el-menu-item index="history">
          <el-icon><Clock /></el-icon>
          <span>历史记录</span>
        </el-menu-item>
        <el-menu-item index="settings">
          <el-icon><Setting /></el-icon>
          <span>模型配置</span>
        </el-menu-item>
      </el-menu>

      <div class="sidebar-status">
        <div class="status-row">
          <span>后端服务</span>
          <el-tag :type="backendOnline ? 'success' : 'danger'" round>{{ backendOnline ? '在线' : '离线' }}</el-tag>
        </div>
        <div class="status-row">
          <span>检索模式</span>
          <el-tag type="primary" round>{{ searchModeLabel }}</el-tag>
        </div>
      </div>
    </aside>

    <main class="workspace">
      <header class="topbar">
        <div>
          <p class="eyebrow">{{ viewMeta.eyebrow }}</p>
          <h2>{{ viewMeta.title }}</h2>
        </div>
        <div class="topbar-actions">
          <div class="system-chip">
            <span class="pulse-dot" />
            <span>{{ backendOnline ? 'API Online' : 'API Offline' }}</span>
          </div>
          <div class="system-chip muted">
            <span>{{ totalChunks }}</span>
            <span>Chunks</span>
          </div>
          <el-button :icon="Refresh" @click="refreshAll">刷新</el-button>
          <el-button type="primary" :icon="UploadFilled" @click="activeView = 'documents'">上传文档</el-button>
        </div>
      </header>

      <section class="stats-grid">
        <div class="stat-tile">
          <span>文档</span>
          <strong>{{ sources.length }}</strong>
        </div>
        <div class="stat-tile">
          <span>知识片段</span>
          <strong>{{ totalChunks }}</strong>
        </div>
        <div class="stat-tile">
          <span>识别页数</span>
          <strong>{{ totalPages }}</strong>
        </div>
        <div class="stat-tile">
          <span>最近检索等级</span>
          <strong>{{ confidenceText(lastAnswer?.confidence) }}</strong>
        </div>
      </section>

      <section class="pipeline surface">
        <div class="pipeline-item active">
          <span>01</span>
          <strong>Parse</strong>
          <em>文档解析</em>
        </div>
        <div class="pipeline-line" />
        <div class="pipeline-item active">
          <span>02</span>
          <strong>Index</strong>
          <em>结构化切块</em>
        </div>
        <div class="pipeline-line" />
        <div class="pipeline-item active">
          <span>03</span>
          <strong>Retrieve</strong>
          <em>混合检索</em>
        </div>
        <div class="pipeline-line" />
        <div class="pipeline-item">
          <span>04</span>
          <strong>Answer</strong>
          <em>引用生成</em>
        </div>
      </section>

      <section v-if="activeView === 'qa'" class="qa-layout">
        <div class="question-panel surface">
          <div class="section-head">
            <div>
              <p class="eyebrow">Ask</p>
              <h3>向知识库提问</h3>
            </div>
            <el-tag type="success" effect="plain">Hybrid RAG</el-tag>
          </div>

          <el-input
            v-model="question"
            type="textarea"
            :rows="8"
            resize="none"
            placeholder="例如：这篇论文的核心创新点和实验结论是什么？"
          />

          <div class="prompt-chips">
            <button v-for="prompt in suggestedQuestions" :key="prompt" type="button" @click="question = prompt">
              {{ prompt }}
            </button>
          </div>

          <div class="query-toolbar">
            <el-select v-model="askOptions.source_filter" placeholder="全部文档" clearable>
              <el-option v-for="item in sources" :key="item.source" :label="item.source" :value="item.source" />
            </el-select>
            <el-button type="primary" :icon="Promotion" :loading="asking" @click="submitQuestion">生成回答</el-button>
          </div>

          <el-divider />

          <div class="config-grid">
            <label>
              <span>检索模式</span>
              <el-segmented
                v-model="askOptions.search_mode"
                :options="searchModeOptions"
              />
            </label>
            <label>
              <span>引用数 Top-K</span>
              <el-slider v-model="askOptions.top_k" :min="1" :max="10" />
            </label>
            <label>
              <span>候选召回数</span>
              <el-slider v-model="askOptions.candidate_k" :min="askOptions.top_k" :max="40" />
            </label>
            <label class="switch-line">
              <span>查询改写</span>
              <el-switch v-model="askOptions.rewrite_query" />
            </label>
          </div>
        </div>

        <div class="answer-panel surface">
          <div class="section-head">
            <div>
              <p class="eyebrow">Answer</p>
              <h3>回答与引用证据</h3>
            </div>
            <el-tag :type="confidenceType(lastAnswer?.confidence)" effect="plain" title="启发式检索等级，不代表回答正确概率">
              检索等级：{{ confidenceText(lastAnswer?.confidence) }}
            </el-tag>
          </div>

          <el-empty v-if="!lastAnswer" description="提交问题后，这里会显示回答和引用依据。" />

          <template v-else>
            <div v-if="lastAnswer.rewritten_question" class="rewrite-note">
              <strong>检索改写</strong>
              <span>{{ lastAnswer.rewritten_question }}</span>
            </div>

            <article class="answer-content">{{ lastAnswer.answer }}</article>

            <div class="citation-list">
              <div v-for="citation in lastAnswer.citations" :key="citation.index" class="citation-card">
                <div class="citation-top">
                  <strong>引用 {{ citation.index }}</strong>
                  <el-tag size="small">{{ citation.score }}</el-tag>
                </div>
                <p class="citation-source">
                  {{ citation.source }}
                  <span v-if="citation.page"> · 第 {{ citation.page }} 页</span>
                  <span v-if="citation.section"> · {{ citation.section }}</span>
                </p>
                <p class="citation-meta">
                  片段 {{ citation.chunk_index }} · 字符 {{ citation.char_start }}-{{ citation.char_end }} · {{ citation.retrieval_mode }}
                </p>
                <el-collapse>
                  <el-collapse-item title="查看原文片段" :name="String(citation.index)">
                    <p class="citation-text">{{ citation.content }}</p>
                  </el-collapse-item>
                </el-collapse>
              </div>
            </div>
          </template>
        </div>
      </section>

      <section v-if="activeView === 'documents'" class="documents-layout">
        <div class="surface upload-panel">
          <div class="section-head">
            <div>
              <p class="eyebrow">Upload</p>
              <h3>文档上传</h3>
            </div>
          </div>
          <el-upload
            drag
            multiple
            :auto-upload="false"
            :file-list="pendingFiles"
            :on-change="onFileChange"
            :on-remove="onFileRemove"
            accept=".pdf,.docx,.txt,.md,.markdown"
          >
            <el-icon class="upload-icon"><UploadFilled /></el-icon>
            <div class="el-upload__text">拖拽文件到这里，或点击选择</div>
            <template #tip>
              <div class="el-upload__tip">支持 PDF、Word、TXT、Markdown。上传后会自动解析并写入索引。</div>
            </template>
          </el-upload>
          <el-button class="upload-action" type="primary" :icon="Upload" :loading="uploading" @click="uploadPendingFiles">
            构建索引
          </el-button>
        </div>

        <div class="surface table-panel">
          <div class="section-head">
            <div>
              <p class="eyebrow">Library</p>
              <h3>知识库文档</h3>
            </div>
            <el-button :icon="Refresh" @click="loadSources">刷新列表</el-button>
          </div>
          <el-table :data="sources" height="440" empty-text="暂无已索引文档">
            <el-table-column prop="source" label="文档" min-width="240" />
            <el-table-column prop="chunks" label="片段" width="100" />
            <el-table-column prop="pages" label="页数" width="100" />
            <el-table-column prop="sections" label="章节片段" width="110" />
            <el-table-column label="操作" width="120" fixed="right">
              <template #default="{ row }">
                <el-button type="danger" link :icon="Delete" @click="removeSource(row.source)">删除</el-button>
              </template>
            </el-table-column>
          </el-table>
        </div>
      </section>

      <section v-if="activeView === 'history'" class="surface">
        <div class="section-head">
          <div>
            <p class="eyebrow">History</p>
            <h3>问答记录</h3>
          </div>
          <el-button type="danger" plain :icon="Delete" @click="removeHistory">清空</el-button>
        </div>
        <el-timeline v-if="history.length">
          <el-timeline-item v-for="record in history" :key="record.id" :timestamp="record.create_time" placement="top">
            <div class="history-item">
              <strong>{{ record.question }}</strong>
              <p>{{ record.answer }}</p>
              <div class="history-sources">
                <el-tag v-for="source in record.sources.slice(0, 3)" :key="`${record.id}-${source.index}`" size="small">
                  {{ source.source }}
                </el-tag>
              </div>
            </div>
          </el-timeline-item>
        </el-timeline>
        <el-empty v-else description="暂无历史记录" />
      </section>

      <section v-if="activeView === 'settings'" class="settings-grid">
        <div class="surface">
          <div class="section-head">
            <div>
              <p class="eyebrow">Model</p>
              <h3>模型配置</h3>
            </div>
            <el-button type="primary" :icon="Connection" :loading="testingLlm" @click="runLlmTest">连接测试</el-button>
          </div>

          <div class="status-list">
            <div>
              <span>当前配置</span>
              <el-tag :type="llmStatus?.active_config_id ? 'success' : 'info'">
                {{ llmStatus?.active_config_name || '.env' }}
              </el-tag>
            </div>
            <div>
              <span>OpenAI SDK</span>
              <el-tag :type="llmStatus?.has_openai_package ? 'success' : 'danger'">{{ llmStatus?.has_openai_package ? '已安装' : '缺失' }}</el-tag>
            </div>
            <div>
              <span>Base URL</span>
              <code>{{ llmStatus?.base_url || '-' }}</code>
            </div>
            <div>
              <span>模型</span>
              <code>{{ llmStatus?.model || '-' }}</code>
            </div>
          </div>

          <el-divider />

          <el-table :data="llmConfigs" empty-text="暂无前端配置，将使用 .env">
            <el-table-column prop="name" label="名称" min-width="130" />
            <el-table-column prop="model" label="模型" min-width="150" />
            <el-table-column prop="base_url" label="Base URL" min-width="220" />
            <el-table-column prop="api_key" label="API Key" width="130" />
            <el-table-column label="状态" width="90">
              <template #default="{ row }">
                <el-tag v-if="row.active" type="success">启用中</el-tag>
                <el-tag v-else type="info">备用</el-tag>
              </template>
            </el-table-column>
            <el-table-column label="操作" width="170" fixed="right">
              <template #default="{ row }">
                <el-button type="primary" link :disabled="row.active" @click="setActiveConfig(row.id)">启用</el-button>
                <el-button type="danger" link @click="removeLlmConfig(row.id)">删除</el-button>
              </template>
            </el-table-column>
          </el-table>
        </div>

        <div class="surface">
          <div class="section-head">
            <div>
              <p class="eyebrow">Provider</p>
              <h3>新增 API 配置</h3>
            </div>
          </div>
          <el-form class="config-form" label-position="top">
            <el-form-item label="配置名称">
              <el-input v-model="newConfig.name" placeholder="例如：Groq 免费额度" />
            </el-form-item>
            <el-form-item label="API Key">
              <el-input v-model="newConfig.api_key" type="password" show-password placeholder="sk-..." />
            </el-form-item>
            <el-form-item label="Base URL">
              <el-input v-model="newConfig.base_url" placeholder="https://api.groq.com/openai/v1" />
            </el-form-item>
            <el-form-item label="模型名称">
              <el-input v-model="newConfig.model" placeholder="llama-3.1-8b-instant" />
            </el-form-item>
            <el-form-item>
              <el-checkbox v-model="newConfig.active">保存后立即启用</el-checkbox>
            </el-form-item>
            <el-button type="primary" class="full-width" :loading="savingConfig" @click="saveNewConfig">保存配置</el-button>
          </el-form>

          <div class="provider-presets">
            <button type="button" @click="applyPreset('deepseek')">DeepSeek</button>
            <button type="button" @click="applyPreset('groq')">Groq</button>
            <button type="button" @click="applyPreset('gemini')">Gemini</button>
          </div>
        </div>
      </section>
    </main>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox, type UploadFile, type UploadFiles } from 'element-plus'
import {
  ChatDotRound,
  Clock,
  Connection,
  Delete,
  FolderOpened,
  Promotion,
  Refresh,
  Setting,
  Upload,
  UploadFilled,
} from '@element-plus/icons-vue'
import {
  activateLlmConfig,
  askQuestion,
  clearHistory,
  createLlmConfig,
  deleteLlmConfig,
  deleteSource,
  getHealth,
  getHistory,
  getLlmConfigs,
  getLlmStatus,
  getSources,
  testLlm,
  uploadDocument,
} from './api'
import type { AskResponse, HistoryRecord, LlmConfig, LlmConfigPayload, LlmStatus, SearchMode, SourceItem } from './types'

type ViewKey = 'qa' | 'documents' | 'history' | 'settings'

const activeView = ref<ViewKey>('qa')
const backendOnline = ref(false)
const sources = ref<SourceItem[]>([])
const history = ref<HistoryRecord[]>([])
const llmStatus = ref<LlmStatus | null>(null)
const llmConfigs = ref<LlmConfig[]>([])
const lastAnswer = ref<AskResponse | null>(null)
const question = ref('')
const asking = ref(false)
const uploading = ref(false)
const testingLlm = ref(false)
const savingConfig = ref(false)
const pendingFiles = ref<UploadFile[]>([])

const askOptions = reactive({
  search_mode: 'hybrid' as SearchMode,
  top_k: 5,
  candidate_k: 20,
  rewrite_query: false,
  source_filter: null as string | null,
})

const newConfig = reactive<LlmConfigPayload>({
  name: '',
  api_key: '',
  base_url: 'https://api.deepseek.com',
  model: 'deepseek-chat',
  active: true,
})

const searchModeOptions = [
  { label: '混合', value: 'hybrid' },
  { label: '向量', value: 'vector' },
  { label: '关键词', value: 'keyword' },
]

const suggestedQuestions = [
  '总结文档的核心观点和关键结论',
  '这份资料里有哪些创新点？',
  '列出实验结果或案例中的主要证据',
  '哪些内容可以作为论文/汇报亮点？',
]

const viewMeta = computed(() => {
  const map = {
    qa: { eyebrow: 'RAG Question Answering', title: '智能问答' },
    documents: { eyebrow: 'Knowledge Base', title: '知识库管理' },
    history: { eyebrow: 'Conversation Records', title: '历史记录' },
    settings: { eyebrow: 'LLM Diagnostics', title: '模型配置' },
  }
  return map[activeView.value]
})

const searchModeLabel = computed(() => labelSearchMode(askOptions.search_mode))
const totalChunks = computed(() => sources.value.reduce((sum, item) => sum + Number(item.chunks || 0), 0))
const totalPages = computed(() => sources.value.reduce((sum, item) => sum + Number(item.pages || 0), 0))

onMounted(() => {
  refreshAll()
})

async function refreshAll() {
  await Promise.allSettled([checkHealth(), loadSources(), loadHistory(), loadLlmStatus(), loadLlmConfigs()])
}

async function checkHealth() {
  try {
    await getHealth()
    backendOnline.value = true
  } catch {
    backendOnline.value = false
  }
}

async function loadSources() {
  sources.value = await getSources()
}

async function loadHistory() {
  history.value = await getHistory(30)
}

async function loadLlmStatus() {
  llmStatus.value = await getLlmStatus()
}

async function loadLlmConfigs() {
  llmConfigs.value = await getLlmConfigs()
}

async function submitQuestion() {
  const trimmed = question.value.trim()
  if (!trimmed) {
    ElMessage.warning('请输入问题')
    return
  }
  asking.value = true
  try {
    lastAnswer.value = await askQuestion({
      question: trimmed,
      top_k: askOptions.top_k,
      search_mode: askOptions.search_mode,
      candidate_k: askOptions.candidate_k,
      rewrite_query: askOptions.rewrite_query,
      source_filter: askOptions.source_filter,
    })
    await loadHistory()
  } catch (error) {
    ElMessage.error(errorMessage(error))
  } finally {
    asking.value = false
  }
}

function onFileChange(_file: UploadFile, files: UploadFiles) {
  pendingFiles.value = files
}

function onFileRemove(_file: UploadFile, files: UploadFiles) {
  pendingFiles.value = files
}

async function uploadPendingFiles() {
  const files: File[] = []
  for (const item of pendingFiles.value) {
    if (item.raw) {
      files.push(item.raw as File)
    }
  }
  if (!files.length) {
    ElMessage.warning('请选择文档')
    return
  }
  uploading.value = true
  try {
    for (const file of files) {
      await uploadDocument(file)
    }
    pendingFiles.value = []
    await loadSources()
    ElMessage.success('索引构建完成')
  } catch (error) {
    ElMessage.error(errorMessage(error))
  } finally {
    uploading.value = false
  }
}

async function removeSource(source: string) {
  await ElMessageBox.confirm(`确认删除「${source}」的索引？`, '删除索引', { type: 'warning' })
  await deleteSource(source)
  await loadSources()
  ElMessage.success('已删除索引')
}

async function removeHistory() {
  await ElMessageBox.confirm('确认清空全部问答历史？', '清空历史', { type: 'warning' })
  await clearHistory()
  history.value = []
  ElMessage.success('历史记录已清空')
}

async function runLlmTest() {
  testingLlm.value = true
  try {
    const result = await testLlm()
    ElMessage.success(result.message || '连接成功')
    await loadLlmStatus()
  } catch (error) {
    ElMessage.error(errorMessage(error))
  } finally {
    testingLlm.value = false
  }
}

async function saveNewConfig() {
  if (!newConfig.name.trim() || !newConfig.api_key.trim() || !newConfig.base_url.trim() || !newConfig.model.trim()) {
    ElMessage.warning('请完整填写模型配置')
    return
  }
  savingConfig.value = true
  try {
    await createLlmConfig({ ...newConfig })
    ElMessage.success('模型配置已保存')
    newConfig.name = ''
    newConfig.api_key = ''
    newConfig.active = false
    await Promise.all([loadLlmConfigs(), loadLlmStatus()])
  } catch (error) {
    ElMessage.error(errorMessage(error))
  } finally {
    savingConfig.value = false
  }
}

async function setActiveConfig(configId: string) {
  try {
    await activateLlmConfig(configId)
    await Promise.all([loadLlmConfigs(), loadLlmStatus()])
    ElMessage.success('已切换当前模型配置')
  } catch (error) {
    ElMessage.error(errorMessage(error))
  }
}

async function removeLlmConfig(configId: string) {
  await ElMessageBox.confirm('确认删除这个模型配置？删除后无法恢复。', '删除模型配置', { type: 'warning' })
  await deleteLlmConfig(configId)
  await Promise.all([loadLlmConfigs(), loadLlmStatus()])
  ElMessage.success('模型配置已删除')
}

function applyPreset(provider: 'deepseek' | 'groq' | 'gemini') {
  const presets = {
    deepseek: {
      name: 'DeepSeek',
      base_url: 'https://api.deepseek.com',
      model: 'deepseek-chat',
    },
    groq: {
      name: 'Groq',
      base_url: 'https://api.groq.com/openai/v1',
      model: 'llama-3.1-8b-instant',
    },
    gemini: {
      name: 'Gemini',
      base_url: 'https://generativelanguage.googleapis.com/v1beta/openai/',
      model: 'gemini-2.5-flash',
    },
  }[provider]
  newConfig.name = presets.name
  newConfig.base_url = presets.base_url
  newConfig.model = presets.model
}

function labelSearchMode(mode: SearchMode) {
  return { hybrid: '混合', vector: '向量', keyword: '关键词' }[mode]
}

function confidenceText(confidence?: AskResponse['confidence']) {
  if (!confidence) return '待生成'
  return { high: '高', medium: '中', low: '低' }[confidence]
}

function confidenceType(confidence?: AskResponse['confidence']) {
  if (confidence === 'high') return 'success'
  if (confidence === 'low') return 'warning'
  return 'info'
}

function errorMessage(error: unknown) {
  return error instanceof Error ? error.message : String(error)
}
</script>
