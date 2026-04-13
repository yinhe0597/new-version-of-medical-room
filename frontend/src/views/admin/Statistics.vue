<template>
  <div class="statistics-container">
    <el-card>
      <template #header>
        <div class="card-header">
          <span>营收统计报表</span>
          <div class="filter-box">
            <el-radio-group v-model="statsType" size="small" @change="fetchStats">
              <el-radio-button label="daily">日报</el-radio-button>
              <el-radio-button label="monthly">月报</el-radio-button>
              <el-radio-button label="yearly">年报</el-radio-button>
            </el-radio-group>
            
            <el-date-picker
              v-model="date"
              :type="pickerType"
              :format="dateFormat"
              :value-format="valueFormat"
              placeholder="选择日期"
              style="margin-left: 10px; width: 200px"
              @change="fetchStats"
            />
            
            <el-button type="success" :icon="Download" style="margin-left: 10px">导出Excel</el-button>
          </div>
        </div>
      </template>

      <el-row :gutter="20" class="summary-cards">
        <el-col :span="6">
          <el-card shadow="hover" class="bg-blue">
            <div class="stat-item">
              <div class="label">总收入</div>
              <div class="value">¥ {{ stats.total_revenue.toFixed(2) }}</div>
            </div>
          </el-card>
        </el-col>
        <el-col :span="6">
          <el-card shadow="hover" class="bg-green">
            <div class="stat-item">
              <div class="label">药品收入</div>
              <div class="value">¥ {{ stats.drug_revenue.toFixed(2) }}</div>
            </div>
          </el-card>
        </el-col>
        <el-col :span="6">
          <el-card shadow="hover" class="bg-orange">
            <div class="stat-item">
              <div class="label">诊察费收入</div>
              <div class="value">¥ {{ stats.consultation_revenue.toFixed(2) }}</div>
            </div>
          </el-card>
        </el-col>
        <el-col :span="6">
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
        <el-table-column prop="date" label="时间" width="180" />
        <el-table-column prop="visit_id" label="就诊ID" width="100" />
        <el-table-column prop="amount" label="总金额">
          <template #default="scope">
            ¥ {{ scope.row.amount.toFixed(2) }}
          </template>
        </el-table-column>
        <el-table-column prop="profit" label="利润">
          <template #default="scope">
            ¥ {{ scope.row.profit ? scope.row.profit.toFixed(2) : '0.00' }}
          </template>
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

const statsType = ref('daily')
const date = ref(dayjs().format('YYYY-MM-DD'))
const stats = ref({
  total_revenue: 0,
  drug_revenue: 0,
  consultation_revenue: 0,
  details: []
})

const pickerType = computed(() => {
  if (statsType.value === 'daily') return 'date'
  if (statsType.value === 'monthly') return 'month'
  return 'year'
})

const dateFormat = computed(() => {
  if (statsType.value === 'daily') return 'YYYY-MM-DD'
  if (statsType.value === 'monthly') return 'YYYY-MM'
  return 'YYYY'
})

const valueFormat = computed(() => {
  if (statsType.value === 'daily') return 'YYYY-MM-DD'
  if (statsType.value === 'monthly') return 'YYYY-MM'
  return 'YYYY'
})

const fetchStats = async () => {
  if (!date.value) return
  try {
    const res = await request.get('/admin/statistics/revenue', {
      params: {
        type: statsType.value,
        date: date.value
      }
    })
    stats.value = res.data
  } catch (error) {
    console.error(error)
  }
}

onMounted(() => {
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
</style>
