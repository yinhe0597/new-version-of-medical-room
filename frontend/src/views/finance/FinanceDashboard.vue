<template>
  <div class="finance-dashboard">
    <!-- 顶部摘要卡片 -->
    <el-row :gutter="20" class="summary-row">
      <el-col :span="6">
        <el-card shadow="hover" class="summary-card card-today">
          <div class="card-stat">
            <div class="card-label">今日营收</div>
            <div class="card-value">¥ {{ summary.today_revenue.toFixed(2) }}</div>
          </div>
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card shadow="hover" class="summary-card card-month">
          <div class="card-stat">
            <div class="card-label">本月营收</div>
            <div class="card-value">¥ {{ summary.month_revenue.toFixed(2) }}</div>
          </div>
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card shadow="hover" class="summary-card card-cost">
          <div class="card-stat">
            <div class="card-label">本月成本</div>
            <div class="card-value">¥ {{ summary.month_cost.toFixed(2) }}</div>
          </div>
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card shadow="hover" class="summary-card card-profit">
          <div class="card-stat">
            <div class="card-label">本月利润</div>
            <div class="card-value">¥ {{ summary.month_profit.toFixed(2) }}</div>
          </div>
        </el-card>
      </el-col>
    </el-row>

    <el-row :gutter="20" class="summary-row">
      <el-col :span="6">
        <el-card shadow="hover" class="summary-card card-visit">
          <div class="card-stat">
            <div class="card-label">本月就诊人次</div>
            <div class="card-value">{{ summary.month_visit_count }}</div>
          </div>
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card shadow="hover" class="summary-card card-growth">
          <div class="card-stat">
            <div class="card-label">环比上月增长率</div>
            <div class="card-value" :class="summary.growth_rate >= 0 ? 'green' : 'red'">
              {{ summary.growth_rate >= 0 ? '+' : '' }}{{ summary.growth_rate }}%
            </div>
          </div>
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card shadow="hover" class="summary-card card-prev">
          <div class="card-stat">
            <div class="card-label">上月营收</div>
            <div class="card-value">¥ {{ summary.prev_month_revenue.toFixed(2) }}</div>
          </div>
        </el-card>
      </el-col>
    </el-row>

    <!-- 图表区域 -->
    <el-row :gutter="20">
      <el-col :span="16">
        <el-card shadow="hover">
          <template #header>
            <span>近30天营收趋势</span>
          </template>
          <div ref="trendChartRef" style="height: 350px;"></div>
        </el-card>
      </el-col>
      <el-col :span="8">
        <el-card shadow="hover">
          <template #header>
            <span>收入类型占比</span>
          </template>
          <div ref="pieChartRef" style="height: 350px;"></div>
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>

<script setup>
import { ref, onMounted, onUnmounted, nextTick } from 'vue'
import request from '@/api/request'
import { ElMessage } from 'element-plus'

const summary = ref({
  today_revenue: 0,
  month_revenue: 0,
  month_cost: 0,
  month_profit: 0,
  prev_month_revenue: 0,
  growth_rate: 0,
  month_visit_count: 0,
})

const trendChartRef = ref(null)
const pieChartRef = ref(null)
let trendChart = null
let pieChart = null

const fetchSummary = async () => {
  try {
    const res = await request.get('/finance/dashboard/summary')
    summary.value = res.data
  } catch (error) {
    ElMessage.error('获取财务摘要失败')
  }
}

const renderTrendChart = (data) => {
  if (!trendChartRef.value) return
  const echarts = window.echarts
  if (!echarts) return

  if (!trendChart) {
    trendChart = echarts.init(trendChartRef.value)
  }

  trendChart.setOption({
    tooltip: {
      trigger: 'axis',
      formatter: function(params) {
        let html = `<div style="font-weight:bold;margin-bottom:4px;">${params[0].axisValue}</div>`
        params.forEach(p => {
          html += `<div><span style="display:inline-block;width:10px;height:10px;border-radius:50%;background:${p.color};margin-right:6px;"></span>${p.seriesName}: ¥${p.value.toFixed(2)}</div>`
        })
        return html
      }
    },
    legend: { data: ['营收', '成本', '利润'], top: 0 },
    grid: { left: '3%', right: '4%', bottom: '3%', containLabel: true },
    xAxis: { type: 'category', data: data.map(d => d.date.slice(5)), axisLabel: { rotate: 45 } },
    yAxis: { type: 'value', axisLabel: { formatter: '¥{value}' } },
    series: [
      {
        name: '营收',
        type: 'line',
        smooth: true,
        data: data.map(d => d.revenue),
        itemStyle: { color: '#409eff' },
        areaStyle: { color: 'rgba(64,158,255,0.1)' },
      },
      {
        name: '成本',
        type: 'line',
        smooth: true,
        data: data.map(d => d.cost),
        itemStyle: { color: '#f56c6c' },
        areaStyle: { color: 'rgba(245,108,108,0.1)' },
      },
      {
        name: '利润',
        type: 'line',
        smooth: true,
        data: data.map(d => d.profit),
        itemStyle: { color: '#67c23a' },
        areaStyle: { color: 'rgba(103,194,58,0.1)' },
      },
    ]
  })
}

