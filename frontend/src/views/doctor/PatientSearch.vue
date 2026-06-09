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
              <el-tag :type="typeTagMap[item.patient_type] || 'success'" size="small" style="margin-right:4px;">
                {{ typeLabelMap[item.patient_type] || '学生' }}
              </el-tag>
              <span class="student-id">{{ item.student_id || '-' }}</span>
              <span class="name">{{ item.name }}</span>
              <span class="gender">{{ item.gender }}</span>
              <span class="class-name">{{ item.department || item.shop_name || item.class_name || '-' }}</span>
              <span class="phone">{{ item.phone || '-' }}</span>
            </div>
          </template>
          <template #append>
            <el-button @click="handleSearchFromButton" :loading="loading">查询</el-button>
          </template>
        </el-autocomplete>
      </div>
    </el-card>

    <!-- 我的挂单 -->
    <el-card v-if="myParkedList.length > 0" class="parked-card">
      <template #header>
        <div class="card-header">
          <span>我的挂单 <el-tag type="warning" size="small" effect="plain">{{ myParkedList.length }}</el-tag></span>
          <el-button size="small" link @click="loadMyParkedList" :loading="parkedLoading">刷新</el-button>
        </div>
      </template>
      <el-table :data="myParkedList" v-loading="parkedLoading" stripe size="small">
        <el-table-column prop="patient_name" label="患者" width="100" />
        <el-table-column prop="student_id" label="学号" width="110">
          <template #default="scope">{{ scope.row.student_id || '-' }}</template>
        </el-table-column>
        <el-table-column prop="chief_complaint" label="主诉" min-width="160" show-overflow-tooltip>
          <template #default="scope">{{ scope.row.chief_complaint || '(暂无)' }}</template>
        </el-table-column>
        <el-table-column prop="diagnosis" label="诊断" min-width="120" show-overflow-tooltip>
          <template #default="scope">{{ scope.row.diagnosis || '-' }}</template>
        </el-table-column>
        <el-table-column prop="item_count" label="项目" width="60" align="center">
          <template #default="scope">{{ scope.row.item_count || 0 }}</template>
        </el-table-column>
        <el-table-column prop="updated_at" label="更新时间" width="150" />
        <el-table-column prop="expires_at" label="过期时间" width="150" />
        <el-table-column label="操作" width="160" fixed="right">
          <template #default="scope">
            <el-button size="small" type="primary" link @click="continueParkedRow(scope.row)">继续接诊</el-button>
            <el-button size="small" type="danger" link @click="deleteParkedRow(scope.row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- 患者信息展示 -->
    <el-card v-if="patient" class="info-card">
      <template #header>
        <div class="card-header">
          <span>
            患者信息
            <el-tag v-if="parkedVisit" type="warning" size="small" style="margin-left:8px;">该患者有挂单</el-tag>
          </span>
          <div>
            <el-button @click="toggleHistory">
              {{ showHistory ? '收起历史' : '查看就诊历史' }}
            </el-button>
            <el-button v-if="parkedVisit" type="warning" @click="continueParkedVisit">继续挂单接诊</el-button>
            <el-button type="primary" @click="handleStartVisit">开始接诊</el-button>
          </div>
        </div>
      </template>
      <el-descriptions border>
        <el-descriptions-item label="人员类型">
          <el-tag :type="typeTagMap[patient.patient_type] || 'success'" size="small">
            {{ typeLabelMap[patient.patient_type] || '学生' }}
          </el-tag>
        </el-descriptions-item>
        <el-descriptions-item label="学号" v-if="patient.patient_type === 'student' || !patient.patient_type">{{ patient.student_id || '-' }}</el-descriptions-item>
        <el-descriptions-item label="姓名">{{ patient.name || '-' }}</el-descriptions-item>
        <el-descriptions-item label="性别">{{ patient.gender || '-' }}</el-descriptions-item>
        <el-descriptions-item label="年龄">{{ patient.age || '-' }}</el-descriptions-item>
        <el-descriptions-item label="年级" v-if="patient.patient_type === 'student' || !patient.patient_type">{{ patient.grade || '-' }}</el-descriptions-item>
        <el-descriptions-item label="学院" v-if="patient.patient_type === 'student' || !patient.patient_type">{{ patient.college || '-' }}</el-descriptions-item>
        <el-descriptions-item label="专业" v-if="patient.patient_type === 'student' || !patient.patient_type">{{ patient.major || '-' }}</el-descriptions-item>
        <el-descriptions-item label="班级" v-if="patient.patient_type === 'student' || !patient.patient_type">{{ patient.class_name || '-' }}</el-descriptions-item>
        <el-descriptions-item label="所在单位" v-if="patient.patient_type === 'staff'">{{ patient.department || '-' }}</el-descriptions-item>
        <el-descriptions-item label="商铺名称" v-if="patient.patient_type === 'shop'">{{ patient.shop_name || '-' }}</el-descriptions-item>
        <el-descriptions-item label="电话">{{ patient.phone || '-' }}</el-descriptions-item>
      </el-descriptions>

      <!-- 就诊历史列表 -->
      <div v-if="showHistory" class="history-section">
        <el-divider content-position="left">就诊历史</el-divider>
        <el-table :data="visitHistory" v-loading="historyLoading" stripe size="small">
          <el-table-column prop="date" label="就诊时间" width="150" />
          <el-table-column prop="doctor_name" label="接诊医生" width="90" />
          <el-table-column prop="diagnosis" label="诊断" min-width="130" show-overflow-tooltip />
          <el-table-column prop="total_amount" label="金额" width="80">
            <template #default="scope">¥{{ (scope.row.total_amount || 0).toFixed(2) }}</template>
          </el-table-column>
          <el-table-column prop="status" label="状态" width="95">
            <template #default="scope">
              <el-tag :type="getStatusType(scope.row.status)" size="small">
                {{ getStatusText(scope.row.status) }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column label="操作" width="60">
            <template #default="scope">
              <el-button size="small" type="primary" link @click="openCaseReview(scope.row.visit_id)">详情</el-button>
            </template>
          </el-table-column>
        </el-table>
        <div v-if="!historyLoading && visitHistory.length === 0" style="text-align:center;color:#909399;padding:16px 0;">
          暂无就诊记录
        </div>
      </div>
    </el-card>

    <!-- 病例复盘弹窗 -->
    <el-dialog v-model="caseDialogVisible" title="病例详情" width="840px">
      <div v-loading="caseLoading" v-if="caseDetail" class="case-review">
        <el-descriptions border :column="2" title="患者信息">
          <el-descriptions-item label="姓名">{{ caseDetail.patient?.name || '-' }}</el-descriptions-item>
          <el-descriptions-item label="学号">{{ caseDetail.patient?.student_id || '-' }}</el-descriptions-item>
          <el-descriptions-item label="就诊时间" :span="2">{{ caseDetail.created_at }}</el-descriptions-item>
          <el-descriptions-item label="状态">{{ getStatusText(caseDetail.status) }}</el-descriptions-item>
          <el-descriptions-item label="医生">{{ caseDetail.doctor_name }}</el-descriptions-item>
        </el-descriptions>

        <!-- 状态流转时间线 -->
        <div v-if="caseDetail.status_timeline && caseDetail.status_timeline.length > 0" style="margin-top:16px;">
          <div style="font-weight:bold;margin-bottom:10px;">状态流转</div>
          <el-timeline>
            <el-timeline-item
              v-for="(step, idx) in caseDetail.status_timeline"
              :key="idx"
              :timestamp="step.timestamp"
              :type="timelineType(step.status)"
              placement="top"
              size="small"
            >
              <div style="display:flex;justify-content:space-between;align-items:center;">
                <span>
                  <strong>{{ step.actor }}</strong> {{ step.label }}
                  <span v-if="step.amount" style="color:#f56c6c;"> ¥{{ step.amount }}</span>
                </span>
                <el-tag v-if="step.reason" type="danger" size="small">{{ step.reason }}</el-tag>
              </div>
            </el-timeline-item>
          </el-timeline>
        </div>

        <el-descriptions border :column="1" title="电子病历" direction="vertical" style="margin-top:16px;">
          <el-descriptions-item label="主诉">{{ caseDetail.chief_complaint || '无' }}</el-descriptions-item>
          <el-descriptions-item label="现病史">{{ caseDetail.present_illness || '无' }}</el-descriptions-item>
          <el-descriptions-item label="既往史">{{ caseDetail.past_history || '无' }}</el-descriptions-item>
          <el-descriptions-item label="体格检查">{{ caseDetail.physical_exam || '无' }}</el-descriptions-item>
          <el-descriptions-item label="诊断">{{ caseDetail.diagnosis || '无' }}</el-descriptions-item>
          <el-descriptions-item label="医生留言">{{ caseDetail.doctor_advice || '无' }}</el-descriptions-item>
        </el-descriptions>
        <div style="margin-top:16px;">
          <div style="font-weight:bold;margin-bottom:8px;">处方明细</div>
          <el-table :data="caseDetail.items" border stripe size="small">
            <el-table-column prop="drug_name" label="药品名称" />
            <el-table-column prop="specification" label="规格" width="100" />
            <el-table-column label="用法" min-width="160">
              <template #default="scope">
                {{ scope.row.usage }} / {{ scope.row.dosage }} / {{ scope.row.frequency }} / {{ scope.row.timing }} ({{ scope.row.days }}天)
              </template>
            </el-table-column>
            <el-table-column prop="quantity" label="数量" width="70" />
            <el-table-column label="金额" width="80">
              <template #default="scope">¥{{ (scope.row.amount || 0).toFixed(2) }}</template>
            </el-table-column>
          </el-table>
        </div>
        <!-- 病历修改记录 -->
        <div style="margin-top:12px;text-align:right;">
          <el-button size="small" type="info" link @click="showEditHistory = !showEditHistory">
            {{ showEditHistory ? '收起修改记录' : '查看修改记录' }}
          </el-button>
        </div>
        <div v-if="showEditHistory" style="margin-top:8px;">
          <el-table :data="editHistory" v-loading="editHistoryLoading" border stripe size="small" max-height="200">
            <el-table-column prop="timestamp" label="修改时间" width="150" />
            <el-table-column prop="user_name" label="操作人" width="80" />
            <el-table-column prop="summary" label="摘要" min-width="120" />
          </el-table>
        </div>
      </div>
      <template #footer>
        <el-button @click="caseDialogVisible = false">关闭</el-button>
      </template>
    </el-dialog>

    <!-- 新人首诊登记 -->
    <el-card v-if="showCreateForm" class="create-card">
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
import { ref, computed, watch, onMounted, onActivated } from 'vue'
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

// 人员类型映射
const typeLabelMap = { student: '学生', staff: '教职工', shop: '商铺员工', temporary: '临时人员' }
const typeTagMap = { student: 'success', staff: 'primary', shop: '', temporary: 'warning' }

const phoneDialogVisible = ref(false)
const tempPhone = ref('')
const updatingPhone = ref(false)

// 就诊历史
const showHistory = ref(false)
const visitHistory = ref([])
const historyLoading = ref(false)

// 病例详情弹窗
const caseDialogVisible = ref(false)
const caseLoading = ref(false)
const caseDetail = ref(null)
const showEditHistory = ref(false)
const editHistory = ref([])
const editHistoryLoading = ref(false)

// 挂单相关
const myParkedList = ref([])
const parkedLoading = ref(false)
const parkedVisit = ref(null) // 当前选中患者的挂单（若有）

const loadMyParkedList = async () => {
  parkedLoading.value = true
  try {
    const res = await request.get('/doctor/parked-visits')
    myParkedList.value = Array.isArray(res.data) ? res.data : []
  } catch (e) {
    myParkedList.value = []
  } finally {
    parkedLoading.value = false
  }
}

const checkPatientParked = async (patientId) => {
  if (!patientId) {
    parkedVisit.value = null
    return
  }
  try {
    const res = await request.get(`/doctor/patient/${patientId}/parked-visit`)
    parkedVisit.value = res.data || null
  } catch (e) {
    parkedVisit.value = null
  }
}

const continueParkedVisit = () => {
  if (!parkedVisit.value || !patient.value) return
  router.push({
    path: '/doctor/visit',
    query: {
      patient_id: patient.value.id,
      patient_name: patient.value.name,
      parked_id: parkedVisit.value.id
    }
  })
}

const continueParkedRow = (row) => {
  router.push({
    path: '/doctor/visit',
    query: {
      patient_id: row.patient_id,
      patient_name: row.patient_name,
      parked_id: row.id
    }
  })
}

const deleteParkedRow = async (row) => {
  try {
    await ElMessageBox.confirm(`确定删除「${row.patient_name}」的挂单？删除后无法恢复。`, '删除挂单', {
      type: 'warning',
      confirmButtonText: '确定删除',
      cancelButtonText: '取消'
    })
  } catch {
    return
  }
  try {
    await request.delete(`/doctor/parked-visits/${row.id}`)
    ElMessage.success('已删除挂单')
    if (patient.value && parkedVisit.value && parkedVisit.value.id === row.id) {
      parkedVisit.value = null
    }
    loadMyParkedList()
  } catch (e) {
    ElMessage.error(e?.msg || '删除失败')
  }
}

const timelineType = (status) => {
  const map = { pending: '', nurse_verified: 'primary', completed: 'success', rejected: 'danger', revoked: 'info' }
  return map[status] || 'info'
}

const getStatusType = (status) => {
  const map = { pending: 'warning', nurse_verified: 'info', completed: 'success', rejected: 'danger', revoked: 'info' }
  return map[status] || ''
}
const getStatusText = (status) => {
  const map = { pending: '待护士核验', nurse_verified: '护士已核验', completed: '已完成', rejected: '已驳回', revoked: '已撤销' }
  return map[status] || status
}

const fetchVisitHistory = async () => {
  if (!patient.value) return
  historyLoading.value = true
  try {
    const res = await request.get(`/doctor/patient/${patient.value.id}/visits`)
    visitHistory.value = res.data || []
  } catch {
    visitHistory.value = []
  } finally {
    historyLoading.value = false
  }
}

const toggleHistory = () => {
  showHistory.value = !showHistory.value
  if (showHistory.value && visitHistory.value.length === 0) {
    fetchVisitHistory()
  }
}

const openCaseReview = async (visitId) => {
  currentVisitId = visitId
  caseDialogVisible.value = true
  caseLoading.value = true
  caseDetail.value = null
  showEditHistory.value = false
  editHistory.value = []
  try {
    const res = await request.get(`/doctor/visits/${visitId}`)
    caseDetail.value = res.data
  } catch {
    ElMessage.error('获取详情失败')
    caseDialogVisible.value = false
  } finally {
    caseLoading.value = false
  }
}

const fetchEditHistory = async () => {
  if (!currentVisitId) return
  editHistoryLoading.value = true
  try {
    const res = await request.get(`/doctor/visits/${currentVisitId}/revisions`)
    editHistory.value = res.data || []
  } catch {
    editHistory.value = []
  } finally {
    editHistoryLoading.value = false
  }
}

// track current visit id for revision history
let currentVisitId = null

// watch edit history toggle to fetch data lazily
watch(showEditHistory, (val) => {
  if (val && editHistory.value.length === 0) {
    fetchEditHistory()
  }
})

onMounted(() => {
  loadMyParkedList()
})
onActivated(() => {
  loadMyParkedList()
  if (patient.value && patient.value.id) {
    checkPatientParked(patient.value.id)
  }
})

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
  showHistory.value = false
  visitHistory.value = []
  parkedVisit.value = null
  if (item && item.id) {
    checkPatientParked(item.id)
  }
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
  const typeLabel = typeLabelMap[p.patient_type] || '学生'
  let extraInfo = ''
  if (p.patient_type === 'staff') {
    extraInfo = `<div><b>所在单位：</b>${escapeHtml(p.department || '-')}</div>`
  } else if (p.patient_type === 'shop') {
    extraInfo = `<div><b>商铺名称：</b>${escapeHtml(p.shop_name || '-')}</div>`
  } else if (p.patient_type === 'student' || !p.patient_type) {
    extraInfo = `<div><b>班级：</b>${escapeHtml(p.class_name || '-')}</div>`
  }
  const html = `
    <div style="line-height: 1.8;">
      <div style="margin-bottom: 10px;">请再次确认患者基本信息无误：</div>
      <div><b>人员类型：</b>${typeLabel}</div>
      <div><b>学号/工号：</b>${escapeHtml(p.student_id || '-')}</div>
      <div><b>姓名：</b>${escapeHtml(p.name || '-')}</div>
      <div><b>性别：</b>${escapeHtml(p.gender || '-')}</div>
      <div><b>年龄：</b>${escapeHtml(p.age || '-')}</div>
      ${extraInfo}
      <div><b>电话：</b>${escapeHtml(p.phone || '-')}</div>
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
  if (!/^1\d{10}$/.test(tempPhone.value.trim())) {
    ElMessage.warning('手机号码格式不正确，应为1开头的11位数字')
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
.parked-card {
  margin-bottom: 20px;
}
.info-card {
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
.history-section {
  margin-top: 8px;
}
.case-review :deep(.highlight-label) {
  color: #f56c6c;
  font-weight: bold;
}
</style>
