<template>
  <div class="inventory-container">
    <el-tabs v-model="activeTab" class="inventory-tabs">
      <!-- 盘点操作标签页 -->
      <el-tab-pane label="库存盘点" name="inventory">
        <el-card>
          <template #header>
            <div class="card-header">
              <div style="display: flex; align-items: center; gap: 12px;">
                <span>药品库存列表</span>
                <el-button type="warning" @click="handleSmartInventory">
                  <el-icon><Cpu /></el-icon> 智能盘库
                </el-button>
              </div>
              <el-input
                v-model="searchQuery"
                placeholder="搜索药品名称/规格"
                style="width: 300px"
                clearable
                @clear="() => { drugPage = 1; fetchDrugs() }"
                @keyup.enter="() => { drugPage = 1; fetchDrugs() }"
              >
                <template #append>
                  <el-button :icon="Search" @click="() => { drugPage = 1; fetchDrugs() }" />
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
                <el-tag v-else-if="scope.row.variant_type === 'consumable'" type="info">耗材</el-tag>
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

          <div class="pagination" style="margin-top: 16px; text-align: right;">
            <el-pagination
              v-model:current-page="drugPage"
              v-model:page-size="drugPageSize"
              :total="drugTotal"
              layout="total, prev, pager, next"
              @current-change="handleDrugPageChange"
            />
          </div>
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

      <!-- 月度盘点标签页 -->
      <el-tab-pane label="月度盘点" name="monthly">
        <el-card>
          <template #header>
            <div class="card-header">
              <span>月度库存对比报表</span>
            </div>
          </template>

          <el-form :inline="true" class="monthly-form">
            <el-form-item label="起始日期">
              <el-date-picker 
                v-model="monthlyStartDate" 
                type="date" 
                placeholder="选择起始日期"
                value-format="YYYY-MM-DD"
              />
            </el-form-item>
            <el-form-item label="截止日期">
              <el-date-picker 
                v-model="monthlyEndDate" 
                type="date" 
                placeholder="选择截止日期"
                value-format="YYYY-MM-DD"
              />
            </el-form-item>
            <el-form-item>
              <el-button type="primary" @click="fetchMonthlyReport" :loading="monthlyLoading">
                生成报表
              </el-button>
              <el-button type="success" @click="exportMonthlyReport" :disabled="monthlyData.length === 0">
                导出Excel
              </el-button>
            </el-form-item>
          </el-form>

          <el-table :data="monthlyData" stripe style="width: 100%" v-loading="monthlyLoading" 
                    show-summary :summary-method="getMonthlySummaries">
            <el-table-column type="index" label="序号" width="60" />
            <el-table-column prop="storage_location" label="存放位置" width="90">
              <template #default="scope">{{ scope.row.storage_location || '-' }}</template>
            </el-table-column>
            <el-table-column prop="drug_name" label="名称" min-width="150" />
            <el-table-column label="类型" width="80">
              <template #default="scope">
                <el-tag v-if="scope.row.type === 3" type="info" size="small">耗材</el-tag>
                <el-tag v-else size="small">药品</el-tag>
              </template>
            </el-table-column>
            <el-table-column prop="specification" label="规格" width="120" />
            <el-table-column prop="purchase_price" label="购进价" width="90" />
            <el-table-column prop="unit" label="单位" width="80" />
            <el-table-column prop="opening_stock" label="上月盘点数" width="120" />
            <el-table-column prop="inbound" label="入库数" width="100" />
            <el-table-column prop="outbound" label="出库数" width="100" />
            <el-table-column prop="adjustment" label="盘点调整" width="100" />
            <el-table-column prop="closing_stock" label="现存数" width="100" />
            <el-table-column prop="inbound_amount" label="本月进药金额" width="120" />
            <el-table-column prop="current_stock_amount" label="现库存金额" width="120" />
          </el-table>
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

      <!-- 智能盘库结果弹窗 -->
      <el-dialog
        v-model="smartDialogVisible"
        title="智能盘库报告"
        width="800px"
        destroy-on-close
      >
        <!-- 筛选控制区域 -->
        <div style="margin-bottom: 16px;">
          <!-- 筛选类目勾选 -->
          <div style="margin-bottom: 12px; padding: 10px 14px; background: #f5f7fa; border-radius: 6px;">
            <span style="font-size: 14px; font-weight: 500; margin-right: 16px;">筛选类目：</span>
            <el-checkbox v-model="showStockWarnings" @change="onFilterCategoryChange">
              <span style="font-weight: 500;">📦 库存预警</span>
            </el-checkbox>
            <el-checkbox v-model="showExpiryWarnings" @change="onFilterCategoryChange" style="margin-left: 20px;">
              <span style="font-weight: 500;">⚠️ 有效期预警</span>
            </el-checkbox>
          </div>
          <!-- 库存预警参数 -->
          <div v-if="showStockWarnings" style="display: flex; flex-wrap: wrap; align-items: center; gap: 16px; margin-bottom: 8px;">
            <div style="display: flex; align-items: center; gap: 8px;">
              <span style="white-space: nowrap; font-size: 14px;">库存阈值：</span>
              <el-input-number 
                v-model="smartThreshold" 
                :min="1" 
                :max="9999" 
                size="default"
                style="width: 140px;"
              />
            </div>
            <el-checkbox v-model="smartScatteredOnly">仅显示含“散”类目</el-checkbox>
          </div>
          <!-- 有效期预警参数 -->
          <div v-if="showExpiryWarnings" style="display: flex; flex-wrap: wrap; align-items: center; gap: 16px; margin-bottom: 8px;">
            <div style="display: flex; align-items: center; gap: 8px;">
              <span style="white-space: nowrap; font-size: 14px;">有效期预警天数：</span>
              <el-input-number
                v-model="smartExpiryThreshold"
                :min="1"
                :max="365"
                size="default"
                style="width: 120px;"
              />
            </div>
          </div>
          <el-button type="primary" size="default" @click="handleSmartInventory" :disabled="!showStockWarnings && !showExpiryWarnings">
            重新筛选
          </el-button>
          <span v-if="!showStockWarnings && !showExpiryWarnings" style="margin-left: 8px; color: #E6A23C; font-size: 13px;">请至少勾选一个筛选类目</span>
        </div>
      
        <div v-if="smartResult">
          <el-alert
            :title="`本次盘库共合并 ${smartResult.merged_groups} 组重复项，清理了 ${smartResult.deleted_duplicates} 条冗余记录。`"
            type="success"
            show-icon
            :closable="false"
            style="margin-bottom: 16px"
          />
      
          <div v-if="showStockWarnings">
            <h3 style="margin: 0 0 12px 0; font-size: 15px;">📦 库存预警清单 (库存 &lt; {{ smartThreshold }})</h3>
            <el-table :data="smartResult.warnings" border stripe size="small" max-height="250" empty-text="无符合条件的预警物资">
              <el-table-column prop="name" label="名称" min-width="150" />
              <el-table-column prop="specification" label="规格" width="120" />
              <el-table-column prop="stock" label="当前库存" width="100" align="center">
                <template #default="scope">
                  <span style="color: #f56c6c; font-weight: bold">{{ scope.row.stock }}</span>
                </template>
              </el-table-column>
            </el-table>
            <div style="margin: 4px 0 16px; color: #909399; font-size: 13px;">
              共 {{ smartResult.warnings.length }} 种物资库存低于预警值
            </div>
          </div>
      
          <div v-if="showExpiryWarnings">
            <h3 style="margin: 0 0 12px 0; font-size: 15px; color: #E6A23C;">⚠️ 有效期预警清单 ({{ smartExpiryThreshold }} 天内到期)</h3>
            <el-table
              :data="smartResult.expiry_warnings"
              border
              stripe
              size="small"
              max-height="300"
              empty-text="无有效期预警物资"
              :row-class-name="({row}) => row.is_expired ? 'expired-row' : ''"
            >
              <el-table-column prop="name" label="名称" min-width="140" />
              <el-table-column prop="specification" label="规格" width="110" />
              <el-table-column label="有效期" width="120">
                <template #default="scope">{{ scope.row.expiry_date }}</template>
              </el-table-column>
              <el-table-column label="剩余天数" width="110" align="center">
                <template #default="scope">
                  <el-tag v-if="scope.row.is_expired" type="danger" size="small">已过期 {{ Math.abs(scope.row.days_remaining) }} 天</el-tag>
                  <el-tag v-else-if="scope.row.days_remaining === 0" type="danger" size="small">今天到期</el-tag>
                  <el-tag v-else-if="scope.row.days_remaining <= 7" type="danger" size="small">{{ scope.row.days_remaining }} 天</el-tag>
                  <el-tag v-else type="warning" size="small">{{ scope.row.days_remaining }} 天</el-tag>
                </template>
              </el-table-column>
              <el-table-column prop="stock" label="库存" width="80" align="center" />
              <el-table-column label="状态" width="90" align="center">
                <template #default="scope">
                  <el-tag v-if="scope.row.is_expired" type="danger" size="small">已过期</el-tag>
                  <el-tag v-else-if="scope.row.days_remaining <= 7" type="danger" size="small">紧急</el-tag>
                  <el-tag v-else-if="scope.row.days_remaining <= 30" type="warning" size="small">注意</el-tag>
                  <el-tag v-else type="info" size="small">正常</el-tag>
                </template>
              </el-table-column>
            </el-table>
            <div style="margin-top: 4px; color: #909399; font-size: 13px;">
              共 {{ (smartResult.expiry_warnings || []).length }} 种物资在 {{ smartExpiryThreshold }} 天内到期或已过期
            </div>
          </div>
        </div>
        <template #footer>
          <el-button @click="smartDialogVisible = false">关 闭</el-button>
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
import { Search, Cpu } from '@element-plus/icons-vue'
import { ElMessage, ElLoading } from 'element-plus'
import request from '@/api/request'

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
const drugPage = ref(1)
const drugPageSize = ref(20)
const drugTotal = ref(0)

