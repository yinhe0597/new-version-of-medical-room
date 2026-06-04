<template>
  <div class="statistics-container">
    <el-card>
      <template #header>
        <div class="card-header">
          <span>药品出库报表</span>
          <div class="filter-box">
            <el-date-picker
              v-model="timeRange"
              type="datetimerange"
              format="YYYY-MM-DD HH:mm"
              value-format="YYYY-MM-DD HH:mm:ss"
              start-placeholder="开始时间"
              end-placeholder="结束时间"
              style="width: 360px"
              @change="fetchData"
            />

            <el-select
              v-model="doctorId"
              clearable
              filterable
              placeholder="接诊医生"
              style="margin-left: 10px; width: 160px"
              @change="fetchData"
            >
              <el-option v-for="u in doctors" :key="u.id" :label="u.real_name" :value="u.id" />
            </el-select>

            <el-select
              v-model="nurseId"
              clearable
              filterable
              placeholder="开药护士"
              style="margin-left: 10px; width: 160px"
              @change="fetchData"
            >
              <el-option v-for="u in nurses" :key="u.id" :label="u.real_name" :value="u.id" />
            </el-select>

            <el-input
              v-model="keyword"
              clearable
              placeholder="药品名称/规格关键字"
              style="margin-left: 10px; width: 220px"
              @keyup.enter="fetchData"
            />

            <el-button type="primary" style="margin-left: 10px" @click="fetchData" :loading="loading">查询</el-button>
            <el-button type="success" :icon="Download" style="margin-left: 10px" @click="exportExcel">导出Excel</el-button>
          </div>
        </div>
      </template>

      <el-alert
        type="info"
        show-icon
        :closable="false"
        style="margin-bottom: 12px;"
        title="说明：本报表按已结算的就诊记录统计（已生成 Payment）。仅统计护士执行发药/收款后产生的药品出库；未结算/未执行的处方不计入。"
      />

      <el-row :gutter="20" class="summary-cards">
        <el-col :span="8">
          <el-card shadow="hover" class="bg-blue">
            <div class="stat-item">
              <div class="label">出库记录数</div>
              <div class="value">{{ summary.total_records }}</div>
            </div>
          </el-card>
        </el-col>
        <el-col :span="8">
          <el-card shadow="hover" class="bg-green">
            <div class="stat-item">
              <div class="label">合计数量</div>
              <div class="value">{{ summary.total_quantity }}</div>
            </div>
          </el-card>
        </el-col>
        <el-col :span="8">
          <el-card shadow="hover" class="bg-orange">
            <div class="stat-item">
              <div class="label">合计金额</div>
              <div class="value">¥ {{ summary.total_amount.toFixed(2) }}</div>
            </div>
          </el-card>
        </el-col>
      </el-row>

      <el-divider content-position="left">明细数据</el-divider>

      <el-table :data="details" stripe style="width: 100%" height="460" v-loading="loading">
        <el-table-column prop="date" label="出库时间" width="170" />
        <el-table-column prop="visit_id" label="就诊ID" width="90" />
        <el-table-column label="患者" width="120">
          <template #default="scope">{{ maskName(scope.row.patient_name) }}</template>
        </el-table-column>
        <el-table-column prop="doctor_name" label="接诊医生" width="110" />
        <el-table-column prop="nurse_name" label="开药护士" width="110" />
        <el-table-column prop="drug_name" label="药品名称" min-width="160" show-overflow-tooltip />
        <el-table-column prop="specification" label="规格" width="140" show-overflow-tooltip />
        <el-table-column prop="is_scattered" label="零散" width="70">
          <template #default="scope">
            <el-tag :type="scope.row.is_scattered ? 'warning' : 'info'">{{ scope.row.is_scattered ? '是' : '否' }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="quantity" label="数量" width="80" />
        <el-table-column prop="unit" label="单位" width="70" />
        <el-table-column prop="price_at_visit" label="单价" width="90">
          <template #default="scope">¥ {{ (scope.row.price_at_visit || 0).toFixed(2) }}</template>
        </el-table-column>
        <el-table-column prop="amount" label="金额" width="100">
          <template #default="scope">¥ {{ (scope.row.amount || 0).toFixed(2) }}</template>
        </el-table-column>
        <el-table-column prop="payment_method" label="支付方式" width="100" />
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
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import request from '@/api/request'
import { Download } from '@element-plus/icons-vue'
import dayjs from 'dayjs'
import { ElMessage } from 'element-plus'
import { useUserStore } from '@/store/user'

const userStore = useUserStore()
const isFinance = computed(() => userStore.userInfo?.role === 'finance')

const maskName = (name) => {
  if (!name || !isFinance.value) return name || '-'
  if (name.length <= 1) return name
  return name[0] + '*'.repeat(name.length - 1)
}

const loading = ref(false)
const timeRange = ref([
  dayjs().startOf('day').format('YYYY-MM-DD HH:mm:ss'),
  dayjs().endOf('day').format('YYYY-MM-DD HH:mm:ss')
])
const doctorId = ref()
const nurseId = ref()
const keyword = ref('')

const doctors = ref([])
const nurses = ref([])

const page = ref(1)
const pageSize = ref(50)
const total = ref(0)

const summary = ref({
  total_records: 0,
  total_quantity: 0,
  total_amount: 0
})
const details = ref([])

const fetchUsers = async () => {
  try {
    const res = await request.get('/admin/statistics/revenue/users')
    doctors.value = (res.data?.doctors || [])
    nurses.value = (res.data?.nurses || [])
  } catch (error) {
    return
  }
}

const fetchData = async () => {
  if (!Array.isArray(timeRange.value) || timeRange.value.length !== 2) return
  loading.value = true
  try {
    const res = await request.get('/admin/statistics/drug-outbound', {
      params: {
        start_time: timeRange.value[0],
        end_time: timeRange.value[1],
        doctor_id: doctorId.value,
        nurse_id: nurseId.value,
        keyword: keyword.value.trim(),
        page: page.value,
        size: pageSize.value
      }
    })
    summary.value = res.data.summary
    details.value = res.data.details
    total.value = res.data.meta.total
  } catch (error) {
    ElMessage.error(error.msg || '加载失败')
  } finally {
    loading.value = false
  }
}

const handlePageChange = (val) => {
  page.value = val
  fetchData()
}

const exportExcel = async () => {
  if (!Array.isArray(timeRange.value) || timeRange.value.length !== 2) return
  try {
    const blob = await request.get('/admin/statistics/drug-outbound/export', {
      params: {
        start_time: timeRange.value[0],
        end_time: timeRange.value[1],
        doctor_id: doctorId.value,
        nurse_id: nurseId.value,
        keyword: keyword.value.trim()
      },
      responseType: 'blob'
    })
    const filename = `drug_outbound_${dayjs(timeRange.value[0]).format('YYYYMMDDHHmm')}_${dayjs(timeRange.value[1]).format('YYYYMMDDHHmm')}.xlsx`
    const url = window.URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = filename
    document.body.appendChild(a)
    a.click()
    a.remove()
    window.URL.revokeObjectURL(url)
  } catch (error) {
    ElMessage.error(error.msg || '导出失败')
  }
}

onMounted(() => {
  fetchUsers()
  fetchData()
})
</script>

<style scoped>
.statistics-container {
  padding: 20px;
}
.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.filter-box {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
}
.summary-cards {
  margin-bottom: 20px;
}
.stat-item {
  text-align: center;
}
.label {
  font-size: 14px;
  color: #606266;
  margin-bottom: 10px;
}
.value {
  font-size: 24px;
  font-weight: bold;
  color: #303133;
}
.bg-blue {
  background-color: #ecf5ff;
}
.bg-green {
  background-color: #f0f9eb;
}
.bg-orange {
  background-color: #fdf6ec;
  color: #e6a23c;
}
.pagination {
  margin-top: 16px;
  display: flex;
  justify-content: flex-end;
}
</style>
