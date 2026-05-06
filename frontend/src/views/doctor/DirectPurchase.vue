<template>
  <div class="direct-purchase-container">
    <el-page-header v-if="patient" @back="reselectPatient" content="单独购药 - 开立处方">
      <template #extra>
        <div class="patient-info-tag">
          <el-tag type="success" effect="dark">{{ patient.name }} ({{ patient.student_id || '无学号' }})</el-tag>
        </div>
      </template>
    </el-page-header>
    <el-page-header v-else content="单独购药 - 患者搜索" :icon="null"></el-page-header>

    <!-- Step 1: Patient Search -->
    <div v-if="!patient" class="search-section" style="margin-top: 20px;">
      <el-card class="search-card">
        <div class="search-box">
          <el-autocomplete
            v-model="searchKeyword"
            placeholder="请输入姓名（前几位即可）"
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
                <span class="name">{{ item.name }}</span>
                <span class="gender">{{ item.gender }}</span>
              </div>
            </template>
            <template #append>
              <el-button @click="handleSearchFromButton" :loading="loading">查询</el-button>
            </template>
          </el-autocomplete>
        </div>
      </el-card>

      <!-- 新建患者表单 -->
      <el-card v-if="showCreateForm" class="create-card" style="margin-top: 20px;">
        <template #header>
          <span>未找到患者，请新建档案</span>
        </template>
        <el-form :model="createForm" :rules="rules" ref="formRef" label-width="100px">
          <el-form-item label="姓名" prop="name">
            <el-input v-model="createForm.name"></el-input>
          </el-form-item>
          <el-form-item label="性别" prop="gender">
            <el-radio-group v-model="createForm.gender">
              <el-radio label="男">男</el-radio>
              <el-radio label="女">女</el-radio>
            </el-radio-group>
          </el-form-item>
          <el-form-item label="联系电话" prop="phone">
            <el-input v-model="createForm.phone"></el-input>
          </el-form-item>
          <el-form-item>
            <el-button type="primary" @click="handleCreate" :loading="creating">保存并购药</el-button>
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
          该患者目前未登记手机号码，请补充后再购药：
        </div>
        <el-input
          v-model="tempPhone"
          placeholder="请输入手机号码"
          clearable
        ></el-input>
        <template #footer>
          <span class="dialog-footer">
            <el-button @click="skipPhoneInput">暂不补充，直接购药</el-button>
            <el-button type="primary" @click="submitPhone" :loading="updatingPhone">
              保存并购药
            </el-button>
          </span>
        </template>
      </el-dialog>
    </div>

    <!-- Step 2: Prescription -->
    <div v-else class="prescription-section" style="margin-top: 20px;">
      <el-card class="box-card" header="处方开立 (免病历)">
        <div style="margin-bottom: 20px;">
          <el-alert title="单独购药说明" type="info" description="患者已登记个人信息，无需书写病历即可在医生处进行购药。请人工审核药品禁忌后开具处方。" show-icon />
        </div>
        
        <!-- 药品搜索 -->
        <div class="drug-search">
          <el-select
            v-model="selectedDrugId"
            filterable
            remote
            reserve-keyword
            placeholder="输入药品名称搜索"
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
          <el-table-column label="用法/用量" min-width="180">
            <template #default="scope">
              <div class="usage-inputs" v-if="scope.row.type === 1">
                <el-select v-model="scope.row.usage" placeholder="用法" size="small" style="width: 80px" allow-create filterable default-first-option>
                  <el-option v-for="item in usageOptions" :key="item" :label="item" :value="item" />
                </el-select>
                <el-select v-model="scope.row.dosage" placeholder="用量" size="small" style="width: 80px" allow-create filterable default-first-option>
                  <el-option v-for="item in dosageOptions" :key="item" :label="item" :value="item" />
                </el-select>
                <el-select v-model="scope.row.frequency" placeholder="频次" size="small" style="width: 80px" allow-create filterable default-first-option>
                  <el-option v-for="item in frequencyOptions" :key="item" :label="item" :value="item" />
                </el-select>
                <el-select v-model="scope.row.timing" placeholder="时间" size="small" style="width: 80px" allow-create filterable default-first-option>
                  <el-option label="餐前" value="餐前" />
                  <el-option label="餐后" value="餐后" />
                  <el-option label="餐中" value="餐中" />
                  <el-option label="空腹" value="空腹" />
                  <el-option label="睡前" value="睡前" />
                </el-select>
              </div>
              <div v-else>
                <span style="color: #909399; font-size: 12px;">无需填写用法</span>
              </div>
            </template>
          </el-table-column>
          <el-table-column label="数量" width="120">
            <template #default="scope">
              <el-input-number v-model="scope.row.quantity" :min="1" :max="scope.row.type === 1 ? (scope.row.maxStock > 0 ? scope.row.maxStock : 999) : 999" size="small" style="width: 100px" />
            </template>
          </el-table-column>
          <el-table-column label="单价" width="80">
            <template #default="scope">{{ scope.row.price.toFixed(2) }}</template>
          </el-table-column>
          <el-table-column label="金额" width="80">
            <template #default="scope">{{ (Math.round(scope.row.price * scope.row.quantity * 100) / 100).toFixed(2) }}</template>
          </el-table-column>
          <el-table-column label="操作" width="60">
            <template #default="scope">
              <el-button type="danger" link @click="removeDrug(scope.$index)">删除</el-button>
            </template>
          </el-table-column>
        </el-table>

        <!-- 费用结算 -->
        <div class="footer-action">
          <div style="display: flex; align-items: center; gap: 20px; flex-wrap: wrap;">
            <el-checkbox v-model="checkContraindications">已人工审核药品禁忌，确认无误</el-checkbox>
            <el-form inline style="margin-bottom: 0;">
              <el-form-item label="诊察费" style="margin-bottom: 0;">
                <el-input-number v-model="consultationFee" :min="0" :precision="2" :step="1" />
              </el-form-item>
              <el-form-item label="总金额" style="margin-bottom: 0;">
                <span class="total-amount">¥ {{ totalAmount.toFixed(2) }}</span>
              </el-form-item>
            </el-form>
          </div>
          <div class="buttons" style="margin-top: 15px;">
            <el-button @click="resetPrescription">重置</el-button>
            <el-button type="primary" @click="submitPrescription" :loading="submitting">提交处方</el-button>
          </div>
        </div>
      </el-card>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { Search } from '@element-plus/icons-vue'
