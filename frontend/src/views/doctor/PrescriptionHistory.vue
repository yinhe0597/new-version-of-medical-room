<template>
  <div class="history-container">
    <el-card>
      <template #header>
        <div class="card-header">
          <span>历史就诊记录</span>
          <div class="filter-box">
            <el-date-picker
              v-model="startDate"
              type="date"
              placeholder="开始日期"
              value-format="YYYY-MM-DD"
              @change="fetchHistory"
            />
          </div>
        </div>
      </template>
      
      <el-table :data="historyList" v-loading="loading" stripe style="width: 100%">
        <el-table-column prop="date" label="就诊时间" width="180" />
        <el-table-column prop="patient_name" label="患者姓名" width="120" />
        <el-table-column prop="diagnosis" label="诊断" />
        <el-table-column prop="total_amount" label="总金额" width="120">
          <template #default="scope">
            ¥ {{ scope.row.total_amount.toFixed(2) }}
          </template>
        </el-table-column>
        <el-table-column prop="status" label="状态" width="100">
          <template #default="scope">
            <el-tag :type="getStatusType(scope.row.status)">
              {{ getStatusText(scope.row.status) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="220" fixed="right">
          <template #default="scope">
            <el-button size="small" type="primary" link @click="openCaseReview(scope.row.id)">
              病例复盘
            </el-button>
            <el-button
              v-if="scope.row.status !== 'rejected'"
              size="small"
              type="success"
              link
              @click="openSupplementDialog(scope.row)"
            >
              修改病历
            </el-button>
            <el-button
              v-if="scope.row.status === 'rejected' || scope.row.status === 'revoked'"
              size="small"
              type="warning"
              link
              @click="reopenPrescription(scope.row)"
            >
              重新开方
            </el-button>
          </template>
        </el-table-column>
      </el-table>
      
      <div class="pagination">
        <el-pagination
          background
          layout="prev, pager, next"
          :total="total"
          :page-size="pageSize"
          @current-change="handlePageChange"
        />
      </div>
    </el-card>

    <!-- 病例复盘弹窗 -->
    <el-dialog v-model="dialogVisible" title="病例复盘" width="800px">
      <div ref="printRef" v-loading="detailLoading" v-if="visitDetail" class="case-review">
        <el-descriptions border :column="2" title="患者信息">
          <el-descriptions-item label="姓名">{{ visitDetail.patient.name || '-' }}</el-descriptions-item>
          <el-descriptions-item label="学号/工号">{{ visitDetail.patient.student_id || '-' }}</el-descriptions-item>
          <el-descriptions-item label="性别">{{ visitDetail.patient.gender || '-' }}</el-descriptions-item>
          <el-descriptions-item label="电话">{{ visitDetail.patient.phone || '-' }}</el-descriptions-item>
          <el-descriptions-item label="年级">{{ visitDetail.patient.grade || '-' }}</el-descriptions-item>
          <el-descriptions-item label="学院">{{ visitDetail.patient.college || '-' }}</el-descriptions-item>
          <el-descriptions-item label="专业">{{ visitDetail.patient.major || '-' }}</el-descriptions-item>
          <el-descriptions-item label="班级">{{ visitDetail.patient.class_name || '-' }}</el-descriptions-item>
          <el-descriptions-item label="就诊时间" :span="2">{{ visitDetail.created_at }}</el-descriptions-item>
          <el-descriptions-item label="状态">{{ getStatusText(visitDetail.status) }}</el-descriptions-item>
          <el-descriptions-item v-if="visitDetail.status === 'rejected'" label="驳回原因" :span="2">
            {{ visitDetail.reject_reason || '-' }}
          </el-descriptions-item>
        </el-descriptions>

        <el-descriptions border :column="1" title="电子病历" direction="vertical" style="margin-top: 20px;">
          <el-descriptions-item label="主诉">{{ visitDetail.chief_complaint || '无' }}</el-descriptions-item>
          <el-descriptions-item label="现病史">{{ visitDetail.present_illness || '无' }}</el-descriptions-item>
          <el-descriptions-item label="既往史（过敏史）">{{ visitDetail.past_history || '无' }}</el-descriptions-item>
          <el-descriptions-item label="体格检查">{{ visitDetail.physical_exam || '无' }}</el-descriptions-item>
          <el-descriptions-item label="诊断" label-class-name="highlight-label">{{ visitDetail.diagnosis || '无' }}</el-descriptions-item>
          <el-descriptions-item label="医生留言">{{ visitDetail.doctor_advice || '无' }}</el-descriptions-item>
        </el-descriptions>

        <!-- 修改记录 -->
        <div v-if="revisions.length > 0" style="margin-top: 20px;">
          <el-divider content-position="left">修改记录</el-divider>
          <el-timeline>
            <el-timeline-item
              v-for="rev in revisions"
              :key="rev.id"
              :timestamp="rev.timestamp"
              placement="top"
            >
              <el-card shadow="never" :body-style="{ padding: '10px' }">
                <p style="margin: 0; font-size: 13px; color: #606266;">
                  <strong>{{ rev.user_name }}</strong> {{ rev.summary }}
                </p>
                <div v-if="rev.details && rev.details.changes" style="margin-top: 8px;">
                  <div v-for="(change, field) in rev.details.changes" :key="field"
                       style="font-size: 12px; color: #909399; margin-top: 4px;">
                    <span>{{ fieldLabel(field) }}：</span>
                    <span style="text-decoration: line-through; color: #F56C6C;">{{ change.old || '(空)' }}</span>
                    <span> → </span>
                    <span style="color: #67C23A;">{{ change.new || '(空)' }}</span>
                  </div>
                </div>
              </el-card>
            </el-timeline-item>
          </el-timeline>
        </div>

        <div style="margin-top: 20px;">
          <div style="font-size: 16px; font-weight: bold; margin-bottom: 10px;">处方明细</div>
          <el-table :data="visitDetail.items" border stripe size="small">
            <el-table-column prop="drug_name" label="药品名称" />
            <el-table-column prop="specification" label="规格" width="120" />
            <el-table-column label="用法" min-width="180">
              <template #default="scope">
                {{ scope.row.usage }} / {{ scope.row.dosage }} / {{ scope.row.frequency }} / {{ scope.row.timing }} ({{ scope.row.days }}天)
              </template>
            </el-table-column>
            <el-table-column prop="quantity" label="数量" width="80" />
            <el-table-column label="金额" width="80">
              <template #default="scope">¥ {{ scope.row.amount.toFixed(2) }}</template>
            </el-table-column>
          </el-table>
        </div>
      </div>
      <template #footer>
        <el-button type="primary" :disabled="detailLoading || !visitDetail" @click="exportCaseReviewPdf">导出PDF</el-button>
        <el-button @click="dialogVisible = false">关闭</el-button>
      </template>
    </el-dialog>

    <!-- 修改病历弹窗 -->
    <el-dialog v-model="supplementDialogVisible" title="修改病历" width="700px">
      <el-form :model="supplementForm" label-position="top">
        <el-form-item label="主诉">
          <el-input v-model="supplementForm.chief_complaint" type="textarea" :rows="2" placeholder="请填写主诉"></el-input>
        </el-form-item>
        <el-form-item label="现病史">
          <el-input v-model="supplementForm.present_illness" type="textarea" :rows="3" placeholder="请填写现病史"></el-input>
        </el-form-item>
        <el-form-item label="既往史（过敏史）">
          <el-input v-model="supplementForm.past_history" type="textarea" :rows="2" placeholder="请填写既往史"></el-input>
        </el-form-item>
        <el-form-item label="体格检查">
          <el-input v-model="supplementForm.physical_exam" type="textarea" :rows="2" placeholder="请填写体格检查"></el-input>
        </el-form-item>
        <el-form-item label="医生留言/小贴士">
          <el-input v-model="supplementForm.doctor_advice" type="textarea" :rows="2" placeholder="给患者的自定义建议..."></el-input>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="supplementDialogVisible = false" :disabled="supplementSubmitting">取消</el-button>
        <el-button type="primary" @click="submitSupplement" :loading="supplementSubmitting">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, onMounted, nextTick } from 'vue'
import { useRouter } from 'vue-router'
import request from '@/api/request'
import { ElMessage } from 'element-plus'

const router = useRouter()
const historyList = ref([])
const loading = ref(false)
const startDate = ref('')
const page = ref(1)
const pageSize = ref(20)
const total = ref(0)

const dialogVisible = ref(false)
const detailLoading = ref(false)
const visitDetail = ref(null)
const printRef = ref(null)

// 修改记录
const revisions = ref([])
const revisionsLoading = ref(false)

const loadRevisions = async (visitId) => {
  revisionsLoading.value = true
  try {
    const res = await request.get(`/doctor/visits/${visitId}/revisions`)
    revisions.value = res.data.data || res.data || []
  } catch (e) {
    revisions.value = []
  } finally {
    revisionsLoading.value = false
  }
}

const fieldLabel = (field) => {
  const map = {
    'chief_complaint': '主诉',
    'present_illness': '现病史',
    'past_history': '既往史',
    'physical_exam': '体格检查',
    'doctor_advice': '医生留言',
    'special_note': '特殊备注'
  }
  return map[field] || field
}

// 补充病历状态
const supplementDialogVisible = ref(false)
const supplementSubmitting = ref(false)
const supplementVisitId = ref(null)
const supplementForm = ref({
  chief_complaint: '',
  present_illness: '',
  past_history: '',
  physical_exam: '',
  doctor_advice: ''
})

const fetchHistory = async () => {
  loading.value = true
  try {
    const res = await request.get('/doctor/visits/history', {
      params: {
        page: page.value,
        size: pageSize.value,
        start_date: startDate.value
      }
    })
    historyList.value = res.data
    total.value = res.meta.total
  } catch (error) {
    console.error(error)
  } finally {
    loading.value = false
  }
}

const handlePageChange = (val) => {
  page.value = val
  fetchHistory()
}

const getStatusType = (status) => {
  const map = {
    'pending': 'warning',
    'nurse_verified': 'info',
    'completed': 'success',
    'rejected': 'danger',
    'revoked': 'info'
  }
  return map[status] || ''
}

const getStatusText = (status) => {
  const map = {
    'pending': '待护士核验',
    'nurse_verified': '护士已核验',
    'completed': '已完成',
    'rejected': '已驳回',
    'revoked': '已撤销'
  }
  return map[status] || status
}

const openCaseReview = async (visitId) => {
  dialogVisible.value = true
  detailLoading.value = true
  revisions.value = []
  try {
    const res = await request.get(`/doctor/visits/${visitId}`)
    visitDetail.value = res.data
    loadRevisions(visitId)
  } catch (error) {
    ElMessage.error('获取详情失败')
    dialogVisible.value = false
  } finally {
    detailLoading.value = false
  }
}

const exportCaseReviewPdf = async () => {
  if (!visitDetail.value) return
  await nextTick()
  if (!printRef.value) return

  const win = window.open('', '_blank')
  if (!win) {
    ElMessage.error('浏览器拦截了弹窗，请允许弹窗后重试')
    return
  }

  const patientName = visitDetail.value.patient?.name || '患者'
  const createdAt = visitDetail.value.created_at || ''
  const title = `${patientName}-病例复盘${createdAt ? `-${createdAt}` : ''}`
  const styles = Array.from(document.querySelectorAll('link[rel="stylesheet"], style'))
    .map((el) => el.outerHTML)
    .join('\n')

  const contentHtml = printRef.value.outerHTML
  const scriptTagOpen = '<scr' + 'ipt>'
  const scriptTagClose = '</scr' + 'ipt>'
  const html = `<!doctype html>
<html lang="zh-CN">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>${title}</title>
    ${styles}
    <style>
      @page { size: A4; margin: 12mm; }
      body { color: #000; background: #fff; }
      .print-header { font-size: 18px; font-weight: 700; margin: 0 0 12px 0; }
      .print-sub { font-size: 12px; color: #666; margin: 0 0 16px 0; }
      table { page-break-inside: avoid; }
    </style>
  </head>
  <body>
    <div class="print-header">病例复盘</div>
    <div class="print-sub">${patientName}${createdAt ? ` · ${createdAt}` : ''}</div>
    ${contentHtml}
    ${scriptTagOpen}
      window.onload = () => {
        setTimeout(() => {
          window.focus()
          window.print()
        }, 200)
      }
      window.onafterprint = () => {
        window.close()
      }
    ${scriptTagClose}
  </body>
</html>`

  win.document.open()
  win.document.write(html)
  win.document.close()
}

const openSupplementDialog = async (row) => {
  supplementVisitId.value = row.id
  supplementForm.value = {
    chief_complaint: '',
    present_illness: '',
    past_history: '',
    physical_exam: '',
    doctor_advice: ''
  }
  try {
    const res = await request.get(`/doctor/visits/${row.id}`)
    const detail = res.data || {}
    supplementForm.value.chief_complaint = detail.chief_complaint || ''
    supplementForm.value.present_illness = detail.present_illness || ''
    supplementForm.value.past_history = detail.past_history || ''
    supplementForm.value.physical_exam = detail.physical_exam || ''
    supplementForm.value.doctor_advice = detail.doctor_advice || ''
  } catch (error) {
    ElMessage.error(error.msg || '获取就诊详情失败')
    return
  }
  supplementDialogVisible.value = true
}

const submitSupplement = async () => {
  const fields = ['chief_complaint', 'present_illness', 'past_history', 'physical_exam', 'doctor_advice']
  const payload = {}
  let hasValue = false
  for (const field of fields) {
    const val = (supplementForm.value[field] || '').trim()
    if (val) {
      payload[field] = val
      hasValue = true
    }
  }
  if (!hasValue) {
    ElMessage.warning('请至少填写一项病历信息')
    return
  }
  supplementSubmitting.value = true
  try {
    await request.put(`/doctor/visits/${supplementVisitId.value}/medical-record`, payload)
    ElMessage.success('病历修改成功')
    supplementDialogVisible.value = false
    fetchHistory()
  } catch (error) {
    ElMessage.error(error.msg || '保存失败')
  } finally {
    supplementSubmitting.value = false
  }
}

const reopenPrescription = (row) => {
  router.push({
    path: '/doctor/visit',
    query: {
      patient_id: row.patient_id,
      patient_name: row.patient_name,
      student_id: row.student_id || '',
      source_visit_id: row.id
    }
  })
}

onMounted(() => {
  fetchHistory()
})
</script>

<style scoped>
.history-container {
  padding: 20px;
}
.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.pagination {
  margin-top: 20px;
  display: flex;
  justify-content: flex-end;
}
.case-review :deep(.highlight-label) {
  color: #f56c6c;
  font-weight: bold;
}
</style>
