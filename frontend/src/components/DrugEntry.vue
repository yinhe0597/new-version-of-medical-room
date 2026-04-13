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
        <el-form-item label="整份规格" prop="pack_specification">
          <el-input v-model="form.pack_specification" placeholder="示例：20 mg×100粒/瓶" @blur="handlePackSpecBlur" />
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
    base.pack_specification = [{ required: true, message: '请输入整份规格', trigger: 'blur' }]
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

const packMeta = ref(null)
const parsePackSpec = (text) => {
  const s = String(text || '').trim()
  const ok = /^\s*.+[xX×]\s*\d+\s*[^\d/]+\s*\/\s*\S+\s*$/.test(s)
  if (!ok) return null
  const m = s.match(/[xX×]\s*(\d+)\s*([^\d/\s]+)\s*\/\s*(\S+)\s*$/)
  if (!m) return null
  const packAmount = Number(m[1])
  const unitName = String(m[2] || '').trim()
  const packUnit = String(m[3] || '').trim()
  if (!Number.isFinite(packAmount) || packAmount <= 0 || !unitName || !packUnit) return null
  return { packAmount, unitName, packUnit }
}

const handlePackSpecBlur = () => {
  packMeta.value = parsePackSpec(form.value.pack_specification)
}

const handleRetailToggle = (checked) => {
  if (!checked) {
    form.value.min_sale_unit = ''
    form.value.min_sale_price = null
  }
}

const computeThreshold = () => {
  if (!form.value.retail_enabled) return null
  const meta = packMeta.value || parsePackSpec(form.value.pack_specification)
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
  const meta = packMeta.value || parsePackSpec(form.value.pack_specification)
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
    pack_price: null,
    inbound_quantity: 1,
    retail_enabled: false,
    min_sale_unit: '',
    min_sale_price: null,
    specification: '',
    unit: '',
    price: null
  }
  packMeta.value = null
  nameOptions.value = []
}

const submit = async () => {
  if (!formRef.value) return
  await formRef.value.validate(async (valid) => {
    if (!valid) return
    submitting.value = true
    try {
      const payload = { ...form.value }
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

