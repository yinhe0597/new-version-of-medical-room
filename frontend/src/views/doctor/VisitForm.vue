<template>
  <div class="visit-form-container">
    <el-page-header @back="goBack" content="电子病历与处方开立">
      <template #extra>
        <div class="patient-info-tag">
          <el-tag type="success" effect="dark">{{ patientName }} ({{ studentId }})</el-tag>
        </div>
      </template>
    </el-page-header>

    <div class="main-content">
      <el-row :gutter="20">
        <!-- 左侧：电子病历 -->
        <el-col :span="10">
          <el-card class="box-card" header="电子病历">
            <el-form :model="visitForm" label-position="top">
              <el-form-item label="主诉">
                <el-input v-model="visitForm.chief_complaint" type="textarea" :rows="2" @input="onTemplateInput('chief_complaint')"></el-input>
              </el-form-item>
              <el-form-item label="现病史">
                <el-input v-model="visitForm.present_illness" type="textarea" :rows="2"></el-input>
              </el-form-item>
              <el-form-item label="既往史（过敏史）">
                <el-input v-model="visitForm.past_history" type="textarea" :rows="2"></el-input>
              </el-form-item>
              <el-form-item label="体格检查">
                <el-input v-model="visitForm.physical_exam" type="textarea" :rows="2" @input="onTemplateInput('physical_exam')"></el-input>
              </el-form-item>
              <el-form-item label="诊断" class="asterisk-left el-form-item--label-top">
                <div style="width: 100%; display: flex; flex-direction: column; gap: 10px;">
                  <el-autocomplete
                    v-model="diagnosisSearch"
                    :fetch-suggestions="querySearchDiagnosisAsync"
                    placeholder="快速检索并添加诊断 (输入拼音或名称)"
                    @select="handleDiagnosisSelect"
                    style="width: 100%"
                    clearable
                  >
                    <template #default="{ item }">
                      <div class="diagnosis-item">
                        <span>{{ item.name }}</span>
                        <span class="diagnosis-code">{{ item.code }}</span>
                      </div>
                    </template>
                  </el-autocomplete>
                  <el-input 
                    v-model="visitForm.diagnosis" 
                    type="textarea" 
                    :rows="3" 
                    placeholder="可在此直接编辑或手动输入多条诊断"
                  ></el-input>
                </div>
              </el-form-item>
              <el-form-item label="医生留言/小贴士 (如：适量运动，戒烟戒酒)">
                <el-input v-model="visitForm.doctor_advice" type="textarea" :rows="2" placeholder="给患者的自定义建议..." @input="onTemplateInput('doctor_advice')"></el-input>
              </el-form-item>
            </el-form>
          </el-card>
        </el-col>

        <!-- 右侧：开处方 -->
        <el-col :span="14">
          <el-card class="box-card" header="处方开立">
            <!-- 药品搜索 -->
            <div class="drug-search">
              <el-select
                v-model="selectedDrugId"
                filterable
                remote
                reserve-keyword
                placeholder="输入药品或项目名称搜索"
                :remote-method="searchDrugs"
                :loading="loadingDrugs"
                style="width: 100%"
                @change="handleDrugSelect"
              >
                <el-option
                  v-for="item in drugOptions"
                  :key="item.option_id"
                  :label="`${item.name} [${item.specification}] (${item.option_label}) - ¥${item.display_price.toFixed(2)}`"
                  :value="item.option_id"
                >
                  <span style="float: left">{{ item.name }}</span>
                  <span style="float: right; color: #8492a6; font-size: 13px">
                    {{ item.specification }} | {{ item.type === 1 ? '库存: ' + item.stock + ' | ' : '' }}{{ item.option_label }}: ¥{{ item.display_price.toFixed(2) }}
                  </span>
                </el-option>
              </el-select>
            </div>

            <!-- 已选药品列表 -->
            <el-table :data="prescriptionItems" style="width: 100%; margin-top: 20px" border size="small">
              <el-table-column prop="name" label="药品名称" min-width="120" />
              <el-table-column prop="specification" label="规格" width="100" />
              <el-table-column label="零散用药" width="80">
                <template #default="scope">
                  <el-checkbox v-model="scope.row.is_scattered" v-if="scope.row.type === 1" />
                  <span v-else style="color: #909399; font-size: 12px;">-</span>
                </template>
              </el-table-column>
              <el-table-column label="用法/用量" min-width="180">
                <template #default="scope">
                  <div class="usage-inputs" v-if="scope.row.type === 1">
                    <el-select
                      v-model="scope.row.usage"
                      placeholder="用法"
                      size="small"
                      style="width: 80px"
                      allow-create
                      filterable
                      default-first-option
                    >
                      <el-option v-for="item in usageOptions" :key="item" :label="item" :value="item" />
                    </el-select>

                    <el-select
                      v-model="scope.row.dosage"
                      placeholder="用量"
                      size="small"
                      style="width: 80px"
                      allow-create
                      filterable
                      default-first-option
                    >
                      <el-option v-for="item in dosageOptions" :key="item" :label="item" :value="item" />
                    </el-select>

                    <el-select
                      v-model="scope.row.frequency"
                      placeholder="频次"
                      size="small"
                      style="width: 80px"
                      allow-create
                      filterable
                      default-first-option
                    >
                      <el-option v-for="item in frequencyOptions" :key="item" :label="item" :value="item" />
                    </el-select>

                    <el-select 
                      v-model="scope.row.timing" 
                      placeholder="时间" 
                      size="small" 
                      style="width: 80px"
                      allow-create
                      filterable
                      default-first-option
                    >
                      <el-option label="餐前" value="餐前" />
                      <el-option label="餐后" value="餐后" />
                      <el-option label="餐中" value="餐中" />
                      <el-option label="空腹" value="空腹" />
                      <el-option label="睡前" value="睡前" />
                    </el-select>
                    </div>
                    <div v-else>
                      <span style="color: #909399; font-size: 12px;">诊疗项目 (无需填写用法)</span>
                    </div>
                  </template>
                </el-table-column>
              <el-table-column label="天数" width="80">
                <template #default="scope">
                  <el-select 
                    v-model="scope.row.days" 
                    placeholder="天数" 
                    size="small" 
                    style="width: 100%"
                    v-if="scope.row.type === 1"
                  >
                    <el-option v-for="day in 7" :key="day" :label="day + '天'" :value="day" />
                  </el-select>
                  <span v-else style="color: #909399; font-size: 12px;">-</span>
                </template>
              </el-table-column>
              <el-table-column label="数量" width="120">
                <template #default="scope">
                  <el-input-number 
                    v-model="scope.row.quantity" 
                    :min="1" 
                    :max="scope.row.type === 1 ? (scope.row.maxStock > 0 ? scope.row.maxStock : 999) : 999" 
                    size="small" 
                    style="width: 100px"
                  />
                </template>
              </el-table-column>
              <el-table-column label="单价" width="80">
                <template #default="scope">
                  {{ scope.row.price.toFixed(2) }}
                </template>
              </el-table-column>
              <el-table-column label="金额" width="80">
                <template #default="scope">
                  {{ (scope.row.price * scope.row.quantity).toFixed(2) }}
                </template>
              </el-table-column>
              <el-table-column label="操作" width="60">
                <template #default="scope">
                  <el-button type="danger" link @click="removeDrug(scope.$index)">删除</el-button>
                </template>
              </el-table-column>
            </el-table>

            <!-- 费用结算 -->
            <div class="footer-action">
              <el-form inline>
                <el-form-item label="诊察费">
                  <el-input-number v-model="visitForm.consultation_fee" :min="0" :precision="2" :step="1" />
                </el-form-item>
                <el-form-item label="总金额">
                  <span class="total-amount">¥ {{ totalAmount.toFixed(2) }}</span>
                </el-form-item>
              </el-form>
              <div class="buttons">
                <el-button @click="resetForm">重置</el-button>
                <el-button type="primary" @click="openSubmitConfirm" :loading="submitting">提交处方</el-button>
              </div>
            </div>
          </el-card>
        </el-col>
      </el-row>
    </div>

    <el-dialog v-model="confirmDialogVisible" title="确认提交处方" width="900px">
      <el-descriptions border :column="2" title="就诊信息">
        <el-descriptions-item label="患者">{{ patientName }} ({{ studentId }})</el-descriptions-item>
        <el-descriptions-item label="诊断">{{ visitForm.diagnosis || '-' }}</el-descriptions-item>
        <el-descriptions-item label="主诉" :span="2">{{ visitForm.chief_complaint || '无' }}</el-descriptions-item>
        <el-descriptions-item label="现病史" :span="2">{{ visitForm.present_illness || '无' }}</el-descriptions-item>
        <el-descriptions-item label="既往史（过敏史）" :span="2">{{ visitForm.past_history || '无' }}</el-descriptions-item>
        <el-descriptions-item label="体格检查" :span="2">{{ visitForm.physical_exam || '无' }}</el-descriptions-item>
        <el-descriptions-item label="医生留言" :span="2">{{ visitForm.doctor_advice || '无' }}</el-descriptions-item>
      </el-descriptions>

      <div style="margin-top: 20px;">
        <div style="font-size: 16px; font-weight: bold; margin-bottom: 10px;">处方明细</div>
        <el-table :data="prescriptionItems" border stripe size="small">
          <el-table-column prop="name" label="药品名称" min-width="140" />
          <el-table-column prop="specification" label="规格" width="120" />
          <el-table-column label="用法" min-width="220">
            <template #default="scope">
              <span v-if="scope.row.type === 1">
                {{ scope.row.usage }} / {{ scope.row.dosage }} / {{ scope.row.frequency }} / {{ scope.row.timing }}
              </span>
              <span v-else style="color: #909399">-</span>
            </template>
          </el-table-column>
          <el-table-column prop="quantity" label="数量" width="80" />
          <el-table-column label="单价" width="90">
            <template #default="scope">¥ {{ scope.row.price.toFixed(2) }}</template>
          </el-table-column>
          <el-table-column label="金额" width="100">
            <template #default="scope">¥ {{ (scope.row.price * scope.row.quantity).toFixed(2) }}</template>
          </el-table-column>
        </el-table>
      </div>

      <div class="confirm-totals">
        <div class="confirm-total-line">
          <span>处方小计</span>
          <span>¥ {{ drugTotalAmount.toFixed(2) }}</span>
        </div>
        <div class="confirm-total-line">
          <span>诊察费</span>
          <span>¥ {{ visitForm.consultation_fee.toFixed(2) }}</span>
        </div>
        <div class="confirm-total-line confirm-total-final">
          <span>应收总额</span>
          <span>¥ {{ totalAmount.toFixed(2) }}</span>
        </div>
      </div>

      <template #footer>
        <el-button @click="confirmDialogVisible = false" :disabled="submitting">取消</el-button>
        <el-button type="primary" @click="confirmSubmit" :loading="submitting">确认提交</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="templateDialogVisible" :title="templateDialogTitle" width="800px">
      <div style="display: flex; gap: 10px; align-items: center; margin-bottom: 12px;">
        <el-input v-model="templateKeyword" placeholder="搜索模板标题/内容" clearable @keyup.enter="loadTemplates" />
        <el-button @click="loadTemplates" :loading="templateLoading">查询</el-button>
      </div>
      <el-table :data="templateList" border stripe size="small" v-loading="templateLoading" @row-click="applyTemplate">
        <el-table-column prop="title" label="标题" width="220" />
        <el-table-column label="内容">
          <template #default="scope">
            <div style="white-space: pre-wrap; word-break: break-word; max-height: 160px; overflow: hidden;">
              {{ scope.row.content }}
            </div>
          </template>
        </el-table-column>
        <el-table-column prop="updated_at" label="更新时间" width="170" />
      </el-table>
      <template #footer>
        <el-button @click="templateDialogVisible = false">关闭</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import request from '@/api/request'
