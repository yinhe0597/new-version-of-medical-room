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
        <el-table-column label="操作" width="120" fixed="right">
          <template #default="scope">
            <el-button size="small" type="primary" link @click="openCaseReview(scope.row.id)">
              病例复盘
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
      <div v-loading="detailLoading" v-if="visitDetail" class="case-review">
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
        <el-button @click="dialogVisible = false">关闭</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import request from '@/api/request'
import { ElMessage } from 'element-plus'

const historyList = ref([])
const loading = ref(false)
const startDate = ref('')
const page = ref(1)
const pageSize = ref(20)
const total = ref(0)

const dialogVisible = ref(false)
const detailLoading = ref(false)
const visitDetail = ref(null)

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
    'rejected': 'danger'
  }
  return map[status] || ''
}

const getStatusText = (status) => {
  const map = {
    'pending': '待护士核验',
    'nurse_verified': '护士已核验',
    'completed': '已完成',
    'rejected': '已驳回'
  }
  return map[status] || status
}

const openCaseReview = async (visitId) => {
  dialogVisible.value = true
  detailLoading.value = true
  try {
    const res = await request.get(`/doctor/visits/${visitId}`)
    visitDetail.value = res.data
  } catch (error) {
    ElMessage.error('获取详情失败')
    dialogVisible.value = false
  } finally {
    detailLoading.value = false
  }
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
