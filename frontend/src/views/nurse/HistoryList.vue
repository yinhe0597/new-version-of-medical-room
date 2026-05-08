<template>
  <div class="history-list-container">
    <h2>历史诊疗记录</h2>

    <div class="filter-bar">
      <el-input
        v-model="searchName"
        placeholder="搜索患者姓名"
        :prefix-icon="Search"
        clearable
        style="width: 220px"
      />
      <el-select v-model="filterStatus" placeholder="全部状态" clearable style="width: 150px">
        <el-option label="全部" value="" />
        <el-option label="待处理" value="pending" />
        <el-option label="已审核" value="nurse_verified" />
        <el-option label="已完成" value="completed" />
        <el-option label="已驳回" value="rejected" />
      </el-select>
    </div>

    <el-table :data="filteredList" v-loading="loading" stripe style="width: 100%">
      <el-table-column prop="created_at" label="就诊时间" width="180" />
      <el-table-column prop="patient_name" label="患者姓名" width="120" />
      <el-table-column prop="student_id" label="学号" width="150" />
      <el-table-column prop="doctor_name" label="医生" width="120" />
      <el-table-column prop="diagnosis" label="诊断" min-width="160" show-overflow-tooltip />
      <el-table-column label="费用总额" width="120">
        <template #default="scope">
          ¥{{ scope.row.total_amount.toFixed(2) }}
        </template>
      </el-table-column>
      <el-table-column label="状态" width="100">
        <template #default="scope">
          <el-tag :type="getStatusTagType(scope.row.status)">
            {{ getStatusText(scope.row.status) }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="140">
        <template #default="scope">
          <el-button
            v-if="scope.row.status === 'completed'"
            type="primary"
            link
            @click="openDetail(scope.row)"
          >
            编辑处置情况
          </el-button>
          <el-button
            v-else
            type="info"
            link
            @click="openDetail(scope.row)"
          >
            查看详情
          </el-button>
        </template>
      </el-table-column>
      <template #empty>暂无历史记录</template>
    </el-table>

    <el-dialog v-model="showDetail" title="编辑处置情况" width="580px">
      <div v-if="currentRow" class="detail-info">
        <el-descriptions :column="2" border>
          <el-descriptions-item label="患者姓名">{{ currentRow.patient_name }}</el-descriptions-item>
          <el-descriptions-item label="学号">{{ currentRow.student_id }}</el-descriptions-item>
          <el-descriptions-item label="医生姓名">{{ currentRow.doctor_name }}</el-descriptions-item>
          <el-descriptions-item label="就诊时间">{{ currentRow.created_at }}</el-descriptions-item>
          <el-descriptions-item label="诊断" :span="2">{{ currentRow.diagnosis || '无' }}</el-descriptions-item>
          <el-descriptions-item label="费用总额">¥{{ currentRow.total_amount.toFixed(2) }}</el-descriptions-item>
          <el-descriptions-item label="当前状态">
            <el-tag :type="getStatusTagType(currentRow.status)">
              {{ getStatusText(currentRow.status) }}
            </el-tag>
          </el-descriptions-item>
        </el-descriptions>

        <div v-if="currentRow.revoked_at" class="revoke-info">
          <el-alert type="warning" :closable="false" show-icon>
            <template #title>
              <span>撤销时间：{{ currentRow.revoked_at }}</span>
            </template>
            <template #default>
              <span>撤销原因：{{ currentRow.revoke_reason || '-' }}</span>
            </template>
          </el-alert>
        </div>
      </div>

      <template #footer>
        <el-button
          v-if="currentRow && currentRow.status === 'completed'"
          type="danger"
          @click="handleRevoke"
        >
          撤销交易
        </el-button>
        <el-button @click="showDetail = false">关闭</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import request from '@/api/request'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Search } from '@element-plus/icons-vue'

const loading = ref(false)
const historyList = ref([])
const searchName = ref('')
const filterStatus = ref('')
const showDetail = ref(false)
const currentRow = ref(null)

const filteredList = computed(() => {
  let list = historyList.value
  if (searchName.value) {
    const keyword = searchName.value.trim().toLowerCase()
    list = list.filter(item => item.patient_name && item.patient_name.toLowerCase().includes(keyword))
  }
  if (filterStatus.value) {
    list = list.filter(item => item.status === filterStatus.value)
  }
  return list
})

const getStatusText = (status) => {
  const map = {
    pending: '待处理',
    nurse_verified: '已审核',
    completed: '已完成',
    rejected: '已驳回'
  }
  return map[status] || status
}

const getStatusTagType = (status) => {
  const map = {
    pending: 'warning',
    nurse_verified: '',
    completed: 'success',
    rejected: 'danger'
  }
  return map[status] ?? 'info'
}

const fetchHistory = async () => {
  loading.value = true
  try {
    const res = await request.get('/nurse/my-history')
    historyList.value = res.data || []
  } catch (error) {
    ElMessage.error(error.msg || '获取历史记录失败')
  } finally {
    loading.value = false
  }
}

const openDetail = (row) => {
  currentRow.value = row
  showDetail.value = true
}

const handleRevoke = () => {
  const visitId = currentRow.value.visit_id
  ElMessageBox.prompt(
    '此操作将撤销该处方的交易，处方将恢复为待处理状态，库存将自动还原。请输入撤销原因：',
    '撤销交易确认',
    {
      confirmButtonText: '确认撤销',
      cancelButtonText: '取消',
      inputPlaceholder: '请输入撤销原因（必填）',
      inputValidator: (val) => {
        if (!val || !val.trim()) return '撤销原因不能为空'
        return true
      }
    }
  ).then(async ({ value }) => {
    try {
      await request.post(`/nurse/visits/${visitId}/revoke`, { reason: value.trim() })
      ElMessage.success('交易已成功撤销')
      showDetail.value = false
      await fetchHistory()
    } catch (error) {
      ElMessage.error(error.msg || '撤销失败')
    }
  }).catch(() => {})
}

onMounted(() => {
  fetchHistory()
})
</script>

<style scoped>
.history-list-container {
  padding: 20px;
}
.filter-bar {
  display: flex;
  gap: 12px;
  margin-bottom: 16px;
}
.detail-info {
  margin-bottom: 10px;
}
.revoke-info {
  margin-top: 16px;
}
</style>
