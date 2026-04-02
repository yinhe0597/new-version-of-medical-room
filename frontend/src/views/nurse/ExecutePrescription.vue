<template>
  <div class="execute-container">
    <el-page-header @back="goBack" content="处方执行与结算" />
    
    <div class="main-content" v-loading="loading">
      <div v-if="visitDetail">
        <!-- 患者信息 -->
        <el-descriptions title="患者信息" border class="mb-20">
          <el-descriptions-item label="姓名">{{ visitDetail.patient.name }}</el-descriptions-item>
          <el-descriptions-item label="学号">{{ visitDetail.patient.student_id }}</el-descriptions-item>
          <el-descriptions-item label="开方医生">{{ visitDetail.doctor_name }}</el-descriptions-item>
          <el-descriptions-item label="开方时间">{{ visitDetail.created_at }}</el-descriptions-item>
          <el-descriptions-item label="诊断">{{ visitDetail.diagnosis || '无' }}</el-descriptions-item>
        </el-descriptions>

        <!-- 药品明细 -->
        <el-table :data="visitDetail.items" border stripe class="mb-20">
          <el-table-column prop="drug_name" label="名称" />
          <el-table-column prop="specification" label="规格" />
          <el-table-column label="用法" width="200">
            <template #default="scope">
              <span v-if="scope.row.type === 1">
                {{ scope.row.usage }} / {{ scope.row.dosage }} / {{ scope.row.frequency }} / {{ scope.row.timing }}
              </span>
              <span v-else style="color: #909399">-</span>
            </template>
          </el-table-column>
          <el-table-column prop="quantity" label="数量" width="100" />
          <el-table-column label="库存状态" width="120">
            <template #default="scope">
              <el-tag v-if="scope.row.type === 1" :type="scope.row.stock >= scope.row.quantity ? 'success' : 'danger'">
                {{ scope.row.stock >= scope.row.quantity ? '充足' : '不足' }}
              </el-tag>
              <el-tag v-else type="info">不限</el-tag>
            </template>
          </el-table-column>
          <el-table-column label="金额" width="120">
            <template #default="scope">
              ¥ {{ scope.row.amount.toFixed(2) }}
            </template>
          </el-table-column>
        </el-table>

        <!-- 结算区域 -->
        <el-card class="payment-card">
          <div class="payment-summary">
            <p>诊察费: ¥ {{ visitDetail.consultation_fee.toFixed(2) }}</p>
            <p class="total">应收总额: ¥ {{ visitDetail.total_amount.toFixed(2) }}</p>
          </div>
          
          <div class="payment-method">
            <span>支付方式：</span>
            <el-radio-group v-model="paymentMethod">
              <el-radio label="cash">现金</el-radio>
              <el-radio label="card">一卡通</el-radio>
              <el-radio label="other">其他</el-radio>
            </el-radio-group>
          </div>

          <div class="action-buttons">
            <el-button @click="goBack">取消</el-button>
            <el-button type="primary" size="large" @click="handleExecute" :loading="executing" :disabled="!canExecute">
              确认收款并完成
            </el-button>
          </div>
        </el-card>
      </div>
    </div>

    <!-- 票据打印弹窗 (Mock) -->
    <el-dialog v-model="showReceipt" title="收费票据" width="400px" center>
      <div class="receipt-preview" id="receipt-print-area">
        <h3 style="text-align: center">校医务室收费凭证</h3>
        <p>时间: {{ receiptData?.paid_at }}</p>
        <p>单号: {{ receiptData?.payment_id }}</p>
        <hr/>
        <p>姓名: {{ visitDetail?.patient.name }} ({{ visitDetail?.patient.student_id }})</p>
        <p>诊断: {{ visitDetail?.diagnosis || '无' }}</p>
        
        <div class="prescription-print-info">
          <p><strong>处方明细：</strong></p>
          <div v-for="item in visitDetail?.items" :key="item.drug_name" class="item-line">
            - {{ item.drug_name }} ({{ item.specification }}) x{{ item.quantity }}
            <br v-if="item.type === 1"/>
            <span v-if="item.type === 1">&nbsp;&nbsp;用法: {{ item.usage }} / {{ item.dosage }} / {{ item.frequency }} / {{ item.timing }}</span>
          </div>
        </div>

        <div v-if="visitDetail?.doctor_advice" class="advice-print-info" style="margin-top: 10px; padding: 5px; border: 1px solid #eee;">
          <p><strong>医生小贴士：</strong></p>
          <p>{{ visitDetail.doctor_advice }}</p>
        </div>

        <hr/>
        <p>金额: ¥ {{ receiptData?.amount.toFixed(2) }}</p>
        <p>支付方式: {{ getPaymentMethodText(paymentMethod) }}</p>
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
import { ref, onMounted, computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import request from '@/api/request'
import { ElMessage } from 'element-plus'

const route = useRoute()
const router = useRouter()
const visitId = route.params.visitId

const visitDetail = ref(null)
const loading = ref(false)
const executing = ref(false)
const paymentMethod = ref('cash')
const showReceipt = ref(false)
const receiptData = ref(null)

const canExecute = computed(() => {
  if (!visitDetail.value) return false
  return visitDetail.value.items.every(item => item.type === 2 || item.stock >= item.quantity)
})

const fetchDetail = async () => {
  loading.value = true
  try {
    const res = await request.get(`/nurse/visits/${visitId}`)
    visitDetail.value = res.data
  } catch (error) {
    ElMessage.error('获取处方详情失败')
  } finally {
    loading.value = false
  }
}

const handleExecute = async () => {
  executing.value = true
  try {
    const res = await request.post(`/nurse/visits/${visitId}/execute`, {
      payment_method: paymentMethod.value
    })
    receiptData.value = res.data
    showReceipt.value = true
    ElMessage.success('结算成功')
  } catch (error) {
    ElMessage.error(error.msg || '结算失败')
  } finally {
    executing.value = false
  }
}

const printReceipt = async () => {
  try {
    await request.put(`/nurse/payments/${receiptData.value.payment_id}/print`)
    window.print() // Browser print
    showReceipt.value = false
    router.push('/nurse/pending')
  } catch (error) {
    console.error(error)
  }
}

const goBack = () => {
  router.push('/nurse/pending')
}

const getPaymentMethodText = (val) => {
  const map = { 'cash': '现金', 'card': '一卡通', 'other': '其他' }
  return map[val]
}

onMounted(() => {
  fetchDetail()
})
</script>

<style scoped>
.execute-container {
  padding: 20px;
}
.main-content {
  margin-top: 20px;
  max-width: 800px;
  margin-left: auto;
  margin-right: auto;
}
.mb-20 {
  margin-bottom: 20px;
}
.payment-card {
  text-align: right;
}
.payment-summary {
  font-size: 16px;
  margin-bottom: 20px;
}
.total {
  font-size: 24px;
  font-weight: bold;
  color: #f56c6c;
}
.payment-method {
  margin-bottom: 30px;
}
.receipt-preview {
  font-family: 'Courier New', Courier, monospace;
  padding: 10px;
  border: 1px dashed #ccc;
}
.item-line {
  font-size: 12px;
  margin-bottom: 5px;
  line-height: 1.4;
}
.advice-print-info {
  font-size: 12px;
  background-color: #fdf6ec;
}
</style>
