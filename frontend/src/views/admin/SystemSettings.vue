<template>
  <div class="settings-container">
    <el-card>
      <template #header>
        <span>系统设置</span>
      </template>
      
      <el-form label-width="120px">
        <el-form-item label="数据备份">
          <el-button type="primary" :icon="DocumentCopy" @click="handleBackup" :loading="backingUp">
            立即备份数据库
          </el-button>
          <div class="tip">系统将自动导出当前数据库文件到服务器备份目录。</div>
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
    const res = await request.post('/admin/backup')
    ElMessage.success(`备份成功，文件名：${res.filename}`)
  } catch (error) {
    ElMessage.error(error.msg || '备份失败')
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
