<template>
  <div class="patient-search-container">
    <!-- 搜索区域 -->
    <el-card class="search-card">
      <div class="search-box">
        <el-autocomplete
          v-model="searchKeyword"
          placeholder="请输入姓名 / 学号 / 手机号 / 拼音（前几位即可）"
          class="search-input"
          :fetch-suggestions="handleSearch"
          :trigger-on-focus="false"
          clearable
          @select="handleSelect"
          @keyup.enter="handleEnter"
          :highlight-first-item="true"
        >
          <template #prefix>
            <el-icon><Search /></el-icon>
          </template>
          <template #default="{ item }">
            <div class="patient-suggestion">
              <span class="student-id">{{ item.student_id || '-' }}</span>
              <span class="name">{{ item.name }}</span>
              <span class="gender">{{ item.gender }}</span>
              <span class="class-name">{{ item.class_name || '-' }}</span>
              <span class="phone">{{ item.phone || '-' }}</span>
            </div>
          </template>
          <template #append>
            <el-button @click="handleSearchFromButton" :loading="loading">查询</el-button>
          </template>
        </el-autocomplete>
      </div>
    </el-card>

    <!-- 患者信息展示 -->
    <el-card v-if="patient" class="info-card">
      <template #header>
        <div class="card-header">
          <span>患者信息</span>
          <el-button type="primary" @click="handleStartVisit">开始接诊</el-button>
        </div>
      </template>
      <el-descriptions border>
        <el-descriptions-item label="学号">{{ patient.student_id || '-' }}</el-descriptions-item>
        <el-descriptions-item label="姓名">{{ patient.name || '-' }}</el-descriptions-item>
        <el-descriptions-item label="性别">{{ patient.gender || '-' }}</el-descriptions-item>
        <el-descriptions-item label="年龄">{{ patient.age || '-' }}</el-descriptions-item>
        <el-descriptions-item label="年级">{{ patient.grade || '-' }}</el-descriptions-item>
        <el-descriptions-item label="学院">{{ patient.college || '-' }}</el-descriptions-item>
        <el-descriptions-item label="专业">{{ patient.major || '-' }}</el-descriptions-item>
        <el-descriptions-item label="班级">{{ patient.class_name || '-' }}</el-descriptions-item>
        <el-descriptions-item label="电话">{{ patient.phone || '-' }}</el-descriptions-item>
      </el-descriptions>
    </el-card>

    <!-- 新人首诊登记 -->
    <el-card v-else-if="showCreateForm" class="create-card">
      <template #header>
        <span>未找到人员，请进行新人首诊登记</span>
      </template>
      <el-form :model="createForm" :rules="rules" ref="formRef" label-width="100px">
        <el-form-item>
          <el-switch v-model="createForm.is_temporary" active-text="临时人员" inactive-text="在校学生" />
        </el-form-item>
        <el-form-item v-if="!createForm.is_temporary" label="学号" prop="student_id">
          <el-input v-model="createForm.student_id"></el-input>
        </el-form-item>
        <el-form-item label="姓名" prop="name">
          <el-input v-model="createForm.name"></el-input>
        </el-form-item>
        <el-form-item label="性别" prop="gender">
          <el-radio-group v-model="createForm.gender">
            <el-radio label="男">男</el-radio>
            <el-radio label="女">女</el-radio>
          </el-radio-group>
        </el-form-item>
        <el-form-item v-if="!createForm.is_temporary" label="班级" prop="class_name">
          <el-input v-model="createForm.class_name"></el-input>
        </el-form-item>
        <el-form-item v-if="!createForm.is_temporary" label="辅导员姓名" prop="counselor_name">
          <el-input v-model="createForm.counselor_name"></el-input>
        </el-form-item>
        <el-form-item v-if="!createForm.is_temporary" label="年级" prop="grade">
          <el-input v-model="createForm.grade"></el-input>
        </el-form-item>
        <el-form-item v-if="!createForm.is_temporary" label="学院" prop="college">
          <el-input v-model="createForm.college"></el-input>
        </el-form-item>
        <el-form-item v-if="!createForm.is_temporary" label="专业" prop="major">
          <el-input v-model="createForm.major"></el-input>
        </el-form-item>
        <el-form-item label="年龄" prop="age">
          <el-input-number v-model="createForm.age" :min="1" :max="150" />
        </el-form-item>
        <el-form-item :label="createForm.is_temporary ? '联系电话' : '手机号码（选填）'" prop="phone">
          <el-input v-model="createForm.phone"></el-input>
        </el-form-item>
        <el-form-item label="身份证号（选填）" prop="id_card">
          <el-input v-model="createForm.id_card" maxlength="18" show-word-limit></el-input>
        </el-form-item>
        <el-form-item>
          <el-button type="primary" @click="handleCreate" :loading="creating">保存并接诊</el-button>
        </el-form-item>
      </el-form>
    </el-card>

    <!-- 补充手机号弹窗 -->
    <el-dialog
      v-model="phoneDialogVisible"
      title="补充联系方式"
      width="400px"
    >
      <div style="margin-bottom: 20px;">
        该患者目前未登记手机号码，请补充后再接诊：
      </div>
      <el-input
        v-model="tempPhone"
        placeholder="请输入手机号码"
        clearable
      ></el-input>
      <template #footer>
        <span class="dialog-footer">
          <el-button @click="phoneDialogVisible = false">取消</el-button>
          <el-button @click="skipPhoneInput">暂不补充，直接接诊</el-button>
          <el-button type="primary" @click="submitPhone" :loading="updatingPhone">
            保存并接诊
          </el-button>
        </span>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, computed } from 'vue'
