<template>
  <div class="statistics-container">
    <el-card>
      <template #header>
        <div class="card-header">
          <span>营收统计报表</span>
          <div class="filter-box">
            <el-radio-group v-model="statsType" size="small" @change="handleTypeChange">
              <el-radio-button label="daily">日报</el-radio-button>
              <el-radio-button label="monthly">月报</el-radio-button>
              <el-radio-button label="yearly">年报</el-radio-button>
            </el-radio-group>
            
            <el-date-picker
              v-model="timeRange"
              type="datetimerange"
              format="YYYY-MM-DD HH:mm"
              value-format="YYYY-MM-DD HH:mm:ss"
              start-placeholder="开始时间"
              end-placeholder="结束时间"
              style="margin-left: 10px; width: 360px"
              @change="fetchStats"
            />

            <el-select
              v-model="doctorId"
              clearable
              filterable
              placeholder="接诊医生"
              style="margin-left: 10px; width: 160px"
              @change="fetchStats"
            >
              <el-option v-for="u in doctors" :key="u.id" :label="u.real_name" :value="u.id" />
            </el-select>

            <el-select
              v-model="nurseId"
              clearable
              filterable
              placeholder="开药护士"
              style="margin-left: 10px; width: 160px"
              @change="fetchStats"
            >
              <el-option v-for="u in nurses" :key="u.id" :label="u.real_name" :value="u.id" />
            </el-select>
            
            <el-button type="success" :icon="Download" style="margin-left: 10px" @click="exportExcel">导出Excel</el-button>
          </div>
        </div>
      </template>

      <el-row :gutter="20" class="summary-cards">
        <el-col :span="4">
          <el-card shadow="hover" class="bg-blue">
            <div class="stat-item">
              <div class="label">总收入</div>
              <div class="value">¥ {{ stats.total_revenue.toFixed(2) }}</div>
            </div>
          </el-card>
        </el-col>
        <el-col :span="4">
          <el-card shadow="hover" class="bg-green">
            <div class="stat-item">
              <div class="label">药品收入</div>
              <div class="value">¥ {{ stats.drug_revenue.toFixed(2) }}</div>
            </div>
          </el-card>
        </el-col>
        <el-col :span="4">
          <el-card shadow="hover" class="bg-teal">
            <div class="stat-item">
              <div class="label">诊疗项目收入</div>
              <div class="value">¥ {{ (stats.service_revenue || 0).toFixed(2) }}</div>
            </div>
          </el-card>
        </el-col>
        <el-col :span="4">
          <el-card shadow="hover" class="bg-cyan">
            <div class="stat-item">
              <div class="label">耗材收入</div>
              <div class="value">¥ {{ (stats.consumable_revenue || 0).toFixed(2) }}</div>
            </div>
          </el-card>
        </el-col>
        <el-col :span="4">
          <el-card shadow="hover" class="bg-orange">
            <div class="stat-item">
              <div class="label">诊察费收入</div>
              <div class="value">¥ {{ stats.consultation_revenue.toFixed(2) }}</div>
            </div>
          </el-card>
        </el-col>
        <el-col :span="4">
          <el-card shadow="hover" class="bg-gray">
            <div class="stat-item">
              <div class="label">总成本</div>
              <div class="value">¥ {{ (stats.total_cost || 0).toFixed(2) }}</div>
            </div>
          </el-card>
        </el-col>
        <el-col :span="4">
          <el-card shadow="hover" class="bg-purple">
            <div class="stat-item">
              <div class="label">总利润</div>
              <div class="value">¥ {{ stats.total_profit ? stats.total_profit.toFixed(2) : '0.00' }}</div>
            </div>
          </el-card>
        </el-col>
      </el-row>

      <el-divider content-position="left">明细数据</el-divider>

      <el-table :data="stats.details" stripe style="width: 100%" height="400">
        <el-table-column prop="date" label="时间" width="170" />
        <el-table-column prop="visit_id" label="就诊ID" width="90" />
        <el-table-column prop="patient_name" label="患者" width="120" />
        <el-table-column prop="diagnosis" label="诊断" min-width="200" show-overflow-tooltip />
        <el-table-column prop="doctor_name" label="接诊医生" width="110" />
        <el-table-column prop="nurse_name" label="开药护士" width="110" />
        <el-table-column prop="drug_amount" label="药品" width="100">
          <template #default="scope">¥ {{ (scope.row.drug_amount || 0).toFixed(2) }}</template>
        </el-table-column>
        <el-table-column prop="service_amount" label="诊疗项目" width="110">
          <template #default="scope">¥ {{ (scope.row.service_amount || 0).toFixed(2) }}</template>
        </el-table-column>
        <el-table-column prop="consumable_amount" label="耗材" width="100">
          <template #default="scope">¥ {{ (scope.row.consumable_amount || 0).toFixed(2) }}</template>
        </el-table-column>
        <el-table-column prop="consultation_fee" label="诊察费" width="100">
          <template #default="scope">¥ {{ (scope.row.consultation_fee || 0).toFixed(2) }}</template>
        </el-table-column>
        <el-table-column prop="amount" label="总金额" width="110">
          <template #default="scope">¥ {{ (scope.row.amount || 0).toFixed(2) }}</template>
        </el-table-column>
        <el-table-column prop="cost" label="成本" width="100">
          <template #default="scope">¥ {{ (scope.row.cost || 0).toFixed(2) }}</template>
        </el-table-column>
        <el-table-column prop="profit" label="利润" width="110">
          <template #default="scope">¥ {{ (scope.row.profit || 0).toFixed(2) }}</template>
        </el-table-column>
      </el-table>
    </el-card>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import request from '@/api/request'
