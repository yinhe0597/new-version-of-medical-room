<template>
  <div class="templates-container">
    <el-page-header @back="goBack" :content="pageTitle" />

    <el-card class="box-card">
      <div class="toolbar">
        <el-input
          v-model="keyword"
          placeholder="搜索标题/内容"
          clearable
          style="max-width: 320px"
          @keyup.enter="loadTemplates"
        />
        <div class="toolbar-right">
          <el-button @click="loadTemplates" :loading="loading">查询</el-button>
          <el-button type="primary" @click="openCreate">新增模板</el-button>
        </div>
      </div>

      <el-table :data="templates" border stripe size="small" v-loading="loading">
        <el-table-column prop="title" label="标题" width="220" />
        <el-table-column label="内容">
          <template #default="scope">
            <div class="content-preview">{{ scope.row.content }}</div>
          </template>
        </el-table-column>
        <el-table-column prop="updated_at" label="更新时间" width="170" />
        <el-table-column label="操作" width="160">
          <template #default="scope">
            <el-button link type="primary" @click="openEdit(scope.row)">编辑</el-button>
            <el-button link type="danger" @click="removeTemplate(scope.row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <el-dialog v-model="dialogVisible" :title="dialogTitle" width="700px">
      <el-form :model="form" label-position="top">
        <el-form-item label="标题">
          <el-input v-model="form.title" maxlength="200" show-word-limit />
        </el-form-item>
        <el-form-item label="内容">
          <el-input v-model="form.content" type="textarea" :rows="8" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false" :disabled="saving">取消</el-button>
        <el-button type="primary" @click="saveTemplate" :loading="saving">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import request from '@/api/request'
import { ElMessage, ElMessageBox } from 'element-plus'

const route = useRoute()
const router = useRouter()

const loading = ref(false)
const saving = ref(false)
const templates = ref([])
const keyword = ref('')

const dialogVisible = ref(false)
const form = ref({
  id: null,
  title: '',
  content: ''
})

const pageTitle = computed(() => route.meta.templateTitle || '模板管理')
const category = computed(() => route.meta.templateCategory)
const dialogTitle = computed(() => (form.value.id ? '编辑模板' : '新增模板'))

const goBack = () => {
  router.push('/doctor/patient')
}

const loadTemplates = async () => {
  if (!category.value) return
  loading.value = true
  try {
    const res = await request.get('/doctor/templates', {
      params: { category: category.value, q: keyword.value.trim() }
    })
    templates.value = (res.data || []).map(x => ({ ...x }))
  } catch (error) {
    ElMessage.error(error.msg || '加载模板失败')
  } finally {
    loading.value = false
  }
}

const openCreate = () => {
  form.value = { id: null, title: '', content: '' }
  dialogVisible.value = true
}

const openEdit = (row) => {
  form.value = { id: row.id, title: row.title, content: row.content }
  dialogVisible.value = true
}

const saveTemplate = async () => {
  if (!category.value) return
  const title = (form.value.title || '').trim()
  const content = (form.value.content || '').trim()
  if (!title) {
    ElMessage.warning('请输入标题')
    return
  }
  if (!content) {
    ElMessage.warning('请输入内容')
    return
  }

  saving.value = true
  try {
    if (form.value.id) {
      await request.put(`/doctor/templates/${form.value.id}`, { title, content })
      ElMessage.success('已保存')
    } else {
      await request.post('/doctor/templates', { category: category.value, title, content })
      ElMessage.success('已新增')
    }
    dialogVisible.value = false
    await loadTemplates()
  } catch (error) {
    ElMessage.error(error.msg || '保存失败')
  } finally {
    saving.value = false
  }
}

const removeTemplate = async (row) => {
  try {
    await ElMessageBox.confirm(`确认删除模板「${row.title}」？`, '删除确认', {
      type: 'warning',
      confirmButtonText: '删除',
      cancelButtonText: '取消',
      closeOnClickModal: false
    })
  } catch (e) {
    return
  }

  try {
    await request.delete(`/doctor/templates/${row.id}`)
    ElMessage.success('已删除')
    await loadTemplates()
  } catch (error) {
    ElMessage.error(error.msg || '删除失败')
  }
}

watch(() => route.fullPath, () => {
  keyword.value = ''
  loadTemplates()
})

onMounted(() => {
  loadTemplates()
})
</script>

<style scoped>
.templates-container {
  max-width: 1100px;
  margin: 0 auto;
}
.box-card {
  margin-top: 16px;
}
.toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
  gap: 12px;
}
.toolbar-right {
  display: flex;
  align-items: center;
  gap: 10px;
}
.content-preview {
  white-space: pre-wrap;
  word-break: break-word;
  max-height: 120px;
  overflow: hidden;
}
</style>