// Monthly Report Tab
const monthlyStartDate = ref('')
const monthlyEndDate = ref('')
const monthlyData = ref([])
const monthlyLoading = ref(false)
// Smart Inventory
const smartDialogVisible = ref(false)
const smartResult = ref(null)
const smartThreshold = ref(30)
const smartScatteredOnly = ref(false)
const smartExpiryThreshold = ref(30)
const showStockWarnings = ref(true)
const showExpiryWarnings = ref(true)

const onFilterCategoryChange = () => {
  // 确保至少勾选一项时自动触发筛选
}

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
      params: {
        keyword: searchQuery.value,
        page: drugPage.value,
        size: drugPageSize.value
      }
    })
    drugs.value = res.data
    drugTotal.value = res.meta ? res.meta.total : 0
  } catch (error) {
    ElMessage.error('获取药品列表失败')
  } finally {
    loading.value = false
  }
}

const handleDrugPageChange = (val) => {
  drugPage.value = val
  fetchDrugs()
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

const handleSmartInventory = async () => {
  const loadingInstance = ElLoading.service({
    lock: true,
    text: '正在智能盘点库存，请稍候...',
    background: 'rgba(0, 0, 0, 0.7)',
  })
  try {
    const res = await request.post('/admin/drugs/smart-inventory', {
      threshold: smartThreshold.value,
      scattered_only: smartScatteredOnly.value,
      expiry_threshold: smartExpiryThreshold.value
    })
    smartResult.value = res.data?.data || res.data
    smartDialogVisible.value = true
  } catch (error) {
    ElMessage.error(error.msg || '智能盘库失败')
  } finally {
    loadingInstance.close()
  }
}

const fetchMonthlyReport = async () => {
  if (!monthlyStartDate.value || !monthlyEndDate.value) {
    ElMessage.warning('请选择起始日期和截止日期')
    return
  }
  monthlyLoading.value = true
  try {
    const res = await request.get('/nurse/inventory/monthly-report', {
      params: {
        start_date: monthlyStartDate.value,
        end_date: monthlyEndDate.value
      }
    })
    monthlyData.value = res.data || []
  } catch (error) {
    ElMessage.error('生成报表失败')
  } finally {
    monthlyLoading.value = false
  }
}

const exportMonthlyReport = () => {
  if (!monthlyStartDate.value || !monthlyEndDate.value) {
    ElMessage.warning('请选择日期范围')
    return
  }
  const token = localStorage.getItem('token')
  const url = `/api/nurse/inventory/monthly-report/export?start_date=${monthlyStartDate.value}&end_date=${monthlyEndDate.value}`
  
  fetch(url, {
    headers: { 'Authorization': `Bearer ${token}` }
  })
  .then(res => res.blob())
  .then(blob => {
    const link = document.createElement('a')
    link.href = URL.createObjectURL(blob)
    link.download = `月度盘点报表_${monthlyStartDate.value}_${monthlyEndDate.value}.xlsx`
    link.click()
    URL.revokeObjectURL(link.href)
  })
  .catch(() => ElMessage.error('导出失败'))
}

// 合计行方法
const getMonthlySummaries = ({ columns, data }) => {
  const sums = []
  columns.forEach((column, index) => {
    // 序号列（第一个无 prop 列）显示"合计"
    if (!column.property) {
      sums[index] = '合计'
      return
    }
    if (['opening_stock', 'inbound', 'outbound', 'adjustment', 'closing_stock', 'inbound_amount', 'current_stock_amount'].includes(column.property)) {
      sums[index] = data.reduce((sum, row) => sum + (Number(row[column.property]) || 0), 0)
    } else {
      sums[index] = ''
    }
  })
  return sums
}

watch(activeTab, (newTab) => {
  if (newTab === 'records') {
    fetchRecords()
  } else if (newTab === 'monthly') {
    // 月度盘点不自动加载，等用户点击"生成报表"
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

:deep(.expired-row) {
  background-color: #fef0f0 !important;
}
</style>
