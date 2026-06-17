<template>
  <div class="drug-management">
    <el-card>
      <template #header>
        <div class="card-header">
          <div class="left-panel">
            <el-button type="primary" :icon="Plus" @click="openCreateDialog">新增</el-button>
          </div>
          <div class="right-panel">
            <el-input 
              v-model="keyword" 
              placeholder="搜索药品名称" 
              @keyup.enter="fetchDrugs"
              clearable
              @clear="fetchDrugs"
            >
              <template #append>
                <el-button @click="fetchDrugs">搜索</el-button>
              </template>
            </el-input>
          </div>
        </div>
      </template>

      <el-table :data="drugList" v-loading="loading" stripe style="width: 100%">
        <el-table-column prop="storage_location" label="存放位置" width="90">
          <template #default="scope">{{ scope.row.storage_location || '-' }}</template>
        </el-table-column>
        <el-table-column prop="name" label="名称" />
        <el-table-column prop="type" label="类型" width="100">
          <template #default="scope">
            <el-tag :type="scope.row.type === 2 ? 'warning' : scope.row.type === 3 ? 'info' : ''">
              {{ scope.row.type === 2 ? '诊疗项目' : scope.row.type === 3 ? '耗材' : '药品' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="包装" width="90" v-if="!isNurse">
          <template #default="scope">
            <el-tag v-if="scope.row.variant_type === 'pack'">整装</el-tag>
            <el-tag v-else-if="scope.row.variant_type === 'retail'" type="warning">零散</el-tag>
            <el-tag v-else-if="scope.row.variant_type === 'consumable'" type="info">耗材</el-tag>
            <span v-else>-</span>
          </template>
        </el-table-column>
        <el-table-column prop="specification" label="规格" />
        <el-table-column prop="unit" label="单位" width="80" />
        <el-table-column prop="purchase_price" label="购进价" width="80">
          <template #default="scope">
            ¥ {{ scope.row.purchase_price ? scope.row.purchase_price.toFixed(2) : '0.00' }}
          </template>
        </el-table-column>
        <el-table-column prop="price" label="零售价" width="80">
          <template #default="scope">
            ¥ {{ scope.row.price.toFixed(2) }}
          </template>
        </el-table-column>
        <el-table-column prop="scattered_price" label="零卖单价" width="80" v-if="!isNurse">
          <template #default="scope">
            {{ scope.row.has_scattered ? '¥ ' + scope.row.scattered_price.toFixed(4) : '-' }}
          </template>
        </el-table-column>
        <el-table-column prop="conversion_rate" label="转换率" width="80">
          <template #default="scope">
            {{ scope.row.has_scattered ? scope.row.conversion_rate : '-' }}
          </template>
        </el-table-column>
        <el-table-column prop="stock" label="库存" width="80" />
        <el-table-column label="有效期" width="120">
          <template #default="scope">
            <template v-if="scope.row.expiry_date">
              <el-tag
                :type="getExpiryTagType(scope.row.expiry_date)"
                size="small"
              >
                {{ scope.row.expiry_date }}
                <span v-if="getExpiryDays(scope.row.expiry_date) < 0" style="margin-left: 4px; font-size: 11px;">已过期</span>
                <span v-else-if="getExpiryDays(scope.row.expiry_date) <= 30" style="margin-left: 4px; font-size: 11px;">{{ getExpiryDays(scope.row.expiry_date) }}天</span>
              </el-tag>
            </template>
            <span v-else style="color: #909399;">—</span>
          </template>
        </el-table-column>
        <el-table-column prop="status" label="状态" width="100">
          <template #default="scope">
            <el-tag :type="scope.row.status === 1 ? 'success' : 'info'">
              {{ scope.row.status === 1 ? '启用' : '停用' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="180">
          <template #default="scope">
            <el-button size="small" @click="openEditDialog(scope.row)">编辑</el-button>
            <el-button 
              size="small" 
              type="warning" 
              @click="handleDisable(scope.row)" 
              v-if="scope.row.status === 1"
            >停用</el-button>
            <el-button 
              size="small" 
              type="success" 
              @click="handleEnable(scope.row)" 
              v-else
            >启用</el-button>
            <el-button 
              size="small" 
              type="danger" 
              @click="handleRealDelete(scope.row)" 
            >删除</el-button>
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

    <!-- 药品表单弹窗 -->
    <el-dialog 
      v-model="dialogVisible" 
      :title="isEdit ? '编辑项' : '新增项'" 
      width="500px"
    >
      <el-form :model="form" :rules="rules" ref="formRef" label-width="80px">
        <el-form-item label="类型" prop="type">
          <el-radio-group v-model="form.type" @change="handleTypeChange">
            <el-radio :label="1">药品</el-radio>
            <el-radio :label="2">诊疗项目 (打包收费)</el-radio>
            <el-radio :label="3">耗材</el-radio>
          </el-radio-group>
        </el-form-item>
        <el-form-item label="存放位置">
          <div style="display: flex; gap: 8px; align-items: center;">
            <el-select v-model="storageLetter" placeholder="字母" clearable style="width: 80px;" @change="onStorageLetterChange">
              <el-option v-for="l in locationLetters" :key="l" :label="l" :value="l" />
            </el-select>
            <span style="color: #909399;" v-if="storageLetter">+</span>
            <el-input v-model="storageSuffix" placeholder="编号/备注（如1-2、散、库房）" clearable :disabled="!storageLetter" style="width: 200px;" @input="onStorageSuffixChange" />
          </div>
        </el-form-item>
        <el-form-item label="名称" prop="name">
          <el-input v-model="form.name" placeholder="如：阿莫西林 或 小换药"></el-input>
        </el-form-item>
        <el-form-item label="规格" prop="specification">
          <el-input v-model="form.specification" :placeholder="form.type === 2 ? '如：次/项' : ''" :disabled="isGroupedStock && form.type === 1"></el-input>
        </el-form-item>
        <el-form-item label="单位" prop="unit">
          <el-input v-model="form.unit" :placeholder="form.type === 2 ? '如：次' : ''" :disabled="isGroupedStock && form.type === 1"></el-input>
        </el-form-item>
        <el-form-item label="购进价" prop="purchase_price">
          <el-input-number v-model="form.purchase_price" :min="0" :precision="2" :step="0.1" />
        </el-form-item>
        <el-form-item label="零售价" prop="price">
          <el-input-number v-model="form.price" :min="0" :precision="2" :step="0.1" />
        </el-form-item>
        <el-form-item label="支持零卖" prop="has_scattered" v-if="form.type === 1 && !isGroupedStock">
          <el-switch v-model="form.has_scattered" />
        </el-form-item>
        <el-form-item label="零卖价" prop="scattered_price" v-if="form.type === 1 && form.has_scattered && !isGroupedStock">
          <el-input-number v-model="form.scattered_price" :min="0" :precision="4" :step="0.01" />
        </el-form-item>
        <el-form-item label="转换率" prop="conversion_rate" v-if="form.type === 1 && form.has_scattered && !isGroupedStock">
          <el-input-number v-model="form.conversion_rate" :min="1" :step="1" placeholder="1整件=多少零卖单位" />
        </el-form-item>
        <el-form-item :label="isEdit ? '现有库存' : '初始库存'" prop="stock" v-if="form.type === 1 || form.type === 3">
          <el-input-number v-model="form.stock" :min="0" :step="1" :disabled="isEdit || isGroupedStock" />
        </el-form-item>
        <el-form-item label="有效期" v-if="form.type === 1 || form.type === 3">
          <el-date-picker
            v-model="form.expiry_date"
            type="date"
            placeholder="选择有效期"
            value-format="YYYY-MM-DD"
            :disabled-date="(d) => d < new Date(new Date().setHours(0,0,0,0))"
            clearable
          />
        </el-form-item>

        <!-- 库存操作区域（仅编辑模式） -->
        <div v-if="isEdit && (form.type === 1 || form.type === 3)" style="margin-bottom: 18px; padding: 12px; background: #f5f7fa; border-radius: 6px;">
          <div style="margin-bottom: 10px;">
            <el-button type="warning" size="small" @click="showCorrectionForm = !showCorrectionForm">
              盘点勘误
            </el-button>
            <el-button type="success" size="small" @click="showInboundForm = !showInboundForm">
              入库
            </el-button>
          </div>

          <!-- 盘点勘误表单 -->
          <div v-if="showCorrectionForm" style="margin-top: 10px; padding: 10px; background: #fff; border-radius: 4px;">
            <el-form-item label="实际数量" style="margin-bottom: 8px;">
              <el-input-number v-model="correctionStock" :min="0" :step="1" />
            </el-form-item>
            <el-form-item label="备注" style="margin-bottom: 8px;">
              <el-input v-model="correctionRemark" placeholder="请填写勘误原因" />
            </el-form-item>
            <el-button type="warning" size="small" @click="submitCorrection" :loading="correctionLoading">
              确认勘误
            </el-button>
          </div>

          <!-- 入库表单 -->
          <div v-if="showInboundForm" style="margin-top: 10px; padding: 10px; background: #fff; border-radius: 4px;">
            <el-form-item label="入库数量" style="margin-bottom: 8px;">
              <el-input-number v-model="inboundQuantity" :min="1" :step="1" />
            </el-form-item>
            <el-form-item label="备注" style="margin-bottom: 8px;">
              <el-input v-model="inboundRemark" placeholder="如：进货补充" />
            </el-form-item>
            <el-button type="success" size="small" @click="submitInbound" :loading="inboundLoading">
              确认入库
            </el-button>
          </div>
        </div>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" @click="submitForm" :loading="submitting">确定</el-button>
      </template>
    </el-dialog>


  </div>
</template>

<script setup>
import { ref, onMounted, computed, watch } from 'vue'
import request from '@/api/request'
import { Plus } from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useUserStore } from '@/store/user'

const userStore = useUserStore()
const isNurse = computed(() => userStore.userInfo?.role === 'nurse')

const keyword = ref('')
const drugList = ref([])
const loading = ref(false)
const page = ref(1)
const pageSize = ref(20)
const total = ref(0)

const dialogVisible = ref(false)

const isEdit = ref(false)
const submitting = ref(false)
const formRef = ref(null)



// 库存操作相关
const showCorrectionForm = ref(false)
const showInboundForm = ref(false)
const correctionStock = ref(0)
const correctionRemark = ref('')
const correctionLoading = ref(false)
const inboundQuantity = ref(1)
const inboundRemark = ref('')
const inboundLoading = ref(false)

const submitCorrection = async () => {
  if (correctionStock.value === form.value.stock) {
    ElMessage.warning('实际数量未发生变化')
    return
  }
  correctionLoading.value = true
  try {
    await request.post('/nurse/inventory', {
      drug_id: form.value.id,
      new_stock: correctionStock.value,
      remark: correctionRemark.value || '盘点勘误'
    })
    ElMessage.success('盘点勘误成功')
    form.value.stock = correctionStock.value
    showCorrectionForm.value = false
    correctionRemark.value = ''
    fetchDrugs()
  } catch (error) {
    ElMessage.error(error.msg || '勘误失败')
  } finally {
    correctionLoading.value = false
  }
}

const submitInbound = async () => {
  if (!inboundQuantity.value || inboundQuantity.value <= 0) {
    ElMessage.warning('入库数量必须大于0')
    return
  }
  inboundLoading.value = true
  try {
    const res = await request.post(`/admin/drugs/${form.value.id}/inbound`, {
      quantity: inboundQuantity.value,
      remark: inboundRemark.value || ''
    })
    ElMessage.success('入库成功')
    form.value.stock = res.data.new_stock
    showInboundForm.value = false
    inboundQuantity.value = 1
    inboundRemark.value = ''
    fetchDrugs()
  } catch (error) {
    ElMessage.error(error.msg || '入库失败')
  } finally {
    inboundLoading.value = false
  }
}


const form = ref({
  id: null,
  name: '',
  type: 1,
  specification: '',
  unit: '',
  purchase_price: 0,
  price: 0,
  has_scattered: false,
  scattered_price: null,
  conversion_rate: null,
  stock: 0,
  status: 1,
  batch_no: null,
  inbound_at: null,
  variant_type: null,
  stock_group_code: null,
  unit_amount: null,
  base_name: null,
  storage_location: null,
  expiry_date: null
})

const isGroupedStock = computed(() => Boolean(form.value && form.value.stock_group_code))

// 有效期计算工具
const getExpiryDays = (expiryDate) => {
  if (!expiryDate) return null
  const today = new Date()
  today.setHours(0, 0, 0, 0)
  const expiry = new Date(expiryDate)
  return Math.ceil((expiry - today) / (1000 * 60 * 60 * 24))
}

const getExpiryTagType = (expiryDate) => {
  const days = getExpiryDays(expiryDate)
  if (days === null) return 'info'
  if (days < 0) return 'danger'      // 已过期
  if (days <= 30) return 'warning'   // 30天内到期
  return 'success'                   // 正常
}

// 存放位置级联选择
const locationLetters = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ'.split('')
const storageLetter = ref(null)
const storageSuffix = ref('')

const syncStorageLocation = () => {
  const suffix = storageSuffix.value.trim()
  if (storageLetter.value && suffix) {
    form.value.storage_location = storageLetter.value + suffix
  } else {
    form.value.storage_location = null
  }
}

const onStorageLetterChange = () => {
  if (!storageLetter.value) storageSuffix.value = ''
  syncStorageLocation()
}

const onStorageSuffixChange = () => { syncStorageLocation() }

const rules = {
  name: [{ required: true, message: '请输入名称', trigger: 'blur' }],
  specification: [{ required: true, message: '请输入规格', trigger: 'blur' }],
  unit: [{ required: true, message: '请输入单位', trigger: 'blur' }],
  price: [{ required: true, message: '请输入单价', trigger: 'blur' }],
  stock: [
    { 
      required: true, 
      validator: (rule, value, callback) => {
        if (form.value.type === 1 && (value === null || value === undefined)) {
          callback(new Error('请输入库存'))
        } else {
          callback()
        }
      }, 
      trigger: 'blur' 
    }
  ]
}

const handleTypeChange = (val) => {
  if (val === 2) {
    form.value.stock = -1
    form.value.has_scattered = false
    form.value.scattered_price = null
    form.value.conversion_rate = null
    if (!form.value.specification) form.value.specification = '项';
    if (!form.value.unit) form.value.unit = '次';
  } else {
    form.value.stock = 0;
    if (val === 3) {
      form.value.has_scattered = false
      form.value.scattered_price = null
      form.value.conversion_rate = null
    }
  }
}

watch(
  () => form.value.has_scattered,
  (val) => {
    if (!val) {
      form.value.scattered_price = null
      form.value.conversion_rate = null
    }
  }
)

const fetchDrugs = async () => {
  loading.value = true
  try {
    const res = await request.get('/admin/drugs', {
      params: {
        page: page.value,
        size: pageSize.value,
        keyword: keyword.value
      }
    })
    drugList.value = res.data || []
    total.value = res.meta ? res.meta.total : 0
  } catch (error) {
    console.error('Fetch drugs failed:', error)
    ElMessage.error(error.msg || '获取列表失败')
  } finally {
    loading.value = false
  }
}

const handlePageChange = (val) => {
  page.value = val
  fetchDrugs()
}

const openCreateDialog = () => {
  isEdit.value = false
  form.value = {
    id: null,
    name: '',
    type: 1,
    specification: '',
    unit: '',
    purchase_price: 0,
    price: 0,
    has_scattered: false,
    scattered_price: null,
    conversion_rate: null,
    stock: 0,
    status: 1,
    batch_no: null,
    inbound_at: null,
    variant_type: null,
    stock_group_code: null,
    unit_amount: null,
    base_name: null,
    storage_location: null,
    expiry_date: null
  }
  storageLetter.value = null
  storageSuffix.value = ''
  dialogVisible.value = true
}

const openEditDialog = (row) => {
  isEdit.value = true
  form.value = {
    purchase_price: 0,
    has_scattered: false,
    scattered_price: null,
    conversion_rate: null,
    batch_no: null,
    inbound_at: null,
    variant_type: null,
    stock_group_code: null,
    unit_amount: null,
    base_name: null,
    storage_location: null,
    expiry_date: null,
    ...row
  }
  const loc = row.storage_location
  if (loc && /^[A-Z]/.test(loc)) {
    storageLetter.value = loc[0]
    storageSuffix.value = loc.slice(1)
  } else {
    storageLetter.value = null
    storageSuffix.value = ''
  }
  showCorrectionForm.value = false
  showInboundForm.value = false
  correctionStock.value = form.value.stock
  dialogVisible.value = true
}

const submitForm = async () => {
  if (!formRef.value) return
  await formRef.value.validate(async (valid) => {
    if (valid) {
      submitting.value = true
      try {
        const payload = { ...form.value }
        if (payload.type === 2) {
          payload.stock = -1
          payload.has_scattered = false
          payload.scattered_price = null
          payload.conversion_rate = null
        }
        if (!payload.has_scattered) {
          payload.scattered_price = null
          payload.conversion_rate = null
        }
        if (payload.stock_group_code) {
          delete payload.stock
          delete payload.has_scattered
          delete payload.scattered_price
          delete payload.conversion_rate
        }
        
        if (isEdit.value) {
          await request.put(`/admin/drugs/${payload.id}`, payload)
          ElMessage.success('修改成功')
        } else {
          await request.post('/admin/drugs', payload)
          ElMessage.success('添加成功')
        }
        dialogVisible.value = false
        fetchDrugs()
      } catch (error) {
        ElMessage.error(error.msg || '操作失败')
      } finally {
        submitting.value = false
      }
    }
  })
}

const handleDisable = (row) => {
  ElMessageBox.confirm(
    `确定要停用药品 ${row.name} 吗？`,
    '警告',
    {
      confirmButtonText: '确定',
      cancelButtonText: '取消',
      type: 'warning',
    }
  ).then(async () => {
    try {
      await request.put(`/admin/drugs/${row.id}`, { status: 0 })
      ElMessage.success('已停用')
      fetchDrugs()
    } catch (error) {
      ElMessage.error('操作失败')
    }
  })
}

const handleRealDelete = (row) => {
  ElMessageBox.confirm(
    `确定要永久删除 ${row.name} 吗？此操作不可恢复！\n如果该项目已被历史处方引用，将无法删除。`,
    '严重警告',
    {
      confirmButtonText: '确定删除',
      cancelButtonText: '取消',
      type: 'error',
    }
  ).then(async () => {
    try {
      await request.delete(`/admin/drugs/${row.id}`)
      ElMessage.success('已永久删除')
      fetchDrugs()
    } catch (error) {
      ElMessage.error(error.msg || '删除失败')
    }
  }).catch(() => {})
}

const handleEnable = async (row) => {
  try {
    // Reuse update API to enable
    await request.put(`/admin/drugs/${row.id}`, { status: 1 })
    ElMessage.success('已启用')
    fetchDrugs()
  } catch (error) {
    ElMessage.error('操作失败')
  }
}


onMounted(() => {
  fetchDrugs()
})
</script>

<style scoped>
.drug-management {
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
</style>