import { ElMessage } from 'element-plus'

const route = useRoute()
const router = useRouter()

const patientId = route.query.patient_id
const patientName = route.query.patient_name
const studentId = route.query.student_id
const sourceVisitId = route.query.source_visit_id

const diagnosisSearch = ref('')

// 电子病历表单
const visitForm = ref({
  chief_complaint: '',
  present_illness: '',
  past_history: '无',
  physical_exam: '',
  diagnosis: '',
  doctor_advice: '',
  consultation_fee: 8.00
})

// 药品相关
const loadingDrugs = ref(false)
const drugOptions = ref([])
const selectedDrugId = ref(null)
const prescriptionItems = ref([])

// 预设选项数据
const usageOptions = ref(['口服', '外用', '静脉注射', '肌肉注射', '皮下注射', '雾化吸入', '含服', '外敷', '滴眼', '滴耳', '滴鼻'])
const buildDosageOptions = () => {
  const out = []
  const push = (v) => {
    if (!v) return
    if (!out.includes(v)) out.push(v)
  }

  const halfUnits = ['片', '粒', '袋', '包']
  halfUnits.forEach(u => push(`半${u}`))

  const countUnits = ['片', '粒', '袋', '包', '支', '瓶', '贴', '喷', '丸', '次', '滴']
  countUnits.forEach(u => {
    for (let i = 1; i <= 6; i++) push(`${i}${u}`)
  })

  ;['1ml', '2ml', '5ml', '10ml', '20ml', '50ml', '100ml'].forEach(push)
  ;['0.5g', '1g', '2g', '5g', '10g', '15g', '20g'].forEach(push)
  push('适量')
  return out
}

