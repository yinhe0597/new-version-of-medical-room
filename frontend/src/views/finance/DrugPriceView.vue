<template>
  <div class="drug-view">
    <el-card>
      <template #header>
        <div class="card-header">
          <span>药品价格查看（只读）</span>
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
        <el-table-column prop="specification" label="规格" />
        <el-table-column prop="unit" label="单位" width="80" />
        <el-table-column prop="purchase_price" label="购进价" width="100">
          <template #default="scope">
            ¥ {{ scope.row.purchase_price ? scope.row.purchase_price.toFixed(2) : '0.00' }}
          </template>
        </el-table-column>
        <el-table-column prop="price" label="零售价" width="100">
          <template #default="scope">
            ¥ {{ scope.row.price.toFixed(2) }}
          </template>
        </el-table-column>
        <el-table-column prop="scattered_price" label="零卖单价" width="100">
          <template #default="scope">
            {{ scope.row.has_scattered ? '¥ ' + scope.row.scattered_price.toFixed(4) : '-' }}
          </template>
        </el-table-column>
        <el-table-column prop="stock" label="库存" width="80" />
        <el-table-column prop="status" label="状态" width="80">
          <template #default="scope">
            <el-tag :type="scope.row.status === 1 ? 'success' : 'info'" size="small">
              {{ scope.row.status === 1 ? '启用' : '停用' }}
            </el-tag>
          </template>
        </el-table-column>
      </el-table>

      <div class="pagination" v-if="total > 0">
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
import { ref, onMounted } from 'vue'
import request from '@/api/request'
import { ElMessage } from 'element-plus'

const keyword = ref('')
const drugList = ref([])
const loading = ref(false)
const page = ref(1)
const pageSize = ref(20)
const total = ref(0)

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
    ElMessage.error(error.msg || '获取列表失败')
  } finally {
    loading.value = false
  }
}

const handlePageChange = (val) => {
  page.value = val
  fetchDrugs()
}

onMounted(() => {
  fetchDrugs()
})
</script>

<style scoped>
.drug-view {
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
