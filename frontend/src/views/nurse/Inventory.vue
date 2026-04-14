<template>
  <div class="inventory-container">
    <el-tabs v-model="activeTab" class="inventory-tabs">
      <el-tab-pane label="入库管理" name="inbound">
        <DrugEntry />
      </el-tab-pane>

      <!-- 盘点操作标签页 -->
      <el-tab-pane label="库存盘点" name="inventory">
        <el-card>
          <template #header>
            <div class="card-header">
              <span>药品库存列表</span>
              <el-input
                v-model="searchQuery"
                placeholder="搜索药品名称/规格"
                style="width: 300px"
                clearable
                @clear="fetchDrugs"
                @keyup.enter="fetchDrugs"
              >
                <template #append>
                  <el-button :icon="Search" @click="fetchDrugs" />
                </template>
              </el-input>
            </div>
          </template>

          <el-table :data="drugs" stripe style="width: 100%" v-loading="loading">
            <el-table-column prop="name" label="药名" />
            <el-table-column prop="specification" label="规格" width="150" />
            <el-table-column label="包装" width="90">
              <template #default="scope">
                <el-tag v-if="scope.row.variant_type === 'pack'">整装</el-tag>
                <el-tag v-else-if="scope.row.variant_type === 'retail'" type="warning">零散</el-tag>
                <el-tag v-else-if="scope.row.has_scattered" type="info">整/散</el-tag>
                <span v-else>-</span>
              </template>
            </el-table-column>
            <el-table-column prop="unit" label="单位" width="100" />
            <el-table-column label="售价" width="100">
              <template #default="scope">
                <span style="color: #67C23A; font-weight: bold;">¥ {{ scope.row.price.toFixed(2) }}</span>
              </template>
            </el-table-column>
            <el-table-column prop="stock" label="当前系统库存" width="120">
              <template #default="scope">
                <el-tag :type="scope.row.stock < 10 ? 'danger' : 'success'">
                  {{ scope.row.stock }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column label="操作" width="150" fixed="right">
              <template #default="scope">
                <el-button type="primary" size="small" @click="openInventoryDialog(scope.row)">
                  盘点
                </el-button>
              </template>
            </el-table-column>
          </el-table>
        </el-card>
      </el-tab-pane>

      <!-- 盘点记录标签页 -->
      <el-tab-pane label="盘点记录" name="records">
        <el-card>
          <el-table :data="records" stripe style="width: 100%" v-loading="loadingRecords">
            <el-table-column prop="timestamp" label="盘点时间" width="180" />
            <el-table-column prop="drug_name" label="药名" />
            <el-table-column prop="specification" label="规格" width="120" />
            <el-table-column label="库存变更" width="150">
              <template #default="scope">
                {{ scope.row.old_stock }} → <b>{{ scope.row.new_stock }}</b>
              </template>
            </el-table-column>
            <el-table-column prop="nurse_name" label="操作人" width="100" />
            <el-table-column prop="remark" label="盘点备注" />
          </el-table>

          <div class="pagination">
            <el-pagination
              v-model:current-page="recordPage"
              v-model:page-size="recordSize"
              :total="recordTotal"
              layout="total, prev, pager, next"
              @current-change="fetchRecords"
            />
          </div>
        </el-card>
      </el-tab-pane>
    </el-tabs>

      <!-- 盘点弹窗 (普通药品) -->
      <el-dialog
        v-model="dialogVisible"
        title="库存盘点"
        width="400px"
      >
        <el-form :model="form" :rules="rules" ref="formRef" label-width="100px">
          <el-form-item label="药品名称">
            <span>{{ currentDrug?.name }} ({{ currentDrug?.specification }})</span>
          </el-form-item>
          <el-form-item label="原库存量">
            <el-tag type="info">{{ currentDrug?.stock }}</el-tag>
          </el-form-item>
          <el-form-item label="实际数量" prop="new_stock">
            <el-input-number v-model="form.new_stock" :min="0" :step="1" />
          </el-form-item>
          <el-form-item label="盘点备注" prop="remark">
            <el-input
              v-model="form.remark"
              type="textarea"
              :rows="3"
              placeholder="请填写盘点原因（如：损耗等）"
            />
          </el-form-item>
        </el-form>
        <template #footer>
          <span class="dialog-footer">
            <el-button @click="dialogVisible = false">取消</el-button>
            <el-button type="primary" @click="submitInventory" :loading="submitting">
              确认盘点
            </el-button>
          </span>
        </template>
      </el-dialog>

      <!-- 联合盘点弹窗 (整散库存组药品) -->
      <el-dialog
        v-model="groupDialogVisible"
        title="整散联合盘点"
        width="450px"
      >
        <div style="margin-bottom: 20px; font-size: 13px; color: #606266; line-height: 1.5;">
          该药品为整散共享库存，调整需同时输入<strong>实际物理存在的整盒数</strong>与<strong>实际物理存在的散件数</strong>，系统将自动核算新的库存总量并同步。
        </div>
        <el-form :model="groupForm" :rules="groupRules" ref="groupFormRef" label-width="100px">
          <el-form-item label="药品名称">
            <span style="font-weight: bold;">{{ currentDrug?.base_name || currentDrug?.name }}</span>
          </el-form-item>
          <el-form-item label="包装规格">
            <span>{{ currentDrug?.unit_amount || '未知' }} 最小单位 / 整件</span>
          </el-form-item>
          <el-form-item label="实际整件数" prop="actual_packs">
            <el-input-number v-model="groupForm.actual_packs" :min="0" :step="1" />
          </el-form-item>
          <el-form-item label="实际散件数" prop="actual_retail_units">
            <el-input-number v-model="groupForm.actual_retail_units" :min="0" :step="1" />
          </el-form-item>
          <el-form-item label="盘点后总计">
            <el-tag type="warning" size="large">
              {{ groupForm.actual_packs * (currentDrug?.unit_amount || 0) + groupForm.actual_retail_units }} 最小单位
            </el-tag>
          </el-form-item>
          <el-form-item label="盘点备注" prop="remark">
            <el-input
              v-model="groupForm.remark"
              type="textarea"
              :rows="2"
              placeholder="请填写盘点原因（如：药片破损、过期清理等）"
            />
          </el-form-item>
        </el-form>
        <template #footer>
          <span class="dialog-footer">
            <el-button @click="groupDialogVisible = false">取消</el-button>
            <el-button type="primary" @click="submitGroupInventory" :loading="submitting">
              确认联合盘点
            </el-button>
          </span>
        </template>
      </el-dialog>
    </div>
  </template>

<script setup>
import { ref, onMounted, watch } from 'vue'
import { Search } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import request from '@/api/request'
import DrugEntry from '@/components/DrugEntry.vue'

const activeTab = ref('inventory')

// Inventory Tab
const searchQuery = ref('')
const drugs = ref([])
const loading = ref(false)

// Records Tab
const records = ref([])
const loadingRecords = ref(false)
const recordPage = ref(1)
const recordSize = ref(20)
const recordTotal = ref(0)

// Dialog
const dialogVisible = ref(false)
const groupDialogVisible = ref(false)
const submitting = ref(false)
const currentDrug = ref(null)
const formRef = ref(null)
const groupFormRef = ref(null)

const form = ref({
  new_stock: 0,
  remark: ''
})

const rules = {
  new_stock: [{ required: true, message: '请输入实际数量', trigger: 'blur' }],
  remark: [{ required: true, message: '请填写盘点备注', trigger: 'blur' }]
}

const groupForm = ref({
  actual_packs: 0,
  actual_retail_units: 0,
  remark: ''
})

const groupRules = {
  actual_packs: [{ required: true, message: '请输入实际整件数', trigger: 'blur' }],
  actual_retail_units: [{ required: true, message: '请输入实际散件数', trigger: 'blur' }],
  remark: [{ required: true, message: '请填写盘点备注', trigger: 'blur' }]
}

const fetchDrugs = async () => {
  loading.value = true
  try {
    const res = await request.get('/nurse/drugs', {
      params: { keyword: searchQuery.value }
    })
    drugs.value = res.data
  } catch (error) {
    ElMessage.error('获取药品列表失败')
  } finally {
    loading.value = false
  }
}

const fetchRecords = async () => {
  loadingRecords.value = true
  try {
    const res = await request.get('/nurse/inventory/records', {
      params: {
        page: recordPage.value,
        size: recordSize.value
      }
    })
    records.value = res.data
    recordTotal.value = res.meta.total
  } catch (error) {
    ElMessage.error('获取盘点记录失败')
  } finally {
    loadingRecords.value = false
  }
}

const openInventoryDialog = (drug) => {
  currentDrug.value = drug
  if (drug && drug.stock_group_code) {
    // 根据当前库存和换算率，大致推算当前的整散件，方便护士参考
    const isRetail = drug.variant_type === 'retail'
    const packs = isRetail ? Math.floor(drug.stock / (drug.unit_amount || 1)) : drug.stock
    const loose = isRetail ? (drug.stock % (drug.unit_amount || 1)) : 0
    
    groupForm.value.actual_packs = packs
    groupForm.value.actual_retail_units = loose
    groupForm.value.remark = ''
    groupDialogVisible.value = true
  } else {
    form.value.new_stock = drug.stock
    form.value.remark = ''
    dialogVisible.value = true
  }
}

const submitGroupInventory = async () => {
  if (!groupFormRef.value) return
  await groupFormRef.value.validate(async (valid) => {
    if (valid) {
      submitting.value = true
      try {
        await request.post('/nurse/inventory/group', {
          group_code: currentDrug.value.stock_group_code,
          actual_packs: groupForm.value.actual_packs,
          actual_retail_units: groupForm.value.actual_retail_units,
          remark: groupForm.value.remark
        })
        ElMessage.success('联合盘点成功')
        groupDialogVisible.value = false
        fetchDrugs()
        if (activeTab.value === 'records') {
          fetchRecords()
        }
      } catch (error) {
        ElMessage.error(error.msg || '盘点失败')
      } finally {
        submitting.value = false
      }
    }
  })
}

const submitInventory = async () => {
  if (!formRef.value) return
  await formRef.value.validate(async (valid) => {
    if (valid) {
      if (form.value.new_stock === currentDrug.value.stock) {
        ElMessage.warning('实际数量未发生变化，无需盘点')
        return
      }

      submitting.value = true
      try {
        await request.post('/nurse/inventory', {
          drug_id: currentDrug.value.id,
          new_stock: form.value.new_stock,
          remark: form.value.remark
        })
        ElMessage.success('盘点成功')
        dialogVisible.value = false
        fetchDrugs()
        if (activeTab.value === 'records') {
          fetchRecords()
        }
      } catch (error) {
        ElMessage.error(error.msg || '盘点失败')
      } finally {
        submitting.value = false
      }
    }
  })
}

watch(activeTab, (newTab) => {
  if (newTab === 'records') {
    fetchRecords()
  } else {
    fetchDrugs()
  }
})

onMounted(() => {
  fetchDrugs()
})
</script>

<style scoped>
.inventory-container {
  padding: 20px;
}
.inventory-tabs {
  background: #fff;
  padding: 20px;
  border-radius: 8px;
  box-shadow: 0 2px 12px 0 rgba(0,0,0,0.1);
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
