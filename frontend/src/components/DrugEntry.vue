<template>
  <el-card>
    <template #header>
      <div class="header">
        <span>入库录入</span>
      </div>
    </template>

    <el-form ref="formRef" :model="form" :rules="rules" label-position="top">
      <el-form-item label="入库类型" prop="type">
        <el-radio-group v-model="form.type">
          <el-radio :label="1">药品</el-radio>
          <el-radio :label="2">诊疗项目</el-radio>
        </el-radio-group>
      </el-form-item>

      <el-form-item label="药品/项目名称" prop="name">
        <el-select
          v-model="form.name"
          filterable
          remote
          reserve-keyword
          allow-create
          default-first-option
          :remote-method="searchNames"
          :loading="loadingNames"
          placeholder="输入名称联想，或直接输入新名称"
          style="width: 100%"
        >
          <el-option
            v-for="n in nameOptions"
            :key="n"
            :label="n"
            :value="n"
          />
        </el-select>
      </el-form-item>

      <el-form-item label="批次号" prop="batch_no">
        <el-input v-model="form.batch_no" placeholder="例如：2026-04-13-A01" />
      </el-form-item>

      <template v-if="form.type === 1">
        <el-form-item label="整份规格">
          <el-row :gutter="12" style="width: 100%">
            <el-col :span="12">
              <el-form-item label="含量" prop="dosage_value" label-position="top" style="margin-bottom: 0">
                <el-input-number v-model="form.dosage_value" :min="0" :precision="4" :step="0.1" style="width: 100%" />
              </el-form-item>
            </el-col>
            <el-col :span="12">
              <el-form-item label="含量单位" prop="dosage_unit" label-position="top" style="margin-bottom: 0">
                <el-select v-model="form.dosage_unit" filterable allow-create default-first-option style="width: 100%" placeholder="mg/IU等">
                  <el-option v-for="u in dosageUnitOptions" :key="u" :label="u" :value="u" />
                </el-select>
              </el-form-item>
            </el-col>
          </el-row>
          <el-row :gutter="12" style="width: 100%; margin-top: 12px">
            <el-col :span="12">
              <el-form-item label="每整件数量" prop="pack_amount" label-position="top" style="margin-bottom: 0">
                <el-input-number v-model="form.pack_amount" :min="1" :step="1" style="width: 100%" />
              </el-form-item>
            </el-col>
            <el-col :span="12">
              <el-form-item label="最小单位" prop="unit_name" label-position="top" style="margin-bottom: 0">
                <el-select v-model="form.unit_name" filterable allow-create default-first-option style="width: 100%" placeholder="片/粒等">
                  <el-option v-for="u in unitNameOptions" :key="u" :label="u" :value="u" />
                </el-select>
              </el-form-item>
            </el-col>
          </el-row>
          <el-row :gutter="12" style="width: 100%; margin-top: 12px">
            <el-col :span="12">
              <el-form-item label="整件单位" prop="pack_unit" label-position="top" style="margin-bottom: 0">
                <el-select v-model="form.pack_unit" filterable allow-create default-first-option style="width: 100%" placeholder="瓶/板/袋等">
                  <el-option v-for="u in packUnitOptions" :key="u" :label="u" :value="u" />
                </el-select>
              </el-form-item>
            </el-col>
            <el-col :span="12">
              <el-form-item label="生成规格" label-position="top" style="margin-bottom: 0">
                <el-input :model-value="packSpecText" disabled />
              </el-form-item>
            </el-col>
          </el-row>
          <div v-if="packMeta" class="hint">
            解析：包装量 {{ packMeta.packAmount }}{{ packMeta.unitName }} / {{ packMeta.packUnit }}
          </div>
        </el-form-item>

        <el-row :gutter="16">
          <el-col :span="12">
            <el-form-item label="整份单价(元)" prop="pack_price">
              <el-input-number v-model="form.pack_price" :min="0" :precision="2" :step="0.1" style="width: 100%" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="入库数量(整份)" prop="inbound_quantity">
              <el-input-number v-model="form.inbound_quantity" :min="1" :step="1" style="width: 100%" />
            </el-form-item>
          </el-col>
        </el-row>

        <el-form-item>
          <el-checkbox v-model="form.retail_enabled" @change="handleRetailToggle">可零售</el-checkbox>
        </el-form-item>

        <el-row :gutter="16">
          <el-col :span="12">
            <el-form-item label="最小销售单位" prop="min_sale_unit">
              <el-input
                v-model="form.min_sale_unit"
                placeholder="示例：2粒"
                :disabled="!form.retail_enabled"
              />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="最小销售单价(元)" prop="min_sale_price">
              <el-input-number
                v-model="form.min_sale_price"
                :min="0"
                :precision="2"
                :step="0.01"
                style="width: 100%"
                :disabled="!form.retail_enabled"
                @blur="handleMinPriceBlur"
              />
              <div v-if="thresholdHint" class="hint" :class="{ danger: thresholdHint.level === 'danger' }">
                {{ thresholdHint.text }}
              </div>
            </el-form-item>
          </el-col>
        </el-row>
      </template>

      <template v-else>
        <el-form-item label="规格" prop="specification">
          <el-input v-model="form.specification" placeholder="例如：次/项" />
        </el-form-item>
        <el-row :gutter="16">
          <el-col :span="12">
            <el-form-item label="单位" prop="unit">
              <el-input v-model="form.unit" placeholder="例如：次" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="单价(元)" prop="price">
              <el-input-number v-model="form.price" :min="0" :precision="2" :step="0.1" style="width: 100%" />
            </el-form-item>
          </el-col>
        </el-row>
      </template>

      <div class="actions">
        <el-button @click="resetForm" :disabled="submitting">重置</el-button>
        <el-button type="primary" @click="submit" :loading="submitting">提交入库</el-button>
      </div>
    </el-form>
  </el-card>