import { useRouter } from 'vue-router'
import { Search } from '@element-plus/icons-vue'
import request from '@/api/request'
import { ElMessage, ElMessageBox } from 'element-plus'

const router = useRouter()
const searchKeyword = ref('')
const loading = ref(false)
const patient = ref(null)
const showCreateForm = ref(false)
const creating = ref(false)
const formRef = ref(null)
const searchResults = ref([])

const phoneDialogVisible = ref(false)
const tempPhone = ref('')
const updatingPhone = ref(false)

const escapeHtml = (value) => {
  return String(value ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;')
}

const createForm = ref({
  is_temporary: false,
  student_id: '',
  name: '',
  gender: '男',
  age: null,
  phone: '',
  id_card: '',
  grade: '',
  college: '',
  major: '',
  class_name: '',
  counselor_name: ''
})

const rules = computed(() => {
  const base = {
    name: [{ required: true, message: '请输入姓名', trigger: 'blur' }],
    gender: [{ required: true, message: '请选择性别', trigger: 'change' }],
    age: [{ required: true, message: '请输入年龄', trigger: 'change' }],
    phone: [
      {
        validator: (rule, value, callback) => {
          const v = (value || '').trim()
          if (createForm.value.is_temporary) {
            if (!v) return callback(new Error('请输入手机号码'))
            if (!/^1\d{10}$/.test(v)) return callback(new Error('手机号码格式不正确'))
            return callback()
          }
          if (!v) return callback()
          if (!/^1\d{10}$/.test(v)) return callback(new Error('手机号码格式不正确'))
          return callback()
        },
        trigger: 'blur'
      }
    ],
    id_card: [
      {
        validator: (rule, value, callback) => {
          const v = (value || '').trim()
          if (!v) return callback()
          if (!/^\d{17}[\dXx]$/.test(v)) return callback(new Error('身份证号格式不正确'))
          callback()
        },
        trigger: 'blur'
      }
    ]
  }

  if (!createForm.value.is_temporary) {
    base.student_id = [{ required: true, message: '请输入学号', trigger: 'blur' }]
    base.class_name = [{ required: true, message: '请输入班级', trigger: 'blur' }]
    base.counselor_name = [{ required: true, message: '请输入辅导员姓名', trigger: 'blur' }]
    base.age = [{ required: false, trigger: 'change' }]
  }

  return base
})

let searchTimer = null

const handleSearch = async (query, callback) => {
  if (!query || query.length < 1) {
    callback([])
    return
  }

  if (searchTimer) {
    clearTimeout(searchTimer)
  }

  searchTimer = setTimeout(async () => {
    loading.value = true
    try {
      const res = await request.get('/doctor/patient/search', {
        params: { keyword: query }
      })

      if (res.data && res.data.length > 0) {
        searchResults.value = res.data
        callback(res.data.map(p => ({ ...p, value: p.student_id ? `${p.student_id} ${p.name}` : p.name })))
      } else {
        searchResults.value = []
        callback([])
      }
    } catch (error) {
      console.error('Search error:', error)
      callback([])
    } finally {
      loading.value = false
    }
  }, 300)
}

const handleSearchFromButton = async () => {
  if (!searchKeyword.value) return

  loading.value = true
  patient.value = null
  showCreateForm.value = false

  try {
    const res = await request.get('/doctor/patient/search', {
      params: { keyword: searchKeyword.value }
    })

    if (res.data && res.data.length > 0) {
      if (res.data.length === 1) {
        patient.value = res.data[0]
      } else {
        searchResults.value = res.data
        ElMessage.info(`找到 ${res.data.length} 个匹配结果，请从下拉列表中选择`)
      }
    } else {
      openCreateForm(searchKeyword.value)
    }
  } catch (error) {
    const code = error && typeof error === 'object' ? error.code : undefined
    if (code === 404) {
      openCreateForm(searchKeyword.value)
      return
    }
    if (code === 429) {
      ElMessage.warning('查询过于频繁，请稍后重试')
      return
    }
    ElMessage.error(error.msg || '查询失败')
  } finally {
    loading.value = false
  }
}

const handleSelect = (item) => {
  patient.value = item
  showCreateForm.value = false
  searchKeyword.value = item.student_id || item.name || ''
}

const handleEnter = () => {
  if (searchResults.value.length > 1) {
    ElMessage.info('请从下拉列表中选择一个患者')
  }
}

const handleCreate = async () => {
  if (!formRef.value) return

  await formRef.value.validate(async (valid) => {
    if (valid) {
      creating.value = true
      try {
        const payload = { ...createForm.value }
        const res = await request.post('/doctor/patient', payload)
        ElMessage.success('建档成功')
        patient.value = { ...createForm.value, id: res.data.id }
        showCreateForm.value = false
        handleStartVisit()
      } catch (error) {
        ElMessage.error(error.msg || '建档失败')
      } finally {
        creating.value = false
      }
    }
  })
}

const handleStartVisit = () => {
  if (patient.value && patient.value.is_temporary && !patient.value.phone) {
    ElMessage.warning('临时人员必须填写手机号码')
    return
  }
  if (!patient.value.phone) {
    tempPhone.value = ''
    phoneDialogVisible.value = true
  } else {
    confirmStartVisit()
  }
}

const confirmStartVisit = async () => {
  if (!patient.value) return

  const p = patient.value
  const html = `
    <div style="line-height: 1.8;">
      <div style="margin-bottom: 10px;">请再次确认患者基本信息无误：</div>
      <div><b>学号：</b>${escapeHtml(p.student_id || '-')}</div>
      <div><b>姓名：</b>${escapeHtml(p.name || '-')}</div>
      <div><b>性别：</b>${escapeHtml(p.gender || '-')}</div>
      <div><b>年龄：</b>${escapeHtml(p.age || '-')}</div>
      <div><b>班级：</b>${escapeHtml(p.class_name || '-')}</div>
      <div><b>电话：</b>${escapeHtml(p.phone || '-')}</div>
      <div><b>人员类型：</b>${p.is_temporary ? '临时人员' : '在校学生'}</div>
    </div>
  `

  try {
    await ElMessageBox.confirm(html, '确认接诊信息', {
      dangerouslyUseHTMLString: true,
      confirmButtonText: '确认并开始接诊',
      cancelButtonText: '返回检查',
      type: 'warning',
      closeOnClickModal: false,
      closeOnPressEscape: false,
    })
    startVisit()
  } catch (e) {
    return
  }
}

const submitPhone = async () => {
  if (!tempPhone.value) {
    ElMessage.warning('请输入手机号码')
    return
  }
  
  updatingPhone.value = true
  try {
    await request.put(`/doctor/patient/${patient.value.id}`, {
      phone: tempPhone.value
    })
    patient.value.phone = tempPhone.value
    phoneDialogVisible.value = false
    ElMessage.success('信息已更新')
    confirmStartVisit()
  } catch (error) {
    ElMessage.error('更新失败')
  } finally {
    updatingPhone.value = false
  }
}

const skipPhoneInput = () => {
  phoneDialogVisible.value = false
  confirmStartVisit()
}

const startVisit = () => {
  router.push({
    path: '/doctor/visit',
    query: {
        patient_id: patient.value.id,
        patient_name: patient.value.name
    }
  })
}

const openCreateForm = (keyword) => {
  showCreateForm.value = true
  const kw = (keyword || '').trim()
  createForm.value.is_temporary = false
  createForm.value.student_id = ''
  createForm.value.name = ''
  createForm.value.gender = '男'
  createForm.value.age = null
  createForm.value.phone = ''
  createForm.value.id_card = ''
  createForm.value.grade = ''
  createForm.value.college = ''
  createForm.value.major = ''
  createForm.value.class_name = ''
  createForm.value.counselor_name = ''
  if (/^1\d{10}$/.test(kw)) {
    createForm.value.phone = kw
  } else if (/^\d{4,}$/.test(kw)) {
    createForm.value.student_id = kw
  } else if (/[\u4e00-\u9fff]/.test(kw)) {
    createForm.value.name = kw
  }
}
</script>

<style scoped>
.patient-search-container {
  max-width: 800px;
  margin: 0 auto;
}
.search-card {
  margin-bottom: 20px;
}
.search-box {
  display: flex;
  justify-content: center;
}
.search-input {
  max-width: 500px;
  width: 100%;
}
.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.patient-suggestion {
  display: flex;
  align-items: center;
  gap: 12px;
}
.patient-suggestion .student-id {
  font-weight: bold;
  color: #409EFF;
}
.patient-suggestion .name {
  flex: 1;
}
.patient-suggestion .phone {
  color: #909399;
  font-size: 12px;
}
.patient-suggestion .class-name {
  color: #909399;
  font-size: 12px;
}
</style>