import request from '@/api/request'
import { ElMessage } from 'element-plus'

const router = useRouter()

// ===== Step 1: Patient Search Logic =====
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

const createForm = ref({
  name: '',
  gender: '男',
  phone: ''
})

const rules = {
  name: [{ required: true, message: '请输入姓名', trigger: 'blur' }],
  gender: [{ required: true, message: '请选择性别', trigger: 'change' }]
}

let searchTimer = null

const handleSearch = async (query, callback) => {
  if (!query || query.length < 1) {
    callback([])
    return
  }

  if (searchTimer) clearTimeout(searchTimer)

  searchTimer = setTimeout(async () => {
    loading.value = true
    try {
      const res = await request.get('/doctor/patient/search', {
        params: { keyword: query }
      })

      if (res.data && res.data.length > 0) {
        searchResults.value = res.data
        callback(res.data.map(p => ({ ...p, value: p.name })))
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
        onPatientSelected()
      } else {
        searchResults.value = res.data
        ElMessage.info(`找到 ${res.data.length} 个匹配结果，请从下拉列表中选择`)
      }
    } else {
      ElMessage.info('未找到该患者，请新建档案')
      showCreateForm.value = true
      createForm.value.name = ''
      createForm.value.phone = ''
    }
  } catch (error) {
    ElMessage.error('查询失败')
  } finally {
    loading.value = false
  }
}

const handleSelect = (item) => {
  patient.value = item
  showCreateForm.value = false
  onPatientSelected()
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
        const res = await request.post('/doctor/patient', createForm.value)
        ElMessage.success('建档成功')
        patient.value = { ...createForm.value, id: res.data.id }
        showCreateForm.value = false
        onPatientSelected()
      } catch (error) {
        ElMessage.error(error.msg || '建档失败')
      } finally {
        creating.value = false
      }
    }
  })
}

const onPatientSelected = () => {
  if (!patient.value.phone) {
    tempPhone.value = ''
    phoneDialogVisible.value = true
  } else {
    initPrescription()
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
    initPrescription()
  } catch (error) {
    ElMessage.error('更新失败')
  } finally {
    updatingPhone.value = false
  }
}

const skipPhoneInput = () => {
  phoneDialogVisible.value = false
  initPrescription()
}