const dosageOptions = ref(buildDosageOptions())
const frequencyOptions = ref(['每日1次', '每日2次', '每日3次', '每日4次', '每4小时1次', '每6小时1次', '每8小时1次', '每12小时1次', '必要时', '睡前'])

// 提交状态
const submitting = ref(false)
const confirmDialogVisible = ref(false)

const templateDialogVisible = ref(false)
const templateLoading = ref(false)
const templateList = ref([])
const templateKeyword = ref('')
const templateFieldKey = ref('')

const templateDialogTitle = computed(() => {
  if (templateFieldKey.value === 'chief_complaint') return '选择主诉模板'
  if (templateFieldKey.value === 'physical_exam') return '选择体格检查模板'
  if (templateFieldKey.value === 'doctor_advice') return '选择医生贴士模板'
  return '选择模板'
})

const templateCategoryByField = {
  chief_complaint: 'chief_complaint',
  physical_exam: 'physical_exam',
  doctor_advice: 'doctor_advice'
}

const onTemplateInput = (fieldKey) => {
  if (templateDialogVisible.value) return
  const value = String(visitForm.value[fieldKey] || '')
  if (!value.endsWith('##')) return
  templateFieldKey.value = fieldKey
  templateKeyword.value = ''
  templateDialogVisible.value = true
  loadTemplates()
}

