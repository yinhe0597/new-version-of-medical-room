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
          <div class="tip">系统将直接导出数据库所有数据并打包成 mysql (.sql) 文件下载到您的桌面或本地下载目录。</div>
        </el-form-item>
        
        <el-divider />
        
        <el-form-item label="修改密码">
          <el-button type="warning" @click="showPasswordDialog = true">修改当前用户密码</el-button>
        </el-form-item>
      </el-form>
    </el-card>

    <el-dialog v-model="showPasswordDialog" title="修改密码" width="400px">
      <el-form :model="passwordForm" label-width="100px">
        <el-form-item label="原密码">
          <el-input v-model="passwordForm.old" type="password" show-password></el-input>
        </el-form-item>
        <el-form-item label="新密码">
          <el-input v-model="passwordForm.new" type="password" show-password></el-input>
        </el-form-item>
        <el-form-item label="确认新密码">
          <el-input v-model="passwordForm.confirm" type="password" show-password></el-input>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showPasswordDialog = false">取消</el-button>
        <el-button type="primary" @click="changePassword">确定</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import request from '@/api/request'
import { DocumentCopy } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'

const backingUp = ref(false)
const showPasswordDialog = ref(false)
const passwordForm = ref({
  old: '',
  new: '',
  confirm: ''
})

const handleBackup = async () => {
  backingUp.value = true
  try {
    const res = await request.get('/admin/backup', { responseType: 'blob' })
    
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
    const filename = `medical_db_backup_${timestamp}.sql`

    const url = window.URL.createObjectURL(new Blob([blobData]))
    const link = document.createElement('a')
    link.href = url
    link.setAttribute('download', filename)
    document.body.appendChild(link)
    link.click()
    document.body.removeChild(link)
    
    ElMessage.success('备份已生成并开始下载')
  } catch (error) {
    ElMessage.error('备份失败')
  } finally {
    backingUp.value = false
  }
}

const changePassword = () => {
  // Mock implementation as API was not defined in spec
  ElMessage.info('修改密码功能需后端API支持')
  showPasswordDialog.value = false
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