const reselectPatient = () => {
  patient.value = null
  resetPrescription()
}

// ===== Step 2: Prescription Logic =====
const loadingDrugs = ref(false)
const drugOptions = ref([])
const selectedDrugId = ref(null)
const prescriptionItems = ref([])
const checkContraindications = ref(false)
const consultationFee = ref(0.00) // 单独购药默认诊察费为0

const usageOptions = ref(['口服', '外用', '静脉注射', '肌肉注射', '皮下注射', '雾化吸入', '含服', '外敷', '滴眼', '滴耳', '滴鼻'])
const buildDosageOptions = () => {
  const out = []
  const push = (v) => {
    if (!v) return
    if (!out.includes(v)) out.push(v)
  }

  const countUnits = ['片', '粒', '支']
  countUnits.forEach(u => {
    for (let i = 1; i <= 6; i++) push(`${i}${u}`)
  })
  ;['10ml', '20ml'].forEach(push)
  ;['5g', '10g'].forEach(push)
  push('适量')
  return out
}

const dosageOptions = ref(buildDosageOptions())
const frequencyOptions = ref(['每日1次', '每日2次', '每日3次', '每日4次', '每4小时1次', '每6小时1次', '每8小时1次', '每12小时1次', '必要时', '睡前'])

const submitting = ref(false)

const totalAmount = computed(() => {
  const drugTotal = prescriptionItems.value.reduce((sum, item) => {
    return sum + Math.round(item.price * item.quantity * 100) / 100
  }, 0)
  return Math.round((drugTotal + consultationFee.value) * 100) / 100
})

const initPrescription = () => {
  searchDrugs('')
}

const searchDrugs = async (query) => {
  loadingDrugs.value = true
  try {
    const res = await request.get('/doctor/drugs/search', {
      params: { keyword: query }
    })
    const options = []
    ;(res.data || []).forEach(d => {
      if (d.variant_type === 'retail' || d.variant_type === 'pack' || d.variant_type === 'service') {
        options.push({
          ...d,
          option_id: `${d.id}:variant`,
          option_label: d.variant_type === 'service' ? '项目' : (d.variant_type === 'retail' ? '零散' : '整装'),
          display_price: d.price,
          is_scattered: false,
          maxStock: d.variant_type === 'service' ? 999 : d.stock
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
    if (prescriptionItems.value.find(item => item.option_id === drug.option_id)) {
      ElMessage.warning('该项目已添加')
    } else {
      prescriptionItems.value.push({
        id: drug.id,
        option_id: drug.option_id,
        name: drug.name,
        type: drug.type,
        specification: drug.specification,
        price: Math.round(drug.display_price * 100) / 100,
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

const resetPrescription = () => {
  prescriptionItems.value = []
  checkContraindications.value = false
  consultationFee.value = 0.00
}

const validatePrescription = () => {
  if (!prescriptionItems.value.length) {
    ElMessage.warning('请至少添加一条处方明细')
    return false
  }
  if (!checkContraindications.value) {
    ElMessage.warning('请勾选已人工审核药品禁忌')
    return false
  }
  for (let i = 0; i < prescriptionItems.value.length; i++) {
    const item = prescriptionItems.value[i]
    if (item.quantity <= 0) {
      ElMessage.warning(`第${i + 1}行数量不合法`)
      return false
    }
    if (item.type === 1) {
      if (!item.usage || !item.dosage || !item.frequency || !item.timing) {
        ElMessage.warning(`第${i + 1}行请完善用法用量信息`)
        return false
      }
    }
  }
  return true
}

const submitPrescription = async () => {
  if (!validatePrescription()) return
  
  submitting.value = true
  try {
    const payload = {
      patient_id: patient.value.id,
      chief_complaint: '单独购药',
      present_illness: '无',
      past_history: '无',
      physical_exam: '无',
      diagnosis: '单独购药',
      doctor_advice: '',
      consultation_fee: consultationFee.value,
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
.direct-purchase-container {
  padding: 20px;
}
.search-card {
  max-width: 800px;
  margin: 0 auto;
}
.search-box {
  display: flex;
  justify-content: center;
}
.search-input {
  max-width: 500px;
  width: 100%;
}
.create-card {
  max-width: 800px;
  margin: 0 auto;
}
.patient-suggestion {
  display: flex;
  align-items: center;
  gap: 12px;
}
.patient-suggestion .name {
  flex: 1;
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
</style>