const loadTemplates = async () => {
  const category = templateCategoryByField[templateFieldKey.value]
  if (!category) return
  templateLoading.value = true
  try {
    const res = await request.get('/doctor/templates', {
      params: {
        category,
        q: templateKeyword.value.trim()
      }
    })
    templateList.value = res.data || []
  } catch (error) {
    ElMessage.error(error.msg || '加载模板失败')
  } finally {
    templateLoading.value = false
  }
}

const applyTemplate = (row) => {
  const fieldKey = templateFieldKey.value
  if (!fieldKey) return
  const content = String((row && row.content) || '')
  const value = String(visitForm.value[fieldKey] || '')
  const base = value.endsWith('##') ? value.slice(0, -2) : value
  const prefix = base && !base.endsWith('\n') ? `${base}\n` : base
  visitForm.value[fieldKey] = `${prefix}${content}`
  templateDialogVisible.value = false
}

const totalAmount = computed(() => {
  const drugTotal = prescriptionItems.value.reduce((sum, item) => {
    return sum + (item.price * item.quantity)
  }, 0)
  return drugTotal + visitForm.value.consultation_fee
})

const drugTotalAmount = computed(() => {
  return prescriptionItems.value.reduce((sum, item) => sum + (item.price * item.quantity), 0)
})

const loadRejectedVisitAsDraft = async () => {
  if (!sourceVisitId) return
  try {
    const res = await request.get(`/doctor/visits/${sourceVisitId}`)
    const detail = res.data || {}

    visitForm.value.chief_complaint = detail.chief_complaint || ''
    visitForm.value.present_illness = detail.present_illness || ''
    visitForm.value.past_history = detail.past_history || '无'
    visitForm.value.physical_exam = detail.physical_exam || ''
    visitForm.value.diagnosis = detail.diagnosis || ''
    visitForm.value.doctor_advice = detail.doctor_advice || ''
    visitForm.value.consultation_fee = Number(detail.consultation_fee || 8)

    const draftItems = Array.isArray(detail.items) ? detail.items : []
    prescriptionItems.value = draftItems.map((item, idx) => {
      const quantity = Number(item.quantity || 1)
      const totalAmount = Number(item.amount || 0)
      const unitPrice = Number(item.price_at_visit || (quantity > 0 ? totalAmount / quantity : 0))
      return {
        id: item.drug_id,
        option_id: `draft-${idx}-${item.drug_id}-${item.is_scattered ? 1 : 0}`,
        name: item.drug_name,
        type: Number(item.drug_type || 1),
        specification: item.specification,
        price: Number.isFinite(unitPrice) ? unitPrice : 0,
        maxStock: 999,
        is_scattered: !!item.is_scattered,
        quantity: quantity > 0 ? quantity : 1,
        usage: item.usage || '',
        dosage: item.dosage || '',
        frequency: item.frequency || '',
        timing: item.timing || '',
        days: Number(item.days || 1) > 0 ? Number(item.days || 1) : 1
      }
    })

    ElMessage.success('已载入被驳回处方，可重新修改后提交')
  } catch (error) {
    ElMessage.error(error.msg || '载入历史处方失败')
  }
}