</template>

<script setup>
import { computed, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import request from '@/api/request'

const formRef = ref(null)
const submitting = ref(false)

const form = ref({
  type: 1,
  name: '',
  batch_no: '',
  pack_specification: '',
  dosage_value: null,
  dosage_unit: '',
  pack_amount: null,
  unit_name: '',
  pack_unit: '',
  pack_price: null,
  inbound_quantity: 1,
  retail_enabled: false,
  min_sale_unit: '',
  min_sale_price: null,
  specification: '',
  unit: '',
  price: null
})

const rules = computed(() => {
  const base = {
    type: [{ required: true, message: '请选择类型', trigger: 'change' }],
    name: [{ required: true, message: '请输入名称', trigger: 'blur' }],
    batch_no: [{ required: true, message: '请输入批次号', trigger: 'blur' }]
  }
  if (form.value.type === 1) {
    base.pack_amount = [{ required: true, message: '请输入每整件数量', trigger: 'blur' }]
    base.unit_name = [{ required: true, message: '请输入最小单位', trigger: 'change' }]
    base.pack_unit = [{ required: true, message: '请输入整件单位', trigger: 'change' }]
    base.pack_price = [{ required: true, message: '请输入整份单价', trigger: 'blur' }]
    base.inbound_quantity = [{ required: true, message: '请输入入库数量', trigger: 'blur' }]
    base.min_sale_unit = [{
      validator: (_rule, value, callback) => {
        if (!form.value.retail_enabled) return callback()
        if (!value || !String(value).trim()) return callback(new Error('请输入最小销售单位'))
        if (!/^\s*\d+\s*[^\d\s]+\s*$/.test(String(value))) return callback(new Error('格式示例：2粒'))
        callback()
      },
      trigger: 'blur'
    }]
    base.min_sale_price = [{
      validator: (_rule, value, callback) => {
        if (!form.value.retail_enabled) return callback()
        const v = Number(value)
        if (!Number.isFinite(v) || v <= 0) return callback(new Error('请输入最小销售单价'))
        const threshold = computeThreshold()
        if (threshold != null && v <= threshold) return callback(new Error(`单价过低，应大于 ${threshold.toFixed(2)}`))
        callback()
      },
      trigger: 'blur'
    }]
  } else {
    base.specification = [{ required: true, message: '请输入规格', trigger: 'blur' }]
    base.unit = [{ required: true, message: '请输入单位', trigger: 'blur' }]
    base.price = [{ required: true, message: '请输入单价', trigger: 'blur' }]
  }
  return base
})

const nameOptions = ref([])
const loadingNames = ref(false)
let nameTimer = null

const searchNames = (q) => {
  const keyword = String(q || '').trim()
  if (nameTimer) clearTimeout(nameTimer)
  nameTimer = setTimeout(async () => {
    loadingNames.value = true
    try {
      const res = await request.get('/nurse/drug-names/search', { params: { keyword } })
      nameOptions.value = res.data || []
    } catch {
      nameOptions.value = []
    } finally {
      loadingNames.value = false
    }
  }, 180)
}

const dosageUnitOptions = ['mg', 'g', 'μg', 'IU', 'mL', 'U', '%']
const unitNameOptions = ['片', '粒', '支', '袋', '包', '贴', '喷', '丸', '滴', '盒']
const packUnitOptions = ['盒', '瓶', '板', '袋', '支', '包', '箱']

const packSpecText = computed(() => {
  const packAmount = Number(form.value.pack_amount)
  const unitName = String(form.value.unit_name || '').trim()
  const packUnit = String(form.value.pack_unit || '').trim()
  const dv = Number(form.value.dosage_value)
  const du = String(form.value.dosage_unit || '').trim()

  if (!Number.isFinite(packAmount) || packAmount <= 0 || !unitName || !packUnit) return ''
  if (Number.isFinite(dv) && dv > 0 && du) {
    return `${dv}${du}×${packAmount}${unitName}/${packUnit}`
  }
  return `${packAmount}${unitName}/${packUnit}`
})

const packMeta = computed(() => {
  const packAmount = Number(form.value.pack_amount)
  const unitName = String(form.value.unit_name || '').trim()
  const packUnit = String(form.value.pack_unit || '').trim()
  if (!Number.isFinite(packAmount) || packAmount <= 0 || !unitName || !packUnit) return null
  return { packAmount, unitName, packUnit }
})

const handleRetailToggle = (checked) => {
  if (!checked) {
    form.value.min_sale_unit = ''
    form.value.min_sale_price = null
  }
}

const computeThreshold = () => {
  if (!form.value.retail_enabled) return null
  const meta = packMeta.value
  if (!meta) return null
  const packPrice = Number(form.value.pack_price)
  if (!Number.isFinite(packPrice) || packPrice <= 0) return null
  const min = String(form.value.min_sale_unit || '').trim()
  const mm = min.match(/^\s*(\d+)\s*([^\d\s]+)\s*$/)
  if (!mm) return null
  const minAmount = Number(mm[1])
  const minUnit = String(mm[2] || '').trim()
  if (minUnit !== meta.unitName) return null
  if (!Number.isFinite(minAmount) || minAmount <= 0) return null
  if (meta.packAmount % minAmount !== 0) return null
  return packPrice * (minAmount / meta.packAmount)
}

const thresholdHint = computed(() => {
  if (!form.value.retail_enabled) return null
  const meta = packMeta.value
  if (!meta) return { level: 'info', text: '请按示例填写规格以计算阈值' }
  const t = computeThreshold()
  if (t == null) return { level: 'info', text: '请填写最小销售单位以计算阈值（需能整除包装量）' }
  const p = Number(form.value.min_sale_price)
  if (Number.isFinite(p) && p > 0 && p <= t) return { level: 'danger', text: `单价过低：必须大于 ${t.toFixed(2)}` }
  return { level: 'info', text: `建议阈值：必须大于 ${t.toFixed(2)}` }
})

const handleMinPriceBlur = async () => {
  if (!form.value.retail_enabled) return
  const t = computeThreshold()
  const p = Number(form.value.min_sale_price)
  if (t != null && Number.isFinite(p) && p > 0 && p <= t) {
    ElMessage.error(`最小销售单价过低，必须大于 ${t.toFixed(2)}`)
  }
}

const resetForm = () => {
  form.value = {
    type: 1,
    name: '',
    batch_no: '',
    pack_specification: '',
    dosage_value: null,
    dosage_unit: '',
    pack_amount: null,
    unit_name: '',
    pack_unit: '',
    pack_price: null,
    inbound_quantity: 1,
    retail_enabled: false,
    min_sale_unit: '',
    min_sale_price: null,
    specification: '',
    unit: '',
    price: null
  }
  nameOptions.value = []
}

const submit = async () => {
  if (!formRef.value) return
  await formRef.value.validate(async (valid) => {
    if (!valid) return
    submitting.value = true
    try {
        const payload = { ...form.value, pack_specification: packSpecText.value }
      const res = await request.post('/nurse/inbound', payload)
      ElMessage.success('入库成功')
      resetForm()
      return res
    } catch (error) {
      if (error && error.code === 409) {
        await ElMessageBox.alert(error.msg || '存在重复批次记录', '重复校验', { type: 'warning' })
        return
      }
      if (error && error.threshold != null) {
        ElMessage.error(`${error.msg || '校验失败'}（阈值 > ${Number(error.threshold).toFixed(2)}）`)
        return
      }
      ElMessage.error(error.msg || '入库失败')
    } finally {
      submitting.value = false
    }
  })
}
</script>

<style scoped>
.header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.actions {
  display: flex;
  justify-content: flex-end;
  gap: 12px;
}
.hint {
  font-size: 12px;
  margin-top: 6px;
  color: #909399;
}
.hint.danger {
  color: #f56c6c;
}
</style>

