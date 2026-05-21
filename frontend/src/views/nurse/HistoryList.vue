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
        <el-option label="已撤销" value="revoked" />
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
      <el-table-column label="操作" width="180">
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
          <el-button
            v-if="scope.row.status === 'completed' && scope.row.payment_id"
            type="success"
            link
            @click="openReceipt(scope.row)"
          >
            打印小票
          </el-button>
        </template>
      </el-table-column>
      <template #empty>暂无历史记录</template>
    </el-table>

    <!-- 编辑处置对话框 -->
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

    <!-- 收费票据对话框 -->
    <el-dialog v-model="showReceipt" title="收费票据" width="400px" center>
      <div v-loading="receiptLoading" class="receipt-preview" id="receipt-print-area">
        <h3 style="text-align: center">校医务室收费凭证</h3>
        <p>时间: {{ receiptRow?.paid_at }}</p>
        <p>单号: {{ receiptRow?.payment_id }}</p>
        <hr/>
        <p>姓名: {{ receiptVisit?.patient?.name }} ({{ receiptVisit?.patient?.student_id }})</p>
        <p>诊断: {{ receiptVisit?.diagnosis || '无' }}</p>

        <div class="prescription-print-info">
          <p><strong>处方明细：</strong></p>
          <div v-for="item in receiptVisit?.items" :key="item.item_id" class="item-line">
            - {{ item.drug_name }} ({{ item.specification }}) x{{ item.quantity }}
            <br v-if="item.type === 1" />
            <span v-if="item.type === 1">&nbsp;&nbsp;用法: {{ formatUsageLine(item) }}</span>
          </div>
        </div>

        <div v-if="receiptVisit?.doctor_advice" class="advice-print-info" style="margin-top: 10px; padding: 5px; border: 1px solid #eee;">
          <p><strong>医生小贴士：</strong></p>
          <p>{{ receiptVisit.doctor_advice }}</p>
        </div>

        <div v-if="receiptVisit?.special_note" style="margin-top: 10px; padding: 5px; border: 1px solid #e6a23c; background: #fdf6ec;">
          <p><strong>特殊配药备注：</strong></p>
          <p>{{ receiptVisit.special_note }}</p>
        </div>

        <hr/>
        <p v-if="receiptRow?.payment_original_amount">应收: ¥ {{ receiptRow?.payment_original_amount.toFixed(2) }}</p>
        <p v-if="receiptRow?.payment_original_amount">优惠类型: 职工优惠</p>
        <p>{{ receiptRow?.payment_original_amount ? '实收' : '金额' }}: ¥ {{ (receiptRow?.payment_amount || 0).toFixed(2) }}</p>
        <p>支付方式: {{ getPaymentMethodText(receiptRow?.payment_method) }}</p>
        <hr/>
        <p style="text-align: center">盖章有效</p>
      </div>
      <template #footer>
        <el-button @click="showReceipt = false">关闭</el-button>
        <el-button type="primary" @click="printReceipt">打印</el-button>
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

// 票据相关
const showReceipt = ref(false)
const receiptLoading = ref(false)
const receiptRow = ref(null)
const receiptVisit = ref(null)

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
    rejected: '已驳回',
    revoked: '已撤销'
  }
  return map[status] || status
}

const getStatusTagType = (status) => {
  const map = {
    pending: 'warning',
    nurse_verified: '',
    completed: 'success',
    rejected: 'danger',
    revoked: 'info'
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

const openReceipt = async (row) => {
  receiptRow.value = row
  receiptLoading.value = true
  showReceipt.value = true
  try {
    const res = await request.get(`/nurse/visits/${row.visit_id}`)
    receiptVisit.value = res.data
  } catch (error) {
    ElMessage.error(error.msg || '获取处方详情失败')
    showReceipt.value = false
  } finally {
    receiptLoading.value = false
  }
}

const printReceipt = async () => {
  const pid = receiptRow.value?.payment_id
  if (pid) {
    try {
      await request.put(`/nurse/payments/${pid}/print`)
    } catch (error) {
      console.error(error)
    }
  }
  window.print()
  showReceipt.value = false
}

const getPaymentMethodText = (val) => {
  const map = { 'cash': '现金', 'card': '一卡通', 'other': '其他' }
  return map[val] || val
}

const safeText = (val) => {
  const s = String(val == null ? '' : val).trim()
  if (!s) return '-'
  if (s.includes('?')) return '-'
  return s
}

const formatUsageLine = (row) => {
  if (!row) return '-'
  if (row.is_intravenous) {
    const parts = [`配伍${row.infusion_group || '?'}`]
    if (row.infusion_dosage_value) parts.push(`${row.infusion_dosage_value}${row.infusion_dosage_unit || ''}`)
    if (row.infusion_method) parts.push(row.infusion_method)
    return parts.join(' / ')
  }
  return `${safeText(row.usage)} / ${safeText(row.dosage)} / ${safeText(row.frequency)} / ${safeText(row.timing)}`
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

<style>
@media print {
  /* 彻底隐藏主应用容器，不占用打印页面空间 */
  #app {
    display: none !important;
  }

  /* Element Plus Dialog 默认 teleport 到 body，保留 overlay */
  .el-overlay {
    display: block !important;
    position: static !important;
    background: transparent !important;
  }

  .el-overlay-dialog {
    position: static !important;
  }

  .el-dialog {
    position: static !important;
    box-shadow: none !important;
    margin: 0 !important;
    width: 100% !important;
    max-width: 100% !important;
  }

  /* 隐藏对话框标题、关闭按钮、底部按钮 */
  .el-dialog__header,
  .el-dialog__footer,
  .el-dialog__headerbtn {
    display: none !important;
  }

  .el-dialog__body {
    padding: 10px !important;
  }

  /* 票据打印区域 */
  #receipt-print-area {
    visibility: visible !important;
    position: static !important;
    width: 100%;
  }

  #receipt-print-area * {
    visibility: visible !important;
  }
}
</style>

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
.receipt-preview {
  line-height: 1.6;
}
.receipt-preview p {
  margin: 4px 0;
}
.receipt-preview .item-line {
  margin: 2px 0 2px 10px;
}
.advice-print-info {
  font-size: 13px;
}
</style>