onMounted(async () => {
  if (!patientId) {
    ElMessage.error('未指定患者，请先搜索')
    await router.push('/doctor/patient')
    return
  }
  // Load default drugs
  await searchDrugs('')
  await loadRejectedVisitAsDraft()
})

const goBack = () => {
  router.push('/doctor/patient')
}

const querySearchDiagnosisAsync = async (queryString, cb) => {
  if (!queryString) {
    cb([])
    return
  }
  try {
    const res = await request.get('/doctor/diagnoses/search', {
      params: { keyword: queryString }
    })
    // Element Plus autocomplete expects 'value' field for the input text
    const results = res.data.map(item => ({
      ...item,
      value: item.name
    }))
    cb(results)
  } catch (error) {
    console.error(error)
    cb([])
  }
}

const handleDiagnosisSelect = (item) => {
  const selectedText = `${item.name} (${item.code})`
  if (!visitForm.value.diagnosis) {
    visitForm.value.diagnosis = selectedText
  } else {
    visitForm.value.diagnosis += `\n${selectedText}`
  }
  // Clear the search input after selecting
  diagnosisSearch.value = ''
}

const searchDrugs = async (query) => {
  loadingDrugs.value = true
  try {
    const res = await request.get('/doctor/drugs/search', {
      params: { keyword: query }
    })
    const options = []
    ;(res.data || []).forEach(d => {
      if (d.variant_type === 'retail') {
        options.push({
          ...d,
          option_id: `${d.id}:variant`,
          option_label: '零散',
          display_price: d.price,
          is_scattered: false,
          maxStock: d.stock
        })
        return
      }
      if (d.variant_type === 'pack') {
        options.push({
          ...d,
          option_id: `${d.id}:variant`,
          option_label: '整装',
          display_price: d.price,
          is_scattered: false,
          maxStock: d.stock
        })
        return
      }
      if (d.variant_type === 'service') {
        options.push({
          ...d,
          option_id: `${d.id}:variant`,
          option_label: '项目',
          display_price: d.price,
          is_scattered: false,
          maxStock: 999
        })
        return
      }
      options.push({
        ...d,
        option_id: `${d.id}:whole`,
        option_label: '整装',
        display_price: d.price,
        is_scattered: false,
        maxStock: d.stock
      })
      if (d.has_scattered && d.scattered_price != null) {
        const conv = d.conversion_rate || 1
        options.push({
          ...d,
          option_id: `${d.id}:scattered`,
          option_label: '零散',
          display_price: d.scattered_price,
          is_scattered: true,
          maxStock: (d.stock || 0) * conv
        })
      }
    })
    drugOptions.value = options
  } catch (error) {
    console.error(error)
  } finally {
    loadingDrugs.value = false
  }
}

const handleDrugSelect = (val) => {
  const drug = drugOptions.value.find(item => item.option_id === val)
  if (drug) {
    // Check if already added
    if (prescriptionItems.value.find(item => item.option_id === drug.option_id)) {
      ElMessage.warning('该项目已添加')
    } else {
      prescriptionItems.value.push({
        id: drug.id,
        option_id: drug.option_id,
        name: drug.name,
        type: drug.type,
        specification: drug.specification,
        price: drug.display_price,
        maxStock: drug.maxStock,
        is_scattered: drug.is_scattered,
        quantity: 1,
        usage: drug.type === 1 ? '口服' : '',
        dosage: '',
        frequency: drug.type === 1 ? '每日3次' : '',
        timing: drug.type === 1 ? '餐后' : '',
        days: 1
      })
    }
  }
  selectedDrugId.value = null
}

const removeDrug = (index) => {
  prescriptionItems.value.splice(index, 1)
}

