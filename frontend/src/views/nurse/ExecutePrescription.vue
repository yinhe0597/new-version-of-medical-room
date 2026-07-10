<template>
  <div class="execute-container">
    <el-page-header @back="goBack" content="处方执行与结算" />
    
    <div class="main-content" v-loading="loading">
      <div v-if="visitDetail">
        <el-descriptions title="患者信息" border class="mb-20">
          <el-descriptions-item label="姓名">{{ visitDetail.patient.name }}</el-descriptions-item>
          <el-descriptions-item label="学号">{{ visitDetail.patient.student_id }}</el-descriptions-item>
          <el-descriptions-item label="开方医生">{{ visitDetail.doctor_name }}</el-descriptions-item>
          <el-descriptions-item label="开方时间">{{ visitDetail.created_at }}</el-descriptions-item>
          <el-descriptions-item label="诊断">
            <div style="white-space: pre-line;">{{ visitDetail.diagnosis || '无' }}</div>
          </el-descriptions-item>
          <el-descriptions-item label="处方状态">
            <el-tag :type="getStatusTagType(visitDetail.status)">
              {{ getStatusText(visitDetail.status) }}
            </el-tag>
          </el-descriptions-item>
          <el-descriptions-item v-if="visitDetail.special_note" label="特殊配药备注" :span="3">
            <span style="color: #e6a23c; font-weight: bold;">{{ visitDetail.special_note }}</span>
          </el-descriptions-item>
          <el-descriptions-item v-if="visitDetail.status === 'rejected'" label="驳回原因" :span="3">
            {{ visitDetail.reject_reason || '-' }}
          </el-descriptions-item>
        </el-descriptions>

        <el-card v-if="hasServiceItems && canModify" class="mb-20">
          <div style="margin-bottom: 15px;">
            <span style="font-weight: bold; margin-right: 10px;">诊疗项目/耗材管理</span>
            <el-button size="small" type="primary" @click="openAddServiceDialog">
              + 添加项目
            </el-button>
          </div>
          
          <el-table :data="serviceItems" border stripe>
            <el-table-column prop="drug_name" label="项目名称" />
            <el-table-column prop="specification" label="规格" />
            <el-table-column prop="quantity" label="数量" width="100">
              <template #default="scope">
                <el-input-number 
                  v-if="canModify"
                  v-model="scope.row.quantity" 
                  :min="1" 
                  :max="99"
                  :disabled="!canModify"
                  @change="handleServiceQuantityChange(scope.row)"
                />
                <span v-else>{{ scope.row.quantity }}</span>
              </template>
            </el-table-column>
            <el-table-column label="单价" width="120">
              <template #default="scope">¥ {{ scope.row.unit_price.toFixed(2) }}</template>
            </el-table-column>
            <el-table-column label="金额" width="120">
              <template #default="scope">¥ {{ scope.row.amount.toFixed(2) }}</template>
            </el-table-column>
            <el-table-column label="操作" width="100">
              <template #default="scope">
                <el-button 
                  size="small" 
                  type="danger" 
                  @click="handleDeleteService(scope.row)"
                  :disabled="!canModify"
                >
                  删除
                </el-button>
              </template>
            </el-table-column>
          </el-table>
          
          <div v-if="serviceItems.length === 0 && hasServiceItems" style="text-align: center; color: #909399; padding: 20px;">
            暂无诊疗项目
          </div>
        </el-card>

        <el-table :data="drugItems" border stripe class="mb-20">
          <el-table-column prop="drug_name" label="药品名称" />
          <el-table-column prop="specification" label="规格" />
          <el-table-column label="用法" width="200">
            <template #default="scope">
              <span>{{ formatUsageLine(scope.row) }}</span>
            </template>
          </el-table-column>
          <el-table-column prop="quantity" label="数量" width="100" />
          <el-table-column label="库存状态" width="120">
            <template #default="scope">
              <el-tag :type="scope.row.stock >= getStockNeeded(scope.row) ? 'success' : 'danger'">
                {{ scope.row.stock >= getStockNeeded(scope.row) ? '充足' : '不足' }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column label="单价" width="120">
            <template #default="scope">
              ¥ {{ scope.row.unit_price.toFixed(2) }}
            </template>
          </el-table-column>
          <el-table-column label="金额" width="120">
            <template #default="scope">
              ¥ {{ scope.row.amount.toFixed(2) }}
            </template>
          </el-table-column>
          <el-table-column label="改价" width="100">
            <template #default="scope">
              <el-tag v-if="scope.row.modified_at" type="warning">已改价</el-tag>
              <span v-else style="color: #909399">-</span>
            </template>
          </el-table-column>
          <el-table-column label="操作" width="120">
            <template #default="scope">
              <el-button size="small" @click="openModifyDialog(scope.row)" :disabled="!canModify">
                改价
              </el-button>
            </template>
          </el-table-column>
        </el-table>

        <el-card v-if="visitDetail.status === 'pending' || visitDetail.status === 'nurse_verified'" class="mb-20">
          <div class="verify-actions">
            <el-button v-if="visitDetail.status === 'pending'" type="success" :loading="verifying" @click="handleVerify">
              确认处方无误
            </el-button>
            <el-button type="danger" @click="openRejectDialog">
              驳回
            </el-button>
          </div>
        </el-card>

        <el-card class="payment-card">
          <div class="payment-summary">
            <p>诊察费: ¥ {{ visitDetail.consultation_fee.toFixed(2) }}</p>
            <p class="total">应收总额: ¥ {{ visitDetail.total_amount.toFixed(2) }}</p>
          </div>

          <div class="discount-section" style="margin-top: 10px;">
            <el-checkbox v-if="visitDetail.patient?.patient_type === 'staff'" v-model="employeeDiscount">职工优惠</el-checkbox>
            <div v-if="employeeDiscount" style="margin-top: 12px;">
              <div style="margin-bottom: 8px; display: flex; align-items: center; gap: 8px;">
                <span style="min-width: 90px;">实收诊查费：</span>
                <el-input-number 
                  v-model="actualConsultationFee" 
                  :min="0" 
                  :precision="2" 
                  :step="0.5"
                  size="small"
                />
                <span>元</span>
                <span style="color: #909399; font-size: 12px;">（应收 ¥{{ visitDetail.consultation_fee.toFixed(2) }}）</span>
              </div>
              <div style="display: flex; align-items: center; gap: 8px;">
                <span style="min-width: 120px;">实收物资及项目：</span>
                <el-input-number 
                  v-model="actualDrugAmount" 
                  :min="0" 
                  :precision="2" 
                  :step="0.5"
                  size="small"
                />
                <span>元</span>
                <span style="color: #909399; font-size: 12px;">（应收 ¥{{ itemTotalFromItems.toFixed(2) }}，药品成本参考 ¥{{ drugCostTotal.toFixed(2) }}）</span>
              </div>
              <div style="margin-top: 4px; color: #409eff; font-size: 13px;">
                合计实收：¥ {{ (actualConsultationFee + actualDrugAmount).toFixed(2) }}
              </div>
            </div>
          </div>
          
          <div class="payment-method">
            <span>支付方式：</span>
            <el-radio-group v-model="paymentMethod">
              <el-radio label="cash">现金</el-radio>
              <el-radio label="card">一卡通</el-radio>
              <el-radio label="other">其他</el-radio>
            </el-radio-group>
          </div>

          <el-alert v-if="executeDisabledReason" type="warning" :closable="false" class="mb-20">
            {{ executeDisabledReason }}
          </el-alert>

          <div class="action-buttons">
            <el-button @click="goBack">取消</el-button>
            <el-button type="primary" size="large" @click="handleExecute" :loading="executing" :disabled="!canExecute">
              确认收款并完成
            </el-button>
          </div>
        </el-card>
      </div>
    </div>

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
          <div v-for="item in visitDetail?.items" :key="item.item_id" class="item-line">
            - {{ item.drug_name }} ({{ item.specification }}) x{{ item.quantity }}
            <br v-if="item.type === 1"/>
            <span v-if="item.type === 1">&nbsp;&nbsp;用法: {{ formatUsageLine(item) }}</span>
          </div>
        </div>

        <div v-if="visitDetail?.doctor_advice" class="advice-print-info" style="margin-top: 10px; padding: 5px; border: 1px solid #eee;">
          <p><strong>医生小贴士：</strong></p>
          <p>{{ visitDetail.doctor_advice }}</p>
        </div>

        <div v-if="visitDetail?.special_note" style="margin-top: 10px; padding: 5px; border: 1px solid #e6a23c; background: #fdf6ec;">
          <p><strong>特殊配药备注：</strong></p>
          <p>{{ visitDetail.special_note }}</p>
        </div>

        <hr/>
        <p v-if="receiptData?.original_amount">应收: ¥ {{ receiptData?.original_amount.toFixed(2) }}</p>
        <p v-if="receiptData?.original_amount">优惠类型: 职工优惠</p>
        <p>{{ receiptData?.original_amount ? '实收' : '金额' }}: ¥ {{ receiptData?.amount.toFixed(2) }}</p>
        <p>支付方式: {{ getPaymentMethodText(paymentMethod) }}</p>
        <hr/>
        <p style="text-align: center">盖章有效</p>
      </div>
      <template #footer>
        <el-button @click="showReceipt = false">关闭</el-button>
        <el-button type="primary" @click="printReceipt">打印</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="showReject" title="驳回处方" width="420px">
      <el-input v-model="rejectReason" type="textarea" :rows="4" placeholder="请输入驳回原因" />
      <template #footer>
        <el-button @click="showReject = false">取消</el-button>
        <el-button type="danger" :loading="rejecting" @click="submitReject">提交驳回</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="showModify" title="处方明细改价" width="480px">
      <el-form :model="modifyForm" label-width="90px">
        <el-form-item label="名称">
          <span>{{ modifyForm.drug_name }}</span>
        </el-form-item>
        <el-form-item label="数量">
          <span>{{ modifyForm.quantity }}</span>
        </el-form-item>
        <el-form-item label="当前单价">
          <span>¥ {{ Number(modifyForm.current_price || 0).toFixed(2) }}</span>
        </el-form-item>
        <el-form-item label="新单价">
          <el-input-number v-model="modifyForm.new_price" :min="0" :precision="2" :step="0.1" />
        </el-form-item>
        <el-form-item label="改价原因">
          <el-input v-model="modifyForm.modify_reason" type="textarea" :rows="3" placeholder="请输入改价原因" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showModify = false">取消</el-button>
        <el-button type="primary" :loading="modifying" @click="submitModify" :disabled="!canSubmitModify">
          保存
        </el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="showAddService" title="添加项目" width="500px">
      <el-form :model="addServiceForm" label-width="90px">
        <el-form-item label="选择项目">
          <el-select
            v-model="addServiceForm.drug_id"
            filterable
            remote
            reserve-keyword
            placeholder="输入项目/耗材名称搜索"
            :remote-method="searchServices"
            :loading="loadingServices"
            style="width: 100%"
          >
            <el-option
              v-for="item in serviceOptions"
              :key="item.id"
              :label="`${item.name} [${item.specification}] - ¥${item.price.toFixed(2)}`"
              :value="item.id"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="数量">
          <el-input-number v-model="addServiceForm.quantity" :min="1" :max="99" :step="1" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showAddService = false">取消</el-button>
        <el-button type="primary" :loading="addingService" @click="submitAddService" :disabled="!canSubmitAddService">
          添加
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, onMounted, computed, reactive } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import request from '@/api/request'
import { ElMessage, ElMessageBox } from 'element-plus'

