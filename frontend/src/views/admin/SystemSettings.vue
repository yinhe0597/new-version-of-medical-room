<template>
  <div class="settings-container">
    <el-card>
      <template #header>
        <span>系统设置</span>
      </template>
      
      <el-form label-width="120px">
        <el-form-item label="数据备份">
          <el-button type="primary" :icon="DocumentCopy" @click="handleBackup" :loading="backingUp">
            一键备份数据
          </el-button>
          <div class="tip">系统将根据当前数据库下载 SQLite (.db) 或 MySQL (.sql) 备份文件。</div>
        </el-form-item>
        
        <el-divider />
        
        <el-form-item label="修改密码">
          <ChangePassword />
        </el-form-item>
      </el-form>
    </el-card>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import request from '@/api/request'
import ChangePassword from '@/components/ChangePassword.vue'
import { DocumentCopy } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'

const backingUp = ref(false)

const handleBackup = async () => {
  backingUp.value = true
  try {
    const res = await request.get('/admin/backup', {
      responseType: 'blob',
      timeout: 300000
    })
    
    const blobData = res
    if (blobData.type && blobData.type.includes('application/json')) {
       // If it's json, it might be an error message
       const reader = new FileReader()
       reader.onload = () => {
         const errorData = JSON.parse(reader.result)
         ElMessage.error(errorData.msg || '备份失败')
       }
       reader.readAsText(blobData)
       return
    }

    const timestamp = new Date().toISOString().replace(/[-:T]/g, '').split('.')[0]
    const extension = blobData.type && blobData.type.includes('sqlite') ? 'db' : 'sql'
    const filename = `medical_db_backup_${timestamp}.${extension}`

    const url = window.URL.createObjectURL(blobData)
    const link = document.createElement('a')
    link.href = url
    link.setAttribute('download', filename)
    document.body.appendChild(link)
    link.click()
    document.body.removeChild(link)
    window.setTimeout(() => window.URL.revokeObjectURL(url), 0)
    
    ElMessage.success('备份已生成并开始下载')
  } catch (error) {
    ElMessage.error(error.msg || '备份失败')
  } finally {
    backingUp.value = false
  }
}

</script>

<style scoped>
.settings-container {
  padding: 20px;
  max-width: 600px;
}
.tip {
  font-size: 12px;
  color: #909399;
  margin-top: 5px;
}
</style>