const fetchTrend = async () => {
  try {
    const res = await request.get('/finance/profit-trend', { params: { days: 30 } })
    await nextTick()
    renderTrendChart(res.data)
  } catch (error) {
    // ignore
  }
}

const renderPieChart = (data) => {
  if (!pieChartRef.value) return
  const echarts = window.echarts
  if (!echarts) return

  if (!pieChart) {
    pieChart = echarts.init(pieChartRef.value)
  }

  const items = [
    { name: '药品收入', value: data.drug_revenue },
    { name: '诊疗项目', value: data.service_revenue },
    { name: '耗材收入', value: data.consumable_revenue },
    { name: '诊察费', value: data.consultation_revenue },
  ].filter(item => item.value > 0)

  pieChart.setOption({
    tooltip: {
      formatter: function(params) {
        return `${params.name}: ¥${params.value.toFixed(2)} (${params.percent}%)`
      }
    },
    series: [
      {
        type: 'pie',
        radius: ['40%', '70%'],
        center: ['50%', '50%'],
        data: items,
        label: {
          formatter: function(params) {
            return `${params.name}\n¥${params.value.toFixed(0)}`
          }
        },
        emphasis: {
          itemStyle: {
            shadowBlur: 10,
            shadowOffsetX: 0,
            shadowColor: 'rgba(0,0,0,0.5)'
          }
        }
      }
    ]
  })
}

const fetchRevenueByType = async () => {
  try {
    const res = await request.get('/finance/revenue/by-type', { params: { start_time: '', end_time: '' } })
    await nextTick()
    renderPieChart(res.data)
  } catch (error) {
    // ignore
  }
}

const handleResize = () => {
  if (trendChart) trendChart.resize()
  if (pieChart) pieChart.resize()
}

onMounted(() => {
  // 尝试加载 echarts（如果未全局注册则跳过图表渲染）
  fetchSummary()
  fetchTrend()
  fetchRevenueByType()
  window.addEventListener('resize', handleResize)

  // 如果没有全局 echarts，则动态加载
  if (!window.echarts) {
    const script = document.createElement('script')
    script.src = 'https://cdn.jsdelivr.net/npm/echarts@5/dist/echarts.min.js'
    script.onload = () => {
      fetchTrend()
      fetchRevenueByType()
    }
    document.head.appendChild(script)
  }
})

onUnmounted(() => {
  window.removeEventListener('resize', handleResize)
  if (trendChart) { trendChart.dispose(); trendChart = null }
  if (pieChart) { pieChart.dispose(); pieChart = null }
})
</script>

<style scoped>
.finance-dashboard {
  padding: 20px;
}
.summary-row {
  margin-bottom: 20px;
}
.summary-card {
  text-align: center;
}
.card-stat {
  padding: 10px 0;
}
.card-label {
  font-size: 14px;
  color: #606266;
  margin-bottom: 8px;
}
.card-value {
  font-size: 26px;
  font-weight: bold;
  color: #303133;
}
.card-value.green { color: #67c23a; }
.card-value.red { color: #f56c6c; }
.card-today { background: linear-gradient(135deg, #ecf5ff, #d9ecff); }
.card-month { background: linear-gradient(135deg, #f0f9eb, #e1f3d8); }
.card-cost { background: linear-gradient(135deg, #fef0f0, #fde2e2); }
.card-profit { background: linear-gradient(135deg, #f3e8ff, #e8d5ff); }
.card-visit { background: linear-gradient(135deg, #e8f7f4, #d0efe9); }
.card-growth { background: linear-gradient(135deg, #fdf6ec, #fce8d0); }
.card-prev { background: linear-gradient(135deg, #f5f7fa, #e8ecf1); }
</style>
