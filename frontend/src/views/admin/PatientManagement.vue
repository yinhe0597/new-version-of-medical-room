<template>
  <div class="patient-management">
    <el-card>
      <template #header>
        <div class="card-header">
          <div class="left-panel">
            <el-input
              v-model="keyword"
              placeholder="搜索姓名/学号/拼音/手机号/身份证"
              clearable
              style="width: 260px"
              @clear="fetchPatients"
              @keyup.enter="fetchPatients"
            >
              <template #append>
                <el-button :icon="Search" @click="fetchPatients" />
              </template>
            </el-input>
            <el-select v-model="filterType" placeholder="全部类型" clearable style="width: 120px" @change="fetchPatients">
              <el-option label="全部" value="" />
              <el-option label="学生" value="student" />
              <el-option label="教职工" value="staff" />
              <el-option label="商铺员工" value="shop" />
              <el-option label="临时人员" value="temporary" />
            </el-select>
          </div>
          <div class="right-panel">
            <el-button type="primary" :icon="Plus" @click="openCreateDialog">新增人员</el-button>
            <el-button type="success" @click="showImport = true">批量导入</el-button>
          </div>
        </div>
      </template>

      <el-table :data="patientList" v-loading="loading" stripe style="width: 100%">
        <el-table-column prop="student_id" label="学号" width="120" v-if="!filterType || filterType === 'student'" />
        <el-table-column prop="name" label="姓名" width="90" />
        <el-table-column prop="gender" label="性别" width="60" />
        <el-table-column prop="age" label="年龄" width="60" />
        <el-table-column prop="college" label="学院" min-width="120" show-overflow-tooltip v-if="!filterType || filterType === 'student'" />
        <el-table-column prop="major" label="专业" min-width="100" show-overflow-tooltip v-if="!filterType || filterType === 'student'" />
        <el-table-column prop="class_name" label="班级" min-width="100" show-overflow-tooltip v-if="!filterType || filterType === 'student'" />
        <el-table-column prop="department" label="所在单位" min-width="120" show-overflow-tooltip v-if="filterType === 'staff'" />
        <el-table-column prop="shop_name" label="商铺名称" min-width="120" show-overflow-tooltip v-if="filterType === 'shop'" />
        <el-table-column prop="phone" label="手机号" width="120" />
        <el-table-column prop="counselor_name" label="辅导员" width="90" v-if="!filterType || filterType === 'student'" />
        <el-table-column label="类型" width="100">
          <template #default="scope">
            <el-tag :type="typeTagMap[scope.row.patient_type] || 'success'" size="small">
              {{ typeLabelMap[scope.row.patient_type] || '学生' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="220" fixed="right">
          <template #default="scope">
            <el-button size="small" type="primary" link @click="openCaseHistory(scope.row)">病历</el-button>
            <el-button size="small" @click="openEditDialog(scope.row)">编辑</el-button>
            <el-button size="small" type="danger" @click="handleDelete(scope.row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>

      <div class="pagination-wrapper" v-if="total > 0">
        <el-pagination
          v-model:current-page="currentPage"
          v-model:page-size="pageSize"
          :page-sizes="[20, 50, 100]"
          :total="total"
          layout="total, sizes, prev, pager, next, jumper"
          @size-change="fetchPatients"
          @current-change="fetchPatients"
        />
      </div>
    </el-card>

    <!-- 新增/编辑弹窗 -->
    <el-dialog
      v-model="dialogVisible"
      :title="isEdit ? '编辑人员' : '新增人员'"
      width="520px"
      destroy-on-close
    >
      <el-form :model="form" :rules="rules" ref="formRef" label-width="90px">
        <el-form-item label="人员类型">
          <el-select v-model="form.patient_type" @change="onTypeChange" style="width: 100%">
            <el-option label="学生" value="student" />
            <el-option label="教职工" value="staff" />
            <el-option label="商铺员工" value="shop" />
            <el-option label="临时人员" value="temporary" />
          </el-select>
        </el-form-item>

        <el-form-item label="姓名" prop="name">
          <el-input v-model="form.name" placeholder="请输入姓名" />
        </el-form-item>
        <el-form-item label="性别">
          <el-radio-group v-model="form.gender">
            <el-radio label="男">男</el-radio>
            <el-radio label="女">女</el-radio>
          </el-radio-group>
        </el-form-item>
        <el-form-item label="手机号">
          <el-input v-model="form.phone" placeholder="请输入手机号" />
        </el-form-item>

        <!-- 学生专属字段 -->
        <template v-if="form.patient_type === 'student'">
          <el-form-item label="学号" prop="student_id">
            <el-input v-model="form.student_id" placeholder="留空则自动生成" />
          </el-form-item>
          <el-form-item label="年级">
            <el-input v-model="form.grade" placeholder="如：2024级" />
          </el-form-item>
          <el-form-item label="学院">
            <el-input v-model="form.college" placeholder="请输入学院" />
          </el-form-item>
          <el-form-item label="专业">
            <el-input v-model="form.major" placeholder="请输入专业" />
          </el-form-item>
          <el-form-item label="班级">
            <el-input v-model="form.class_name" placeholder="请输入班级" />
          </el-form-item>
          <el-form-item label="辅导员">
            <el-input v-model="form.counselor_name" placeholder="请输入辅导员姓名" />
          </el-form-item>
        </template>

        <!-- 教职工专属字段 -->
        <template v-if="form.patient_type === 'staff'">
          <el-form-item label="身份证号" prop="id_card">
            <el-input v-model="form.id_card" placeholder="请输入身份证号" maxlength="18" @blur="calcAgeFromIdCard" />
          </el-form-item>
          <el-form-item label="所在单位">
            <el-input v-model="form.department" placeholder="请输入二级单位" />
          </el-form-item>
        </template>

        <!-- 商铺员工专属字段 -->
        <template v-if="form.patient_type === 'shop'">
          <el-form-item label="身份证号" prop="id_card">
            <el-input v-model="form.id_card" placeholder="请输入身份证号" maxlength="18" @blur="calcAgeFromIdCard" />
          </el-form-item>
          <el-form-item label="商铺名称">
            <el-input v-model="form.shop_name" placeholder="请输入商铺名称" />
          </el-form-item>
        </template>

        <!-- 年龄：学生/临时人员手动输入，教职工/商铺员工自动计算只读 -->
        <el-form-item label="年龄">
          <el-input-number v-model="form.age" :min="1" :max="150" controls-position="right" style="width: 100%"
            :disabled="['staff','shop'].includes(form.patient_type)" />
        </el-form-item>

        <!-- 临时人员提示 -->
        <div v-if="form.patient_type === 'temporary'" style="color:#909399;font-size:12px;margin-bottom:8px;padding-left:90px;">
          临时人员手机号为必填项
        </div>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" @click="submitForm" :loading="submitting">确定</el-button>
      </template>
    </el-dialog>

    <!-- 批量导入弹窗 -->
    <el-dialog v-model="showImport" title="批量导入人员" width="520px" destroy-on-close>
      <div class="import-section">
        <el-form-item label="导入类型" style="margin-bottom: 16px">
          <el-select v-model="importType" style="width: 100%">
            <el-option label="学生" value="student" />
            <el-option label="教职工" value="staff" />
            <el-option label="商铺员工" value="shop" />
          </el-select>
        </el-form-item>
        <el-button type="primary" @click="downloadTemplate" style="margin-bottom: 16px">
          下载{{ importTypeLabel }}导入模板
        </el-button>
        <el-upload
          class="upload-demo"
          drag
          :action="uploadUrlWithType"
          :headers="uploadHeaders"
          :on-success="handleImportSuccess"
          :on-error="handleImportError"
          :before-upload="beforeUpload"
          accept=".csv"
          :limit="1"
        >
          <el-icon class="el-icon--upload"><upload-filled /></el-icon>
          <div class="el-upload__text">将文件拖到此处，或 <em>点击上传</em></div>
          <template #tip>
            <div class="el-upload__tip" v-if="importType === 'student'">只能上传 CSV 文件，且需按照模板格式。必填：学号、姓名、班级、辅导员姓名。</div>
            <div class="el-upload__tip" v-else-if="importType === 'staff'">只能上传 CSV 文件。必填：姓名、性别、身份证号、所在单位。</div>
            <div class="el-upload__tip" v-else-if="importType === 'shop'">只能上传 CSV 文件。必填：姓名、性别、身份证号、商铺名称。</div>
          </template>
        </el-upload>
      </div>
    </el-dialog>

    <!-- 就诊历史弹窗 -->
    <el-dialog v-model="historyDialogVisible" :title="`${historyPatientName} - 就诊历史`" width="800px" destroy-on-close>
      <el-table :data="visitHistory" v-loading="historyLoading" stripe size="small">
        <el-table-column prop="date" label="就诊时间" width="150" />
        <el-table-column prop="doctor_name" label="接诊医生" width="90" />
        <el-table-column prop="chief_complaint" label="主诉" min-width="120" show-overflow-tooltip />
        <el-table-column prop="diagnosis" label="诊断" min-width="120" show-overflow-tooltip />
        <el-table-column prop="total_amount" label="金额" width="80">
          <template #default="scope">¥{{ (scope.row.total_amount || 0).toFixed(2) }}</template>
        </el-table-column>
        <el-table-column prop="status" label="状态" width="90">
          <template #default="scope">
            <el-tag :type="getStatusType(scope.row.status)" size="small">{{ getStatusText(scope.row.status) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="70">
          <template #default="scope">
            <el-button size="small" type="primary" link @click="openVisitDetail(scope.row.visit_id)">详情</el-button>
          </template>
        </el-table-column>
      </el-table>
      <div v-if="!historyLoading && visitHistory.length === 0" style="text-align:center;color:#909399;padding:24px 0;">
        暂无就诊记录
      </div>
    </el-dialog>

    <!-- 就诊详情弹窗 -->
    <el-dialog v-model="detailDialogVisible" title="就诊详情" width="800px" destroy-on-close>
      <div v-loading="detailLoading" v-if="visitDetail">
        <el-descriptions border :column="2" title="患者信息">
          <el-descriptions-item label="姓名">{{ visitDetail.patient?.name || '-' }}</el-descriptions-item>
          <el-descriptions-item label="学号">{{ visitDetail.patient?.student_id || '-' }}</el-descriptions-item>
          <el-descriptions-item label="就诊时间" :span="2">{{ visitDetail.created_at }}</el-descriptions-item>
          <el-descriptions-item label="接诊医生">{{ visitDetail.doctor_name }}</el-descriptions-item>
          <el-descriptions-item label="状态">{{ getStatusText(visitDetail.status) }}</el-descriptions-item>
        </el-descriptions>
        <el-descriptions border :column="1" title="电子病历" direction="vertical" style="margin-top:16px;">
          <el-descriptions-item label="主诉">{{ visitDetail.chief_complaint || '无' }}</el-descriptions-item>
          <el-descriptions-item label="现病史">{{ visitDetail.present_illness || '无' }}</el-descriptions-item>
          <el-descriptions-item label="既往史">{{ visitDetail.past_history || '无' }}</el-descriptions-item>
          <el-descriptions-item label="体格检查">{{ visitDetail.physical_exam || '无' }}</el-descriptions-item>
          <el-descriptions-item label="诊断">{{ visitDetail.diagnosis || '无' }}</el-descriptions-item>
          <el-descriptions-item label="医生留言">{{ visitDetail.doctor_advice || '无' }}</el-descriptions-item>
        </el-descriptions>
        <div style="margin-top:16px;">
          <div style="font-weight:bold;margin-bottom:8px;">处方明细</div>
          <el-table :data="visitDetail.items" border stripe size="small">
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
      </div>
      <template #footer>
        <el-button @click="detailDialogVisible = false">关闭</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { Plus, Search, UploadFilled } from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import request from '@/api/request'

const patientList = ref([])
const loading = ref(false)
const keyword = ref('')
const filterType = ref('')
const currentPage = ref(1)
const pageSize = ref(20)
const total = ref(0)

const dialogVisible = ref(false)
const isEdit = ref(false)
const submitting = ref(false)
const formRef = ref(null)
const showImport = ref(false)
const importType = ref('student')

// 类型映射
const typeLabelMap = { student: '学生', staff: '教职工', shop: '商铺员工', temporary: '临时人员' }
const typeTagMap = { student: 'success', staff: 'primary', shop: '', temporary: 'warning' }

// 就诊历史
const historyDialogVisible = ref(false)
const historyPatientName = ref('')
const visitHistory = ref([])
const historyLoading = ref(false)

// 就诊详情
const detailDialogVisible = ref(false)
const detailLoading = ref(false)
const visitDetail = ref(null)

const getStatusType = (status) => {
  const map = { pending: 'warning', nurse_verified: 'info', completed: 'success', rejected: 'danger', revoked: 'info' }
  return map[status] || ''
}
const getStatusText = (status) => {
  const map = { pending: '待护士核验', nurse_verified: '护士已核验', completed: '已完成', rejected: '已驳回', revoked: '已撤销' }
  return map[status] || status
}

const openCaseHistory = async (row) => {
  historyPatientName.value = row.name
  historyDialogVisible.value = true
  historyLoading.value = true
  visitHistory.value = []
  try {
    const res = await request.get(`/admin/patients/${row.id}/visits`)
    visitHistory.value = res.data || []
  } catch {
    ElMessage.error('获取就诊历史失败')
  } finally {
    historyLoading.value = false
  }
}

const openVisitDetail = async (visitId) => {
  detailDialogVisible.value = true
  detailLoading.value = true
  visitDetail.value = null
  try {
    const res = await request.get(`/admin/visits/${visitId}`)
    visitDetail.value = res.data
  } catch {
    ElMessage.error('获取详情失败')
    detailDialogVisible.value = false
  } finally {
    detailLoading.value = false
  }
}

const emptyForm = {
  id: null,
  patient_type: 'student',
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
  counselor_name: '',
  department: '',
  shop_name: '',
  is_temporary: false,
}
const form = ref({ ...emptyForm })

const onTypeChange = (type) => {
  if (type !== 'student') {
    form.value.student_id = ''
    form.value.grade = ''
    form.value.college = ''
    form.value.major = ''
    form.value.class_name = ''
    form.value.counselor_name = ''
  }
  if (type !== 'staff') form.value.department = ''
  if (type !== 'shop') form.value.shop_name = ''
  form.value.is_temporary = (type === 'temporary')
}

const calcAgeFromIdCard = () => {
  const id = form.value.id_card
  if (id && id.length === 18) {
    const year = parseInt(id.substring(6, 10))
    const month = parseInt(id.substring(10, 12)) - 1
    const day = parseInt(id.substring(12, 14))
    const birth = new Date(year, month, day)
    const today = new Date()
    let age = today.getFullYear() - birth.getFullYear()
    if (today.getMonth() < birth.getMonth() ||
       (today.getMonth() === birth.getMonth() && today.getDate() < birth.getDate())) {
      age--
    }
    if (age > 0 && age < 150) form.value.age = age
  }
}

const rules = {
  name: [{ required: true, message: '请输入姓名', trigger: 'blur' }],
}

const importTypeLabel = computed(() => typeLabelMap[importType.value] || '学生')

const uploadUrlWithType = computed(() => {
  const base = import.meta.env.VITE_API_URL
    ? import.meta.env.VITE_API_URL + '/admin/patients/import'
    : '/api/admin/patients/import'
  return base + `?type=${importType.value}`
})

const uploadHeaders = computed(() => ({
  Authorization: `Bearer ${localStorage.getItem('token')}`
}))

const fetchPatients = async () => {
  loading.value = true
  try {
    const params = { page: currentPage.value, size: pageSize.value, keyword: keyword.value }
    if (filterType.value) params.patient_type = filterType.value
    const res = await request.get('/admin/patients', { params })
    patientList.value = res.data || []
    total.value = res.meta?.total || 0
  } catch (error) {
    ElMessage.error(error.msg || '获取人员列表失败')
  } finally {
    loading.value = false
  }
}

const openCreateDialog = () => {
  isEdit.value = false
  form.value = { ...emptyForm }
  dialogVisible.value = true
}

const openEditDialog = (row) => {
  isEdit.value = true
  form.value = {
    id: row.id,
    patient_type: row.patient_type || 'student',
    student_id: row.student_id || '',
    name: row.name || '',
    gender: row.gender || '男',
    age: row.age,
    phone: row.phone || '',
    id_card: row.id_card || '',
    grade: row.grade || '',
    college: row.college || '',
    major: row.major || '',
    class_name: row.class_name || '',
    counselor_name: row.counselor_name || '',
    department: row.department || '',
    shop_name: row.shop_name || '',
    is_temporary: row.is_temporary || false,
  }
  dialogVisible.value = true
}

const submitForm = async () => {
  if (!formRef.value) return
  await formRef.value.validate(async (valid) => {
    if (!valid) return
    submitting.value = true
    try {
      const payload = { ...form.value }
      if (isEdit.value) {
        await request.put(`/admin/patients/${payload.id}`, payload)
        ElMessage.success('更新成功')
      } else {
        await request.post('/admin/patients', payload)
        ElMessage.success('添加成功')
      }
      dialogVisible.value = false
      fetchPatients()
    } catch (error) {
      ElMessage.error(error.msg || '操作失败')
    } finally {
      submitting.value = false
    }
  })
}

const handleDelete = (row) => {
  const typeLabel = typeLabelMap[row.patient_type] || '学生'
  ElMessageBox.confirm(
    `确定要删除${typeLabel} ${row.name}（${row.student_id || row.id_card || '无编号'}）吗？`,
    '警告',
    { confirmButtonText: '确定', cancelButtonText: '取消', type: 'warning' }
  ).then(async () => {
    try {
      await request.delete(`/admin/patients/${row.id}`)
      ElMessage.success('已删除')
      fetchPatients()
    } catch (error) {
      ElMessage.error(error.msg || '删除失败')
    }
  }).catch(() => {})
}

const downloadTemplate = async () => {
  try {
    const res = await request.get('/admin/patients/template', {
      params: { type: importType.value },
      responseType: 'blob'
    })
    const blob = res instanceof Blob ? res : new Blob([res])
    const url = window.URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    const filenameMap = { student: 'students', staff: 'staff', shop: 'shop' }
    link.setAttribute('download', `patients_template_${filenameMap[importType.value] || 'student'}.csv`)
    document.body.appendChild(link)
    link.click()
    document.body.removeChild(link)
  } catch {
    ElMessage.error('模板下载失败')
  }
}

const beforeUpload = (file) => {
  const isCsv = file.name.endsWith('.csv') || file.type === 'text/csv'
  if (!isCsv) ElMessage.error('只能上传 CSV 格式!')
  return isCsv
}

const handleImportSuccess = (response) => {
  ElMessage.success(response.msg || '导入成功')
  showImport.value = false
  fetchPatients()
}

const handleImportError = (error) => {
  try {
    const res = JSON.parse(error.message)
    ElMessage.error(res.msg || '导入失败')
  } catch {
    ElMessage.error('导入失败')
  }
}

onMounted(() => {
  fetchPatients()
})
</script>

<style scoped>
.patient-management {
  padding: 20px;
}
.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  flex-wrap: wrap;
  gap: 10px;
}
.left-panel {
  display: flex;
  gap: 8px;
  align-items: center;
}
.right-panel {
  display: flex;
  gap: 8px;
}
.pagination-wrapper {
  margin-top: 16px;
  display: flex;
  justify-content: flex-end;
}
.import-section {
  text-align: center;
}
</style>