import { Download } from '@element-plus/icons-vue'
import dayjs from 'dayjs'
import { ElMessage } from 'element-plus'

const statsType = ref('daily')
const timeRange = ref([
  dayjs().startOf('day').format('YYYY-MM-DD HH:mm:ss'),
  dayjs().endOf('day').format('YYYY-MM-DD HH:mm:ss')
])
const doctorId = ref()
const nurseId = ref()
const doctors = ref([])
const nurses = ref([])
const stats = ref({
  total_revenue: 0,
  drug_revenue: 0,
  service_revenue: 0,
  consultation_revenue: 0,
  consumable_revenue: 0,
  total_cost: 0,
  total_profit: 0,
  details: []
})

const handleTypeChange = () => {
  if (statsType.value === 'daily') {
    timeRange.value = [
      dayjs().startOf('day').format('YYYY-MM-DD HH:mm:ss'),
      dayjs().endOf('day').format('YYYY-MM-DD HH:mm:ss')
    ]
  } else if (statsType.value === 'monthly') {
    timeRange.value = [
      dayjs().startOf('month').format('YYYY-MM-DD HH:mm:ss'),
      dayjs().endOf('month').format('YYYY-MM-DD HH:mm:ss')
    ]
  } else {
    timeRange.value = [
      dayjs().startOf('year').format('YYYY-MM-DD HH:mm:ss'),
      dayjs().endOf('year').format('YYYY-MM-DD HH:mm:ss')
    ]
  }
  fetchStats()
}

const fetchUsers = async () => {
  try {
    const res = await request.get('/admin/statistics/revenue/users')
    doctors.value = (res.data?.doctors || [])
    nurses.value = (res.data?.nurses || [])
  } catch (error) {
    return
  }
}

const fetchStats = async () => {
  if (!Array.isArray(timeRange.value) || timeRange.value.length !== 2) return
  try {
    const res = await request.get('/admin/statistics/revenue', {
      params: {
        type: statsType.value,
        start_time: timeRange.value[0],
        end_time: timeRange.value[1],
        doctor_id: doctorId.value,
        nurse_id: nurseId.value
      }
    })
    stats.value = res.data
  } catch (error) {
    console.error(error)
  }
}

const exportExcel = async () => {
  if (!Array.isArray(timeRange.value) || timeRange.value.length !== 2) return
  try {
    const blob = await request.get('/admin/statistics/revenue/export', {
      params: {
        type: statsType.value,
        start_time: timeRange.value[0],
        end_time: timeRange.value[1],
        doctor_id: doctorId.value,
        nurse_id: nurseId.value
      },
      responseType: 'blob'
    })
    const filename = `revenue_${statsType.value}_${dayjs(timeRange.value[0]).format('YYYYMMDDHHmm')}_${dayjs(timeRange.value[1]).format('YYYYMMDDHHmm')}.xlsx`
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
  fetchStats()
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
.bg-purple {
  background-color: #f3e8ff;
  color: #b3261e;
}
.bg-teal {
  background-color: #e8f7f4;
  color: #0f766e;
}
.bg-cyan {
  background-color: #e0f7fa;
  color: #00838f;
}
.bg-gray {
  background-color: #f5f7fa;
  color: #606266;
}
</style>
