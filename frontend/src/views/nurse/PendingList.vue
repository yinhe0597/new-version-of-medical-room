<template>
  <div class="pending-list-container">
    <el-card>
      <template #header>
        <div class="card-header">
          <span>待处置处方列表</span>
          <el-button type="primary" :icon="Refresh" circle @click="fetchPendingVisits" />
        </div>
      </template>
      
      <el-table :data="pendingList" v-loading="loading" stripe style="width: 100%">
        <el-table-column prop="created_at" label="开方时间" width="180" />
        <el-table-column prop="patient_name" label="患者姓名" width="120" />
        <el-table-column prop="student_id" label="学号/工号" width="150" />
        <el-table-column prop="total_amount" label="总金额" width="120">
          <template #default="scope">
            ¥ {{ scope.row.total_amount.toFixed(2) }}
          </template>
        </el-table-column>
        <el-table-column label="操作" width="150">
          <template #default="scope">
            <el-button type="primary" size="small" @click="handleExecute(scope.row.visit_id)">
              抓药结算
            </el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import request from '@/api/request'
import { Refresh } from '@element-plus/icons-vue'

const router = useRouter()
const pendingList = ref([])
const loading = ref(false)

const fetchPendingVisits = async () => {
  loading.value = true
  try {
    const res = await request.get('/nurse/pending-visits')
    pendingList.value = res.data
  } catch (error) {
    console.error(error)
  } finally {
    loading.value = false
  }
}

const handleExecute = (visitId) => {
  router.push(`/nurse/execute/${visitId}`)
}

onMounted(() => {
  fetchPendingVisits()
})
</script>

<style scoped>
.pending-list-container {
  padding: 20px;
}
.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
</style>
