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
                <el-input v-model="visitForm.chief_complaint" type="textarea" :rows="2"></el-input>
              </el-form-item>
              <el-form-item label="现病史">
                <el-input v-model="visitForm.present_illness" type="textarea" :rows="2"></el-input>
              </el-form-item>
              <el-form-item label="既往史（过敏史）">
                <el-input v-model="visitForm.past_history" type="textarea" :rows="2"></el-input>
              </el-form-item>
              <el-form-item label="体格检查">
                <el-input v-model="visitForm.physical_exam" type="textarea" :rows="2"></el-input>
              </el-form-item>
              <el-form-item label="诊断" class="asterisk-left el-form-item--label-top">
                <el-autocomplete
                  v-model="visitForm.diagnosis"
                  :fetch-suggestions="querySearchDiagnosisAsync"
                  placeholder="请输入诊断或拼音首字母"
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
              </el-form-item>
              <el-form-item label="医生留言/小贴士 (如：适量运动，戒烟戒酒)">
                <el-input v-model="visitForm.doctor_advice" type="textarea" :rows="2" placeholder="给患者的自定义建议..."></el-input>
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
                <el-button type="primary" @click="submitVisit" :loading="submitting">提交处方</el-button>
              </div>
            </div>
          </el-card>
        </el-col>
      </el-row>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import request from '@/api/request'
import { ElMessage } from 'element-plus'

const route = useRoute()
const router = useRouter()

const patientId = route.query.patient_id
const patientName = route.query.patient_name
const studentId = route.query.student_id

// 电子病历表单
const visitForm = ref({
  chief_complaint: '',
  present_illness: '',
  past_history: '无',
  physical_exam: '',
  diagnosis: '',
  doctor_advice: '',
  consultation_fee: 5.00
})

// 药品相关
const loadingDrugs = ref(false)
const drugOptions = ref([])
const selectedDrugId = ref(null)
const prescriptionItems = ref([])

// 预设选项数据
const usageOptions = ref(['口服', '外用', '静脉注射', '肌肉注射', '皮下注射', '雾化吸入', '含服', '外敷', '滴眼', '滴耳', '滴鼻'])
const dosageOptions = ref(['1片', '2片', '1粒', '2粒', '1支', '2支', '10ml', '20ml', '5g', '10g', '适量'])
const frequencyOptions = ref(['每日1次', '每日2次', '每日3次', '每日4次', '每4小时1次', '每6小时1次', '每8小时1次', '每12小时1次', '必要时', '睡前'])

// 提交状态
const submitting = ref(false)

const totalAmount = computed(() => {
  const drugTotal = prescriptionItems.value.reduce((sum, item) => {
    return sum + (item.price * item.quantity)
  }, 0)
  return drugTotal + visitForm.value.consultation_fee
})

onMounted(() => {
  if (!patientId) {
    ElMessage.error('未指定患者，请先搜索')
    router.push('/doctor/patient')
  }
  // Load default drugs
  searchDrugs('')
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
  visitForm.value.diagnosis = item.name
}

const searchDrugs = async (query) => {
  loadingDrugs.value = true
  try {
    const res = await request.get('/doctor/drugs/search', {
      params: { keyword: query }
    })
    const options = []
    ;(res.data || []).forEach(d => {
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

const resetForm = () => {
  visitForm.value = {
    chief_complaint: '',
    present_illness: '',
    past_history: '无',
    physical_exam: '',
    diagnosis: '',
    doctor_advice: '',
    consultation_fee: 5.00
  }
  prescriptionItems.value = []
}

const submitVisit = async () => {
  if (!visitForm.value.diagnosis) {
    ElMessage.warning('请填写诊断信息')
    return
  }
  
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
</style>