// 监听处方项目变化，自动计算零散药物数量
watch(
  prescriptionItems,
  (newItems) => {
    newItems.forEach(item => {
      if (item.type === 1 && item.is_scattered) {
        // 解析用量
        let dosageAmount = 0
        if (item.dosage.includes('半')) {
          dosageAmount = 0.5
        } else {
          const dosageMatch = item.dosage.match(/(\d+)([片粒袋包支瓶贴喷丸次滴])/)
          if (!dosageMatch) return
          dosageAmount = parseFloat(dosageMatch[1])
          if (!dosageAmount) return
        }
        
        // 解析频次
        let frequencyAmount = 1
        const frequencyMatch = item.frequency.match(/每日(\d+)次/)
        if (frequencyMatch) {
          frequencyAmount = parseFloat(frequencyMatch[1])
        } else if (item.frequency.includes('每4小时')) {
          frequencyAmount = 6
        } else if (item.frequency.includes('每6小时')) {
          frequencyAmount = 4
        } else if (item.frequency.includes('每8小时')) {
          frequencyAmount = 3
        } else if (item.frequency.includes('每12小时')) {
          frequencyAmount = 2
        }
        
        // 计算总数量
        const days = item.days || 1
        item.quantity = Math.round(dosageAmount * frequencyAmount * days)
      }
    })
  },
  { deep: true }
)

const resetForm = () => {
  visitForm.value = {
    chief_complaint: '',
    present_illness: '',
    past_history: '无',
    physical_exam: '',
    diagnosis: '',
    doctor_advice: '',
    consultation_fee: 8.00
  }
  prescriptionItems.value = []
}

const validatePrescription = () => {
  if (!visitForm.value.diagnosis || !String(visitForm.value.diagnosis).trim()) {
    ElMessage.warning('请填写诊断信息')
    return false
  }
  if (!Array.isArray(prescriptionItems.value) || prescriptionItems.value.length === 0) {
    ElMessage.warning('请至少添加一条处方明细')
    return false
  }
  for (let i = 0; i < prescriptionItems.value.length; i++) {
    const item = prescriptionItems.value[i]
    const qty = Number(item.quantity)
    if (!Number.isFinite(qty) || qty <= 0) {
      ElMessage.warning(`第${i + 1}行数量不合法`)
      return false
    }
    if (item.type === 1) {
      const required = [
        { key: 'usage', label: '用法' },
        { key: 'dosage', label: '用量' },
        { key: 'frequency', label: '频次' },
        { key: 'timing', label: '时间' }
      ]
      for (const r of required) {
        if (!String(item[r.key] || '').trim()) {
          ElMessage.warning(`第${i + 1}行请填写${r.label}`)
          return false
        }
      }
      const days = Number(item.days)
      if (!Number.isFinite(days) || days <= 0) {
        ElMessage.warning(`第${i + 1}行天数不合法`)
        return false
      }
    }
  }
  return true
}

const openSubmitConfirm = () => {
  if (!validatePrescription()) return
  confirmDialogVisible.value = true
}

const confirmSubmit = async () => {
  if (!confirmDialogVisible.value) return
  if (!validatePrescription()) return
  submitting.value = true
  try {
    const payload = {
      patient_id: patientId,
      ...visitForm.value,
      items: prescriptionItems.value.map(item => ({
        drug_id: item.id,
        quantity: item.quantity,
        usage: item.usage,
        dosage: item.dosage,
        frequency: item.frequency,
        timing: item.timing,
        days: item.days,
        is_scattered: item.is_scattered || false
      }))
    }
    
    await request.post('/doctor/visits', payload)
    confirmDialogVisible.value = false
    ElMessage.success('处方提交成功')
    router.push('/doctor/history')
  } catch (error) {
    ElMessage.error(error.msg || '提交失败')
  } finally {
    submitting.value = false
  }
}
</script>

<style scoped>
.visit-form-container {
  padding: 20px;
}
.main-content {
  margin-top: 20px;
}
.drug-search {
  margin-bottom: 10px;
}
.usage-inputs {
  display: flex;
  gap: 5px;
}
.footer-action {
  margin-top: 20px;
  border-top: 1px solid #ebeef5;
  padding-top: 20px;
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.total-amount {
  font-size: 20px;
  color: #f56c6c;
  font-weight: bold;
}
.diagnosis-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.diagnosis-code {
  color: #999;
  font-size: 12px;
  margin-left: 10px;
}
.confirm-totals {
  margin-top: 20px;
  display: flex;
  flex-direction: column;
  gap: 8px;
  align-items: flex-end;
}
.confirm-total-line {
  width: 260px;
  display: flex;
  justify-content: space-between;
  font-size: 14px;
}
.confirm-total-final {
  font-size: 18px;
  font-weight: bold;
  color: #f56c6c;
}
</style>