const route = useRoute()
const router = useRouter()
const visitId = route.params.visitId

const visitDetail = ref(null)
const loading = ref(false)
const executing = ref(false)
const paymentMethod = ref('cash')
const employeeDiscount = ref(false)
const actualConsultationFee = ref(0)
const actualDrugAmount = ref(0)
const showReceipt = ref(false)
const receiptData = ref(null)
const verifying = ref(false)
const showReject = ref(false)
const rejectReason = ref('')
const rejecting = ref(false)
const showModify = ref(false)
const modifying = ref(false)
const modifyForm = reactive({
  item_id: null,
  drug_name: '',
  quantity: 0,
  current_price: 0,
  new_price: null,
  modify_reason: ''
})

const showAddService = ref(false)
const addingService = ref(false)
const loadingServices = ref(false)
const serviceOptions = ref([])
const addServiceForm = reactive({
  drug_id: null,
  quantity: 1
})

const getStatusText = (status) => {
  const map = {
    pending: '待护士审核',
    nurse_verified: '已审核待执行',
    rejected: '已驳回',
    completed: '已完成'
  }
  return map[status] || status
}

const getStatusTagType = (status) => {
  const map = {
    pending: 'warning',
    nurse_verified: 'success',
    rejected: 'danger',
    completed: 'info'
  }
  return map[status] || 'info'
}

