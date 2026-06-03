<template>
  <div class="operation-log-container">
    <el-card>
      <template #header>
        <div class="card-header">
          <span>运营日志</span>
        </div>
      </template>

      <!-- 筛选栏 -->
      <el-form :inline="true" class="filter-form">
        <el-form-item label="操作类型">
          <el-select v-model="filters.action_type" clearable placeholder="全部" style="width: 200px">
            <el-option label="修改病历" value="visit_edit" />
            <el-option label="新增药品/项目" value="drug_create" />
            <el-option label="编辑药品/项目" value="drug_update" />
            <el-option label="临时就诊" value="temp_patient_visit" />
            <el-option label="新增人员" value="create_patient" />
            <el-option label="护士审核通过" value="nurse_verify" />
            <el-option label="护士驳回" value="nurse_reject" />
            <el-option label="护士执行收费" value="nurse_execute" />
            <el-option label="护士撤销交易" value="nurse_revoke" />
            <el-option label="护士改价" value="nurse_modify_price" />
            <el-option label="护士新增项目/耗材" value="nurse_add_service" />
            <el-option label="护士库存调整" value="nurse_inventory_adjust" />
            <el-option label="药品入库" value="nurse_inbound" />
            <el-option label="导入数据" value="import_data" />
            <el-option label="数据库备份" value="backup" />
          </el-select>
        </el-form-item>
        <el-form-item label="开始日期">
          <el-date-picker
            v-model="filters.start_date"
            type="date"
            value-format="YYYY-MM-DD"
            placeholder="开始日期"
            style="width: 160px"
          />
        </el-form-item>
        <el-form-item label="结束日期">
          <el-date-picker
            v-model="filters.end_date"
            type="date"
            value-format="YYYY-MM-DD"
            placeholder="结束日期"
            style="width: 160px"
          />
        </el-form-item>
        <el-form-item>
          <el-button type="primary" @click="handleQuery">查询</el-button>
        </el-form-item>
      </el-form>

      <!-- 表格 -->
      <el-table :data="tableData" v-loading="loading" stripe border style="width: 100%">
        <el-table-column type="expand">
          <template #default="{ row }">
            <div class="expand-content">
              <template v-if="row.action_type === 'visit_edit' && parsedChanges(row)">
                <div v-for="(change, idx) in parsedChanges(row)" :key="idx" class="change-item">
                  <span class="field-name">{{ change.field }}：</span>
                  <span class="old-value">{{ change.old_value }}</span>
                  <span class="arrow"> → </span>
                  <span class="new-value">{{ change.new_value }}</span>
                </div>
              </template>
              <template v-else>
                <pre class="detail-pre">{{ formatDetails(row.details) }}</pre>
              </template>
            </div>
          </template>
        </el-table-column>
        <el-table-column label="操作时间" prop="timestamp" width="180" />
        <el-table-column label="操作人" prop="user_name" width="120" />
        <el-table-column label="角色" width="100">
          <template #default="{ row }">
            {{ roleMap[row.user_role] || row.user_role }}
          </template>
        </el-table-column>
        <el-table-column label="操作类型" width="130">
          <template #default="{ row }">
            <el-tag :type="actionTagType(row.action_type)">{{ actionLabel(row.action_type) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="摘要说明" prop="summary" min-width="200" show-overflow-tooltip />
      </el-table>

      <!-- 分页 -->
      <div class="pagination-wrapper">
        <el-pagination
          v-model:current-page="pagination.page"
          v-model:page-size="pagination.size"
          :total="pagination.total"
          :page-sizes="[20, 50, 100]"
          layout="total, sizes, prev, pager, next, jumper"
          @size-change="fetchData"
          @current-change="fetchData"
        />
      </div>
    </el-card>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import request from '@/api/request'

const loading = ref(false)
const tableData = ref([])

const filters = reactive({
  action_type: '',
  start_date: '',
  end_date: ''
})

const pagination = reactive({
  page: 1,
  size: 20,
  total: 0
})

const roleMap = {
  admin: '管理员',
  doctor: '医生',
  nurse: '护士',
  finance: '财务'
}

const actionTypeMap = {
  visit_edit: { label: '修改病历', type: '' },
  drug_create: { label: '新增药品/项目', type: 'success' },
  drug_update: { label: '编辑药品/项目', type: 'success' },
  temp_patient_visit: { label: '临时就诊', type: 'warning' },
  create_patient: { label: '新增人员', type: '' },
  nurse_verify: { label: '护士审核通过', type: 'primary' },
  nurse_reject: { label: '护士驳回', type: 'danger' },
  nurse_execute: { label: '护士执行收费', type: 'success' },
  nurse_revoke: { label: '护士撤销交易', type: 'danger' },
  nurse_modify_price: { label: '护士改价', type: 'warning' },
  nurse_add_service: { label: '护士新增项目', type: 'primary' },
  nurse_inventory_adjust: { label: '库存调整', type: 'warning' },
  nurse_inbound: { label: '药品入库', type: 'success' },
  import_data: { label: '导入数据', type: '' },
  backup: { label: '数据库备份', type: '' }
}

const actionLabel = (type) => actionTypeMap[type]?.label || type
const actionTagType = (type) => actionTypeMap[type]?.type || 'info'

const parsedChanges = (row) => {
  try {
    const details = typeof row.details === 'string' ? JSON.parse(row.details) : row.details
    if (!details || !details.changes) return null

    const changes = details.changes
    // changes 是对象: {"chief_complaint": {"old": "...", "new": "..."}}
    if (typeof changes === 'object' && !Array.isArray(changes)) {
      return Object.entries(changes).map(([field, vals]) => ({
        field: fieldNames[field] || field,
        old_value: vals.old || '',
        new_value: vals.new || ''
      }))
    }
    return null
  } catch {
    return null
  }
}

const fieldNames = {
  chief_complaint: '主诉',
  present_illness: '现病史',
  past_history: '既往史',
  physical_exam: '体格检查',
  doctor_advice: '医生留言',
  special_note: '特殊备注'
}

const formatDetails = (details) => {
  if (!details) return '无详细信息'
  try {
    const obj = typeof details === 'string' ? JSON.parse(details) : details
    return JSON.stringify(obj, null, 2)
  } catch {
    return String(details)
  }
}

const fetchData = async () => {
  loading.value = true
  try {
    const params = {
      page: pagination.page,
      size: pagination.size
    }
    if (filters.action_type) params.action_type = filters.action_type
    if (filters.start_date) params.start_date = filters.start_date
    if (filters.end_date) params.end_date = filters.end_date

    const res = await request.get('/admin/operation-logs', { params })
    // 后端返回格式: {"data": [...], "meta": {...}}, axiox 解包后 res = 整个 body
    tableData.value = res.data || []
    pagination.total = res.meta?.total || 0
  } catch (err) {
    ElMessage.error(err.msg || '获取运营日志失败')
  } finally {
    loading.value = false
  }
}

const handleQuery = () => {
  pagination.page = 1
  fetchData()
}

onMounted(() => {
  fetchData()
})
</script>

<style scoped>
.operation-log-container {
  padding: 20px;
}
.card-header {
  display: flex;
  align-items: center;
  font-size: 16px;
  font-weight: bold;
}
.filter-form {
  margin-bottom: 16px;
}
.pagination-wrapper {
  margin-top: 16px;
  display: flex;
  justify-content: flex-end;
}
.expand-content {
  padding: 12px 20px;
}
.change-item {
  line-height: 2;
}
.field-name {
  font-weight: bold;
  color: #303133;
}
.old-value {
  color: #f56c6c;
  text-decoration: line-through;
}
.arrow {
  color: #909399;
  margin: 0 4px;
}
.new-value {
  color: #67c23a;
}
.detail-pre {
  white-space: pre-wrap;
  word-break: break-all;
  margin: 0;
  font-size: 13px;
  color: #606266;
}
</style>