const getStockNeeded = (item) => {
  if (!item || (item.type !== 1 && item.type !== 3)) return 0
  const qty = Number(item.quantity || 0)
  if (!item.is_scattered) return qty
  const rate = Number(item.conversion_rate || 1)
  if (rate <= 0) return qty
  return Math.ceil(qty / rate)
}

const isGarbledText = (val) => {
  if (typeof val !== 'string') return false
  return val.includes('?')
}

const safeText = (val) => {
  const s = String(val == null ? '' : val).trim()
  if (!s) return '-'
  if (isGarbledText(s)) return '-'
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

const stockSufficient = computed(() => {
  if (!visitDetail.value) return false
  return visitDetail.value.items.every(item => item.type === 2 || item.stock >= getStockNeeded(item))
})

const canModify = computed(() => {
  return Boolean(visitDetail.value && visitDetail.value.status === 'nurse_verified')
})

const serviceItems = computed(() => {
  if (!visitDetail.value) return []
  return visitDetail.value.items.filter(item => item.type === 2 || item.type === 3)
})

const drugItems = computed(() => {
  if (!visitDetail.value) return []
  return visitDetail.value.items.filter(item => item.type !== 2 && item.type !== 3)
})

// 所有处方物资和诊疗项目应收合计
const itemTotalFromItems = computed(() => {
  if (!visitDetail.value) return 0
  return visitDetail.value.items.reduce((sum, item) => sum + (Number(item.amount) || 0), 0)
})

// 药品成本合计（供护士参考）
const drugCostTotal = computed(() => {
  if (!visitDetail.value) return 0
  return drugItems.value.reduce((sum, item) => {
    const cost = Number(item.purchase_cost) || (Number(item.purchase_price) * Number(item.quantity)) || 0
    return sum + cost
  }, 0)
})

const hasServiceItems = computed(() => {
  return serviceItems.value.length > 0 || canModify.value
})

const canExecute = computed(() => {
  if (!visitDetail.value) return false
  return visitDetail.value.status === 'nurse_verified' && stockSufficient.value
})

const executeDisabledReason = computed(() => {
  if (!visitDetail.value) return ''
  const status = visitDetail.value.status
  if (status !== 'nurse_verified') {
    if (status === 'pending') return '请先在本页完成处方审核确认或驳回后再执行结算'
    if (status === 'rejected') return '处方已驳回，无法执行结算'
    if (status === 'completed') return '处方已完成结算'
    return `当前状态为 ${status}，无法执行结算`
  }
  if (!stockSufficient.value) return '存在药品库存不足，请先补充库存或驳回由医生调整处方'
  return ''
})

const fetchDetail = async ({ resetDiscountAmounts = false } = {}) => {
  loading.value = true
  try {
    const res = await request.get(`/nurse/visits/${visitId}`)
    visitDetail.value = res.data
    employeeDiscount.value = visitDetail.value?.patient?.patient_type === 'staff'
    if (employeeDiscount.value && resetDiscountAmounts) {
      actualConsultationFee.value = Number(visitDetail.value.consultation_fee) || 0
      actualDrugAmount.value = itemTotalFromItems.value
    } else if (!employeeDiscount.value) {
      actualConsultationFee.value = 0
      actualDrugAmount.value = 0
    }
  } catch (error) {
    ElMessage.error(error.msg || '获取处方详情失败')
  } finally {
    loading.value = false
  }
}

const handleVerify = async () => {
  verifying.value = true
  try {
    await request.post(`/nurse/visits/${visitId}/verify`)
    ElMessage.success('已确认处方')
    await fetchDetail({ resetDiscountAmounts: true })
  } catch (error) {
    ElMessage.error(error.msg || '确认失败')
  } finally {
    verifying.value = false
  }
}

const openRejectDialog = () => {
  rejectReason.value = ''
  showReject.value = true
}

const submitReject = async () => {
  const reason = String(rejectReason.value || '').trim()
  if (!reason) {
    ElMessage.warning('请输入驳回原因')
    return
  }
  rejecting.value = true
  try {
    await request.post(`/nurse/visits/${visitId}/reject`, { reason })
    ElMessage.success('已驳回处方')
    showReject.value = false
    await fetchDetail({ resetDiscountAmounts: true })
  } catch (error) {
    ElMessage.error(error.msg || '驳回失败')
  } finally {
    rejecting.value = false
  }
}

const openModifyDialog = (row) => {
  if (!canModify.value) return
  modifyForm.item_id = row.item_id
  modifyForm.drug_name = row.drug_name
  modifyForm.quantity = row.quantity
  modifyForm.current_price = row.unit_price
  modifyForm.new_price = row.unit_price
  modifyForm.modify_reason = ''
  showModify.value = true
}

const canSubmitModify = computed(() => {
  const price = Number(modifyForm.new_price)
  const reason = String(modifyForm.modify_reason || '').trim()
  if (!canModify.value) return false
  if (!modifyForm.item_id) return false
  if (!Number.isFinite(price) || price <= 0) return false
  if (!reason) return false
  return true
})

const submitModify = async () => {
  if (!canSubmitModify.value) return
  modifying.value = true
  try {
    await request.put(`/nurse/visits/${visitId}/items/${modifyForm.item_id}/modify`, {
      new_price: Number(modifyForm.new_price),
      modify_reason: String(modifyForm.modify_reason || '').trim()
    })
    ElMessage.success('改价已保存')
    showModify.value = false
    await fetchDetail({ resetDiscountAmounts: true })
  } catch (error) {
    ElMessage.error(error.msg || '改价失败')
  } finally {
    modifying.value = false
  }
}

const handleExecute = async () => {
  executing.value = true
  try {
    const payload = {
      payment_method: paymentMethod.value,
      employee_discount: employeeDiscount.value
    }
    if (employeeDiscount.value) {
      payload.actual_consultation_fee = actualConsultationFee.value
      payload.actual_drug_amount = actualDrugAmount.value
    }
    const res = await request.post(`/nurse/visits/${visitId}/execute`, payload)
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
    const printArea = document.getElementById('receipt-print-area')
    if (!printArea) return
    const printWindow = window.open('', '_blank', 'width=400,height=600')
    if (!printWindow) {
      ElMessage.warning('请允许弹出窗口以完成打印')
      return
    }
    printWindow.document.write(`<!DOCTYPE html><html><head><meta charset="utf-8"><title>收费凭证</title><style>body{font-family:'Courier New',Courier,monospace;padding:10px;line-height:1.6;margin:0}p{margin:4px 0}.item-line{margin:2px 0 2px 10px;font-size:12px;line-height:1.4}.advice-print-info{font-size:13px}h3{text-align:center}hr{border:none;border-top:1px dashed #999;margin:8px 0}</style></head><body>${printArea.innerHTML}</body></html>`)
    printWindow.document.close()
    printWindow.onafterprint = () => {
      printWindow.close()
    }
    printWindow.focus()
    setTimeout(() => {
      printWindow.print()
    }, 500)
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

const openAddServiceDialog = () => {
  addServiceForm.drug_id = null
  addServiceForm.quantity = 1
  serviceOptions.value = []
  showAddService.value = true
}

const searchServices = async (keyword) => {
  if (!keyword.trim()) return
  loadingServices.value = true
  try {
    const res = await request.get(`/nurse/services/search?keyword=${encodeURIComponent(keyword)}`)
    serviceOptions.value = res.data || []
  } catch (error) {
    ElMessage.error(error.msg || '搜索失败')
  } finally {
    loadingServices.value = false
  }
}

const canSubmitAddService = computed(() => {
  return addServiceForm.drug_id && addServiceForm.quantity > 0
})

const submitAddService = async () => {
  if (!canSubmitAddService.value) return
  addingService.value = true
  try {
    await request.post(`/nurse/visits/${visitId}/service-items`, {
      drug_id: addServiceForm.drug_id,
      quantity: addServiceForm.quantity
    })
    ElMessage.success('添加成功')
    showAddService.value = false
    await fetchDetail({ resetDiscountAmounts: true })
  } catch (error) {
    ElMessage.error(error.msg || '添加失败')
  } finally {
    addingService.value = false
  }
}

const handleServiceQuantityChange = async (item) => {
  if (!item.item_id) return
  try {
    await request.put(`/nurse/visits/${visitId}/service-items/${item.item_id}`, {
      quantity: item.quantity
    })
    await fetchDetail({ resetDiscountAmounts: true })
  } catch (error) {
    ElMessage.error(error.msg || '修改失败')
    await fetchDetail({ resetDiscountAmounts: true })
  }
}

const handleDeleteService = async (item) => {
  if (!item.item_id) return
  try {
    await ElMessageBox.confirm(
      `确定要删除追加项目“${item.drug_name || '未命名项目'}”吗？`,
      '删除追加项目',
      {
        confirmButtonText: '确定删除',
        cancelButtonText: '取消',
        type: 'warning'
      }
    )
  } catch (action) {
    if (action === 'cancel' || action === 'close') return
    throw action
  }

  try {
    await request.delete(`/nurse/visits/${visitId}/service-items/${item.item_id}`)
    ElMessage.success('删除成功')
    await fetchDetail({ resetDiscountAmounts: true })
  } catch (error) {
    ElMessage.error(error.msg || '删除失败')
  }
}

onMounted(() => {
  fetchDetail({ resetDiscountAmounts: true })
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
.verify-actions {
  display: flex;
  justify-content: flex-end;
  gap: 12px;
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
